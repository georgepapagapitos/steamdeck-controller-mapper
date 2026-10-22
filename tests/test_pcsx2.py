import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from tests.test_players import GAME_MODE_INFO, GAME_MODE_PROC, joysticks
from maphelper import cli
from maphelper.adapters.pcsx2 import FILE, PCSX2Adapter
from maphelper.devices import SDL_ORDER_SLOTS
from maphelper.formats.ini import IniDocument
from maphelper.model import Controller, Target
from maphelper.resolve import Choice, Resolution, resolve
from maphelper.store import load_layouts, load_rules
from maphelper.writer import Patch, apply_patches, is_managed

FIXTURES = REPO / "tests" / "fixtures"
LIVE = FIXTURES / "pcsx2" / "dualsense-bt"              # the owner's Deck, PCSX2 already migrated to SDL3 names
TEMPLATE = FIXTURES / "pcsx2" / "emudeck-default"       # EmuDeck's fallback template, SDL2-era names
GOLDEN = REPO / "tests" / "golden" / "pcsx2"
LAYOUTS = load_layouts(REPO / "data" / "layouts")
EDGE = Controller(device_ids=("usb:1",), model="sony.dualsense-edge", family="sony.dualsense", brand="sony",
                  style="playstation", capabilities=frozenset({"paddles", "rumble"}))
BLUE_DS4 = Controller(device_ids=("mac:aa:bb:cc:dd:ee:ff",), model="sony.ds4.v2", family="sony.dualshock4",
                      brand="sony", style="playstation", capabilities=frozenset({"gyro", "rumble"}))


def reader(root: Path, name: str = FILE):
    doc = IniDocument.parse((root / name).read_text(encoding="utf-8"))
    return lambda file, section, key: doc.get(section, key) if file == FILE else None


class PCSX2GoldenTest(unittest.TestCase):
    """examples/ rules, P1 = DualSense Edge (paddles on L3/R3), P2 = the blue DS4 (worn stick), on the Deck's live
    PCSX2.ini."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "config"
        shutil.copytree(LIVE, self.root)
        rules = load_rules(REPO / "examples", "user").rules
        target = Target("ps2", "pcsx2")
        self.players = {1: resolve(rules, EDGE, target, LAYOUTS), 2: resolve(rules, BLUE_DS4, target, LAYOUTS)}
        self.adapter = PCSX2Adapter()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def current(self, file, section, key):
        path = self.root / file
        return IniDocument.parse(path.read_text(encoding="utf-8")).get(section, key) if path.exists() else None

    def apply(self, dry_run=False):
        rendered = self.adapter.render(self.players, current=self.current)
        return rendered, apply_patches(self.root, rendered.patches, self.adapter.managed_keys,
                                       state_dir=self.tmp / "state", dry_run=dry_run)

    def test_matches_golden_diff(self):
        _, result = self.apply(dry_run=True)
        path = GOLDEN / "edge-ds4.diff"
        if os.environ.get("UPDATE_GOLDEN"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(result.diff, encoding="utf-8")
        self.assertEqual(result.diff, path.read_text(encoding="utf-8"))

    def test_expected_values(self):
        rendered, result = self.apply()
        self.assertEqual(result.rejected, [])
        self.assertEqual(rendered.warnings, [])
        ini = IniDocument.parse((self.root / FILE).read_text(encoding="utf-8"))
        self.assertEqual(ini.get("Pad1", "L3"), "SDL-0/Paddle1")             # model rule
        self.assertEqual(ini.get("Pad1", "R3"), "SDL-0/Paddle2")
        self.assertEqual(ini.get("Pad2", "L3"), "SDL-1/LeftStick")           # not an Edge: untouched
        self.assertEqual(ini.get("Pad2", "Deadzone"), "0.180000")            # device rule
        self.assertEqual(ini.get("Pad1", "Deadzone"), "0.000000")
        self.assertEqual(ini.get("Hotkeys", "ShutdownVM"), "SDL-0/Back & SDL-0/Start")
        self.assertEqual(ini.get("UI", "SettingsVersion"), "1")

    def test_only_managed_lines_change(self):
        before = (LIVE / FILE).read_text(encoding="utf-8").splitlines()
        self.apply()
        after = (self.root / FILE).read_text(encoding="utf-8").splitlines()
        changed_keys = {l.split("=")[0].strip() for l in set(after) ^ set(before) if "=" in l}
        # Hotkeys are rendered too, but EmuDeck's already hold the same chords, so they don't change.
        self.assertEqual(changed_keys, {"L3", "R3", "Deadzone"})

    def test_second_apply_is_noop_and_pristine_kept(self):
        self.apply()
        mtime = (self.root / FILE).stat().st_mtime_ns
        _, again = self.apply()
        self.assertEqual(again.changed_files, [])
        self.assertEqual((self.root / FILE).stat().st_mtime_ns, mtime)
        pristine = self.tmp / "state" / "backups" / "pristine" / FILE
        self.assertEqual(pristine.read_text(encoding="utf-8"), (LIVE / FILE).read_text(encoding="utf-8"))

    def test_unmanaged_patches_are_rejected(self):
        managed = self.adapter.managed_keys
        for patch in (Patch(FILE, "UI", "SettingsVersion", "2"), Patch(FILE, "Folders", "Bios", "/tmp"),
                      Patch(FILE, "Pad1", "AxisScale", "1"), Patch(FILE, "Hotkeys", "ZoomIn", "SDL-0/Start"),
                      Patch(FILE, "Pad", "MultitapPort1", "true"), Patch("inis/other.ini", "Pad1", "Cross", "x")):
            self.assertFalse(is_managed(patch, managed), patch)

    def test_legacy_names_are_written_as_sdl3(self):
        # EmuDeck's template still says SDL-0/A; a pause rule writes the positional SDL3 name.
        pause = Resolution(bindings={"hotkey.pause": Choice({"chord": ["select", "face_south"]}, "t")})
        out = self.adapter.render({1: pause}, current=reader(TEMPLATE / "inis", "PCSX2.ini"))
        self.assertEqual([(p.section, p.key, p.value) for p in out.patches],
                         [("Hotkeys", "TogglePause", "SDL-0/Back & SDL-0/FaceSouth")])


class PCSX2TokenTest(unittest.TestCase):
    def setUp(self):
        self.adapter = PCSX2Adapter()

    def render(self, bindings=None, options=None, player=1, current=None):
        res = Resolution(bindings={k: Choice(v, "t") for k, v in (bindings or {}).items()},
                         options={k: Choice(v, "t") for k, v in (options or {}).items()})
        return self.adapter.render({player: res}, current=current or reader(LIVE))

    def values(self, out):
        return {(p.section, p.key): p.value for p in out.patches}

    def test_axis_target_with_invert(self):
        out = self.render({"ps2.dualshock2.rstick_y": {"input": "rs_y", "invert": True}})
        self.assertEqual(self.values(out), {("Pad1", "RUp"): "SDL-0/+RightY", ("Pad1", "RDown"): "SDL-0/-RightY"})

    def test_button_from_half_axis_chord_and_none(self):
        out = self.render({"ps2.dualshock2.cross": {"input": "ls_down"},
                           "ps2.dualshock2.analog": {"chord": ["select", "l3"]},
                           "ps2.dualshock2.l1": {"input": "none"}}, player=2)
        self.assertEqual(self.values(out), {("Pad2", "Cross"): "SDL-1/+LeftY",
                                            ("Pad2", "Analog"): "SDL-1/Back & SDL-1/LeftStick",
                                            ("Pad2", "L1"): ""})

    def test_full_axis_on_button_and_gyro_warn(self):
        out = self.render({"ps2.dualshock2.cross": {"input": "ls_x"}, "ps2.dualshock2.circle": {"input": "gyro"}})
        self.assertEqual(out.patches, [])
        self.assertEqual(len(out.warnings), 2)

    def test_hotkeys_toggle_hold_and_missing(self):
        out = self.render({"hotkey.fast_forward": {"chord": ["select", "r2"]},
                           "hotkey.fast_forward_hold": {"chord": ["select", "l2"]},
                           "hotkey.rewind": {"chord": ["select", "l1"]}})
        self.assertEqual(self.values(out), {("Hotkeys", "ToggleTurbo"): "SDL-0/Back & SDL-0/+RightTrigger",
                                            ("Hotkeys", "HoldTurbo"): "SDL-0/Back & SDL-0/+LeftTrigger"})
        self.assertEqual(out.warnings, ["pcsx2: no hotkey for hotkey.rewind"])

    def test_options(self):
        out = self.render(options={"rumble.enabled": False, "deadzones.ls": 0.1, "deadzones.rs": 0.25,
                                   "controller_type": "dualshock2"})
        self.assertEqual(self.values(out), {("Pad1", "LargeMotor"): "", ("Pad1", "SmallMotor"): "",
                                            ("Pad1", "Deadzone"): "0.250000", ("Pad1", "Type"): "DualShock2"})
        self.assertEqual(len(out.warnings), 1)                  # two deadzones, one key
        kept = self.render(options={"rumble.enabled": True})    # EmuDeck's motor bindings stay
        self.assertEqual(kept.patches, [])

    def test_pad_with_type_none_warns(self):
        # The capture's own .bak, from before EmuDeck set Pad2 up: Type = None.
        out = self.render({"ps2.dualshock2.cross": {"input": "face_south"}}, player=2,
                          current=reader(LIVE / "inis", "PCSX2.ini.bak"))
        self.assertIn("Type is None", " ".join(out.warnings))

    def test_players_past_two_need_a_multitap(self):
        out = self.adapter.render({3: Resolution()}, current=reader(LIVE), devices={3: "SDL-2"})
        self.assertEqual(out.patches, [])
        self.assertIn("multitap", out.warnings[0])


class PCSX2DeviceTest(unittest.TestCase):
    def setUp(self):
        self.adapter = PCSX2Adapter()

    def test_virtual_pads_are_their_slot_whatever_the_node_order(self):
        # DualSense in slot 0 ("pad 0", js5), the Deck in slot 1 ("pad 1", js0).
        joys = joysticks(GAME_MODE_PROC, GAME_MODE_INFO, SDL_ORDER_SLOTS)
        self.assertEqual({j.name: self.adapter.device_ref(j, joys) for j in joys},
                         {"DualSense Wireless Controller": "SDL-0", "Steam Deck Controller": "SDL-1"})

    def test_a_native_pad_takes_the_first_free_index(self):
        # Only the Deck's slot 1 is behind Steam: the DualSense, with Steam Input off, fills index 0.
        info = "[slot 1]\nname=Steam Deck Controller\nVID=0x28de\nPID=0x1205\nhandle=0x1\ntype=steam\n"
        proc = GAME_MODE_PROC.split('I: Bus=0003 Vendor=28de Product=11ff Version=0001\nN: Name="Microsoft X-Box 360 '
                                    'pad 0"')[0]
        joys = joysticks(proc, info, SDL_ORDER_SLOTS, behind_steam=set())
        refs = {j.device.name: self.adapter.device_ref(j, joys) for j in joys}
        self.assertEqual(refs["Microsoft X-Box 360 pad 1"], "SDL-1")
        self.assertEqual(refs["DualSense Wireless Controller"], "SDL-0")

    def test_repoint_moves_every_pad_reference(self):
        out = self.adapter.render({}, current=reader(LIVE), devices={1: "SDL-1", 2: "SDL-0"})
        values = {(p.section, p.key): p.value for p in out.patches}
        self.assertEqual(values[("Pad1", "Cross")], "SDL-1/FaceSouth")
        self.assertEqual(values[("Pad2", "Analog")], "SDL-0/Guide")
        self.assertNotIn(("Pad1", "Analog"), values)                          # Keyboard/F6 stays
        self.assertEqual(values[("Hotkeys", "ShutdownVM")], "SDL-1/Back & SDL-1/Start")
        self.assertEqual(values[("Hotkeys", "CycleAspectRatio")], "SDL-1/Start & SDL-1/DPadRight")
        self.assertNotIn(("Hotkeys", "Screenshot"), values)                   # Keyboard/F8 stays
        self.assertTrue(all(is_managed(p, self.adapter.managed_keys) for p in out.patches))
        same = self.adapter.render({}, current=reader(LIVE), devices={1: "SDL-0", 2: "SDL-1"})
        self.assertEqual(same.patches, [])


class PCSX2CliTest(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        self.assertEqual(code, 0, err.getvalue())
        return out.getvalue(), err.getvalue()

    def test_docked_puts_the_switch_pro_on_pad_1(self):
        # docked capture: the Deck in slot 0, the Switch Pro in slot 1; external-first makes the Switch Pro player 1,
        # so Pad1 and the hotkeys move to SDL-1 and Pad2 to the Deck's SDL-0.
        root = FIXTURES / "devices" / "docked"
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(LIVE, tmp / "pcsx2")
        (tmp / "no-rules").mkdir()
        out, err = self.run_cli("apply", "--emulator", "pcsx2", "--system", "ps2", "--config-root", str(tmp / "pcsx2"),
                                "--ignore-devices", "", "--proc-file", str(root / "proc-bus-input-devices"),
                                "--virtual-info", str(root / "virtualgamepadinfo.txt"),
                                "--drm-status", str(root / "drm-status.txt"), "--sys-root", str(tmp),
                                "--rules", str(tmp / "no-rules"))
        self.assertIn("player 1: Nintendo Switch Pro Controller (steam slot 1)", err)
        path = GOLDEN / "docked.diff"
        if os.environ.get("UPDATE_GOLDEN"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(out, encoding="utf-8")
        self.assertEqual(out, path.read_text(encoding="utf-8"))

    def test_explicit_players_keep_each_pads_device(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(LIVE, tmp / "pcsx2")
        out, _ = self.run_cli("apply", "--emulator", "pcsx2", "--system", "ps2", "--config-root", str(tmp / "pcsx2"),
                              "--player", "sony.dualsense", "--player", "sony.dualsense",
                              "--state-dir", str(tmp / "state"))
        self.assertEqual(out.strip(), "No changes.")                          # examples' hotkeys match EmuDeck's


if __name__ == "__main__":
    unittest.main()
