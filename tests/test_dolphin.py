import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper.adapters.dolphin import DolphinAdapter
from maphelper.formats.ini import IniDocument
from maphelper.model import Controller, Target
from maphelper.resolve import resolve
from maphelper.store import load_layouts, load_rules
from maphelper.writer import Patch, apply_patches

FIXTURE = REPO / "tests" / "fixtures" / "dolphin" / "emudeck-default"
GOLDEN = REPO / "tests" / "golden" / "dolphin" / "ds4-melee.diff"
LAYOUTS = load_layouts(REPO / "data" / "layouts")
BLUE_DS4 = Controller(device_ids=("mac:aa:bb:cc:dd:ee:ff",), model="sony.ds4.v2", family="sony.dualshock4",
                      brand="sony", style="playstation", capabilities=frozenset({"gyro", "rumble"}))
XBOX = Controller(device_ids=("usb:1",), model="ms.xbox-one", family="ms.xbox-one", brand="microsoft", style="xbox")


class DolphinGoldenTest(unittest.TestCase):
    """examples/ rules, P1 = DS4, P2 = Xbox pad, launching Melee, against EmuDeck's shipped config."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "config"
        shutil.copytree(FIXTURE, self.root)
        rules = load_rules(REPO / "examples", "user").rules
        target = Target("gc", "dolphin", "GALE01")
        self.players = {1: resolve(rules, BLUE_DS4, target, LAYOUTS), 2: resolve(rules, XBOX, target, LAYOUTS)}
        self.adapter = DolphinAdapter()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def current(self, file, section, key):
        path = self.root / file
        return IniDocument.parse(path.read_text()).get(section, key) if path.exists() else None

    def apply(self, dry_run=False):
        rendered = self.adapter.render(self.players, current=self.current)
        return rendered, apply_patches(self.root, rendered.patches, self.adapter.managed_keys,
                                       state_dir=self.tmp / "state", dry_run=dry_run)

    def test_matches_golden_diff(self):
        _, result = self.apply(dry_run=True)
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(result.diff)
        self.assertEqual(result.diff, GOLDEN.read_text())

    def test_expected_values(self):
        rendered, result = self.apply()
        self.assertEqual(result.rejected, [])
        pad = IniDocument.parse((self.root / "GCPadNew.ini").read_text())
        self.assertEqual(pad.get("GCPad1", "Buttons/A"), "`Button S`")       # family rule
        self.assertEqual(pad.get("GCPad1", "Buttons/Z"), "`Shoulder L`")     # game rule beats family rule
        self.assertEqual(pad.get("GCPad1", "Main Stick/Dead Zone"), "18.00")  # device rule
        self.assertEqual(pad.get("GCPad1", "Rumble/Motor"), "Strong")         # EmuDeck's motor kept
        self.assertEqual(pad.get("GCPad2", "Buttons/Z"), "`Shoulder L`")     # game rule applies to any controller
        self.assertEqual(pad.get("GCPad2", "Buttons/A"), "`Button E`")       # no family rule for Xbox: untouched
        hotkeys = IniDocument.parse((self.root / "Hotkeys.ini").read_text())
        self.assertEqual(hotkeys.get("Hotkeys", "General/Exit"), "@(Back+Start)")
        self.assertEqual(hotkeys.get("Hotkeys", "Save State/Save to Selected Slot"), "@(Back+`Shoulder R`)")

    def test_only_managed_lines_change(self):
        before = (FIXTURE / "GCPadNew.ini").read_text().splitlines()
        self.apply()
        after = (self.root / "GCPadNew.ini").read_text().splitlines()
        changed_keys = {l.split("=")[0].strip() for l in set(after) ^ set(before) if "=" in l}
        # Triggers/L-Analog etc. are rendered too, but already hold the same value, so they don't change.
        self.assertEqual(changed_keys, {"Buttons/A", "Buttons/B", "Buttons/X", "Buttons/Y", "Buttons/Z",
                                        "Main Stick/Dead Zone"})

    def test_second_apply_is_noop_and_pristine_kept(self):
        self.apply()
        mtime = (self.root / "GCPadNew.ini").stat().st_mtime_ns
        _, again = self.apply()
        self.assertEqual(again.changed_files, [])
        self.assertEqual((self.root / "GCPadNew.ini").stat().st_mtime_ns, mtime)
        pristine = self.tmp / "state" / "backups" / "pristine" / "GCPadNew.ini"
        self.assertEqual(pristine.read_text(), (FIXTURE / "GCPadNew.ini").read_text())

    def test_unmanaged_patch_is_rejected(self):
        result = apply_patches(self.root, [Patch("Dolphin.ini", "Core", "CPUCore", "0")],
                               self.adapter.managed_keys, dry_run=True)
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.changed_files, [])


class DolphinTokenTest(unittest.TestCase):
    def setUp(self):
        self.adapter = DolphinAdapter()

    def render_one(self, target, source):
        from maphelper.resolve import Choice, Resolution
        res = Resolution(bindings={target: Choice(value=source, rule_id="t")})
        return self.adapter.render({1: res})

    def test_axis_target_with_invert(self):
        out = self.render_one("gc.standard.main_y", {"input": "ls_y", "invert": True})
        self.assertEqual({p.key: p.value for p in out.patches},
                         {"Main Stick/Up": "`Left Y-`", "Main Stick/Down": "`Left Y+`"})

    def test_letters_only_token_is_bare(self):
        out = self.render_one("gc.standard.start", {"input": "start"})
        self.assertEqual(out.patches[0].value, "Start")

    def test_unbound(self):
        out = self.render_one("gc.standard.z", {"input": "none"})
        self.assertEqual(out.patches[0].value, "")

    def test_full_axis_on_button_warns(self):
        out = self.render_one("gc.standard.a", {"input": "ls_x"})
        self.assertEqual(out.patches, [])
        self.assertTrue(out.warnings)


class UntouchedKeysTest(unittest.TestCase):
    """Owner decision 2026-10-22: keys only shipped defaults decide keep the live value."""

    def apply(self, rules_dir):
        import contextlib, io, shutil, tempfile
        from pathlib import Path
        from maphelper.cli import main
        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "tests/fixtures/dolphin/dualsense-bt", tmp / "cfg")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            main(["apply", "--emulator", "dolphin", "--system", "gc", "--config-root", str(tmp / "cfg"),
                  "--player", "sony.dualsense", "--rules", str(rules_dir), "--state-dir", str(tmp / "state")])
        return out.getvalue()

    def test_no_user_rules_leaves_a_real_config_alone(self):
        # The owner's live GCPadNew.ini predates EmuDeck's current template (Z = `Shoulder R`|Back,
        # fast-forward Start+RT); shipped defaults alone must not rewrite it.
        import tempfile
        self.assertEqual(self.apply(tempfile.mkdtemp()).strip(), "No changes.")

    def test_a_user_rule_still_applies(self):
        import json, tempfile
        rules = Path(tempfile.mkdtemp())
        (rules / "screenshot.json").write_text(json.dumps({
            "schema_version": 1, "id": "user.test.screenshot",
            "applies_to": {"controller": {"level": "any"}, "content": {"level": "global"}},
            "bindings": {"hotkey.screenshot": {"chord": ["select", "face_east"]}}}), encoding="utf-8")
        diff = self.apply(rules)
        self.assertIn("+General/Take Screenshot = @(Back+`Button E`)", diff)
        self.assertNotIn("Buttons/Z", diff)


if __name__ == "__main__":
    unittest.main()
