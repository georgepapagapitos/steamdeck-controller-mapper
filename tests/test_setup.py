"""map-helper setup / uninstall, and doctor's launch-hook checks, against EmuDeck's own SRM parsers and ES-DE settings."""

import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from tests.test_doctor import SRM_DOLPHIN, binary_vdf
from maphelper import cli, doctor, setup

FIXTURES = REPO / "tests" / "fixtures"
SRM = FIXTURES / "srm" / "emudeck-default" / "userConfigurations.json"
ES_SETTINGS = FIXTURES / "es-de" / "emudeck-default" / "es_settings.xml"


def digest(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.entry = self.home / ".local/lib/map-helper/current/mh_entry.py"
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text("", encoding="utf-8")
        self.places = setup.Places(home=self.home, entry=self.entry, proc_root=self.home / "proc")
        (self.home / "proc").mkdir()
        self.srm = self.places.srm_config
        self.srm.parent.mkdir(parents=True)
        shutil.copy2(SRM, self.srm)
        self.places.esde_settings.parent.mkdir(parents=True)
        shutil.copy2(ES_SETTINGS, self.places.esde_settings)

    def parsers(self) -> dict:
        return {p["configTitle"]: p for p in json.loads(self.srm.read_text(encoding="utf-8"))}

    def run_process(self, name):
        pid = self.home / "proc" / "4242"
        pid.mkdir()
        (pid / "cmdline").write_bytes(name.encode() + b"\0--flag\0")


class SetupTest(Base):
    def test_dry_run_changes_nothing(self):
        before = digest(self.home)
        report = setup.setup(self.places)
        self.assertEqual(digest(self.home), before)
        self.assertIn("would wrap parser \"Nintendo GameCube - Dolphin\" (dolphin)", setup.render(report))

    def test_setup_wraps_managed_parsers_only(self):
        report = setup.setup(self.places, write=True)
        self.assertFalse(report.refused, setup.render(report))
        shim = str(self.places.shim)
        p = self.parsers()
        self.assertEqual(p["Nintendo GameCube - Dolphin"]["executableArgs"],
                         f'vblank_mode=0 {shim} --emulator dolphin -- %command% -b -e "${{filePath}}"')
        self.assertFalse(p["Nintendo GameCube - Dolphin"]["executable"]["appendArgsToExecutable"])
        # RetroArch's parsers put their args in the Exe: wrapping them would change the shortcuts' app ids.
        snes = p["Nintendo SNES (Super Nintendo) - RetroArch Snes9x"]
        self.assertNotIn("mh-run", snes["executableArgs"])
        self.assertTrue(snes["executable"]["appendArgsToExecutable"])
        # No descriptor for PUAE, and not an emulator we manage: untouched.
        self.assertNotIn("mh-run", p["Amiga - RetroArch PUAE"]["executableArgs"])
        self.assertNotIn("mh-run", p["Sony PlayStation - DuckStation"]["executableArgs"])
        self.assertNotIn("mh-run", p["Nintendo Metroid Prime Trilogy - PrimeHack"]["executableArgs"])
        self.assertTrue(os.access(self.places.shim, os.X_OK))
        self.assertTrue(os.access(self.places.esde_script, os.X_OK))
        self.assertIn('<bool name="CustomEventScripts" value="true" />',
                      self.places.esde_settings.read_text(encoding="utf-8"))
        self.assertTrue(Path(setup.load_record(self.places.state_dir)["srm"]["backup"]).is_file())
        self.assertIn("new app ids", setup.render(report))

    def test_only_the_edited_values_change(self):
        before = SRM.read_text(encoding="utf-8").splitlines()
        setup.setup(self.places, write=True)
        after = self.srm.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(before), len(after))
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertTrue(changed)
        for old, new in changed:
            self.assertIn('"executableArgs"', old)

    def test_idempotent_and_uninstall_gives_back_identical_files(self):
        before = digest(self.home)
        setup.setup(self.places, write=True)
        once = {k: v for k, v in digest(self.home).items() if "setup.json" not in k}
        report = setup.setup(self.places, write=True)
        self.assertEqual({k: v for k, v in digest(self.home).items() if "setup.json" not in k}, once)
        self.assertFalse([c for c in report.changes if c.action in ("install", "update")], setup.render(report))

        setup.uninstall(self.places, write=True)
        after = digest(self.home)
        self.assertEqual({k: v for k, v in after.items() if "/backups/" not in k}, before)
        self.assertEqual(self.srm.read_bytes(), SRM.read_bytes())
        self.assertEqual(self.places.esde_settings.read_bytes(), ES_SETTINGS.read_bytes())
        self.assertFalse(self.places.shim.exists())
        self.assertEqual(setup.load_record(self.places.state_dir), {})
        again = setup.uninstall(self.places, write=True)
        self.assertEqual([c.action for c in again.changes], ["ok"])

    def test_uninstall_dry_run_changes_nothing(self):
        setup.setup(self.places, write=True)
        before = digest(self.home)
        report = setup.uninstall(self.places)
        self.assertEqual(digest(self.home), before)
        self.assertIn("would unwrap", setup.render(report))

    def test_uninstall_leaves_later_edits(self):
        setup.setup(self.places, write=True)
        # The user changed the Dolphin parser's args after setup, keeping our prefix; and edited the shim.
        text = self.srm.read_text(encoding="utf-8").replace('-b -e \\"${filePath}\\"', '-b -C x -e \\"${filePath}\\"', 1)
        self.srm.write_text(text, encoding="utf-8")
        self.places.shim.write_text("#!/bin/sh\n# mine now\n", encoding="utf-8")
        report = setup.uninstall(self.places, write=True)
        p = self.parsers()
        self.assertEqual(p["Nintendo GameCube - Dolphin"]["executableArgs"],
                         'vblank_mode=0 %command% -b -C x -e "${filePath}"')
        self.assertTrue(self.places.shim.exists())
        self.assertIn("leave", [c.action for c in report.changes])

    def test_refuses_while_srm_runs(self):
        self.run_process("/tmp/.mount_SteamRxyz/steam-rom-manager")
        before = self.srm.read_bytes()
        report = setup.setup(self.places, write=True)
        self.assertTrue(report.refused)
        self.assertEqual(self.srm.read_bytes(), before)

    def test_uninstall_keeps_the_shim_while_srm_runs(self):
        # The parsers stay wrapped while SRM runs, so their shortcuts still run the shim: it must stay too (fail open).
        setup.setup(self.places, write=True)
        self.run_process("/tmp/.mount_SteamRxyz/steam-rom-manager")
        report = setup.uninstall(self.places, write=True)
        self.assertTrue(report.refused)
        self.assertTrue(self.places.shim.exists())

    def test_refuses_the_setting_while_es_de_runs(self):
        self.run_process("/tmp/.mount_ES-DE.abc/usr/bin/es-de")
        report = setup.setup(self.places, write=True)
        self.assertTrue(report.refused)
        self.assertEqual(self.places.esde_settings.read_bytes(), ES_SETTINGS.read_bytes())
        self.assertTrue(self.places.esde_script.is_file())       # the script itself is harmless while it runs

    def test_flips_an_existing_setting_and_back(self):
        text = '<?xml version="1.0"?>\n<bool name="CustomEventScripts" value="false" />\n<bool name="X" value="true" />\n'
        self.places.esde_settings.write_text(text, encoding="utf-8")
        setup.setup(self.places, write=True)
        self.assertIn('"CustomEventScripts" value="true"', self.places.esde_settings.read_text(encoding="utf-8"))
        setup.uninstall(self.places, write=True)
        self.assertEqual(self.places.esde_settings.read_text(encoding="utf-8"), text)

    def test_a_foreign_shim_is_not_overwritten(self):
        self.places.shim.parent.mkdir(parents=True)
        self.places.shim.write_text("#!/bin/sh\necho someone else's\n", encoding="utf-8")
        report = setup.setup(self.places, write=True)
        self.assertTrue(report.refused)
        self.assertIn("someone else's", self.places.shim.read_text(encoding="utf-8"))

    def test_reports_automap(self):
        settings = self.places.emudeck_settings
        settings.parent.mkdir(parents=True)
        settings.write_text("autoMapDolphin=true\ncheevos_password=made-up\n", encoding="utf-8")
        text = setup.render(setup.setup(self.places))
        self.assertIn("AutoMap is on for Dolphin", text)
        self.assertNotIn("made-up", text)

    def test_parse_spans_matches_json(self):
        text = SRM.read_text(encoding="utf-8")
        doc, spans = setup.parse_spans(text)
        self.assertEqual(doc, json.loads(text))
        start, end = spans[(0, "configTitle")]
        self.assertEqual(text[start:end], '"Emulators - Emulators"')

    def test_wrap_args_shapes(self):
        shim = Path("/home/deck/.local/bin/mh-run")
        self.assertEqual(setup.wrap_args('vblank_mode=0 %command% -b -e "${filePath}"', "dolphin", shim),
                         'vblank_mode=0 /home/deck/.local/bin/mh-run --emulator dolphin -- %command% -b -e "${filePath}"')
        self.assertEqual(setup.wrap_args('-batch -fullscreen -nogui "${filePath}"', "pcsx2", shim),
                         '/home/deck/.local/bin/mh-run --emulator pcsx2 -- %command% -batch -fullscreen -nogui '
                         '"${filePath}"')
        self.assertEqual(setup.wrap_args("", "pcsx2", Path("/a b/mh-run")), '"/a b/mh-run" --emulator pcsx2 -- %command%')

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["setup", "--home", str(self.home), "--entry", str(self.entry)])
        self.assertEqual(code, 0)
        self.assertIn("Dry run: nothing changed", out.getvalue())


class DoctorHooksTest(Base):
    def checks(self, steam_root=None):
        return [(f.severity, f.message) for f in doctor.check_launch_hooks(self.home, steam_root or self.home / "Steam")]

    def test_before_setup_everything_is_info(self):
        self.places.esde_script.parent.mkdir(parents=True, exist_ok=True)
        found = self.checks()
        self.assertTrue(found)
        self.assertEqual({s for s, _ in found}, {"info"})

    def test_after_setup_no_problems(self):
        setup.setup(self.places, write=True)
        self.assertEqual(self.checks(), [])

    def test_custom_event_scripts_off_is_an_error(self):
        setup.setup(self.places, write=True)
        shutil.copy2(ES_SETTINGS, self.places.esde_settings)
        self.assertEqual([s for s, m in self.checks() if "custom event scripts are off" in m], ["error"])

    def test_missing_shim_after_setup_is_an_error(self):
        setup.setup(self.places, write=True)
        self.places.shim.unlink()
        self.assertIn("error", [s for s, m in self.checks() if "no shim" in m])

    def test_shortcuts_saved_before_setup(self):
        setup.setup(self.places, write=True)
        config = self.home / "Steam" / "userdata" / "12345" / "config"
        config.mkdir(parents=True)
        # RetroArch's SRM shortcuts carry their args in the Exe; setup leaves them alone, so doctor doesn't nag.
        retroarch = {"AppName": "Made Up Game", "Exe": '"/home/deck/Emulation/tools/launchers/retroarch.sh" -L '
                     '/home/deck/.var/app/org.libretro.RetroArch/config/retroarch/cores/snes9x_libretro.so '
                     '"/run/media/sd/Emulation/roms/snes/Made Up Game.sfc"'}
        (config / "shortcuts.vdf").write_bytes(binary_vdf({"shortcuts": {"0": SRM_DOLPHIN, "1": retroarch}}))
        found = self.checks(self.home / "Steam")
        self.assertEqual([m for s, m in found if "don't run mh-run yet" in m and s == "warning"],
                         ["steam: 1 emulator shortcut(s) don't run mh-run yet (Super Mario Sunshine); run Steam ROM "
                          "Manager's \"Save to Steam\" to pick up the parser change"])


if __name__ == "__main__":
    unittest.main()
