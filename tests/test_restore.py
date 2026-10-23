import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper.cli import main
from maphelper.writer import MANIFEST

RETROARCH = REPO / "tests" / "fixtures" / "retroarch" / "dualsense-bt"
DOLPHIN = REPO / "tests" / "fixtures" / "dolphin" / "emudeck-default"
REMAP = "config/remaps/Snes9x/Snes9x.rmp"      # EmuDeck ships only Snes9x.rmp.disabled: map-helper creates it


def tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def retroarch_save(path: Path, drop: str = "input_player2_", edit: dict = None):
    """What RetroArch's remap save on quit leaves (input_remapping_save_file, configuration.c @ eb7335f): a new file,
    keys sorted, device/port lines for each of input_max_users (5 here), the non-identity remaps it held, turbo
    settings. Lines starting with `drop` are left out, as the Deck's save left out player 2's (docs/13)."""
    keys = dict(ln.split(" = ", 1) for ln in path.read_text(encoding="utf-8").splitlines()
                if not ln.startswith(drop))
    for n in range(1, 6):
        keys |= {f"input_libretro_device_p{n}": '"1"', f"input_player{n}_analog_dpad_mode": '"0"',
                 f"input_remap_port_p{n}": f'"{n - 1}"'}
    keys |= {"input_turbo_enable": '"true"', "input_turbo_mode": '"0"', "input_turbo_period": '"6"'} | (edit or {})
    path.write_text("".join(f"{k} = {v}\n" for k, v in sorted(keys.items())), encoding="utf-8")


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.ra, self.dolphin, self.state = self.tmp / "retroarch", self.tmp / "dolphin", self.tmp / "state"
        shutil.copytree(RETROARCH, self.ra)
        shutil.copytree(DOLPHIN, self.dolphin)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv) + ["--state-dir", str(self.state)])
        return code, out.getvalue()

    def apply_retroarch(self, players=1):
        self.cli("apply", "--emulator", "retroarch", "--system", "snes", "--config-root", str(self.ra),
                 *["--player", "sony.dualsense"] * players, "--rules", str(REPO / "examples"), "--write")

    def created(self):
        return json.loads((self.state / MANIFEST).read_text(encoding="utf-8"))["retroarch"]["files"][REMAP]["created"]

    def apply_both(self):
        self.apply_retroarch()
        self.cli("apply", "--emulator", "dolphin", "--system", "gc", "--game", "GALE01",
                 "--config-root", str(self.dolphin), "--player", "sony.ds4.v2", "--rules", str(REPO / "examples"),
                 "--write")
        self.assertTrue((self.ra / REMAP).exists())
        self.assertNotEqual(tree(self.dolphin), tree(DOLPHIN))

    def test_manifest_records_created_and_modified_files(self):
        self.apply_both()
        manifest = json.loads((self.state / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["retroarch"]["files"][REMAP]["created"], True)
        self.assertEqual(manifest["dolphin"]["files"]["GCPadNew.ini"]["created"], False)
        self.assertTrue((self.state / "backups/pristine/dolphin/GCPadNew.ini").is_file())

    def test_restore_returns_every_file_to_the_fixture(self):
        self.apply_both()
        code, out = self.cli("restore")
        self.assertEqual(code, 0, out)
        self.assertIn(f"deleted        retroarch: {REMAP}", out)
        self.assertEqual(tree(self.ra), tree(RETROARCH))
        self.assertEqual(tree(self.dolphin), tree(DOLPHIN))
        self.assertIn("unchanged", self.cli("restore")[1])          # a second restore has nothing left to do

    def test_restore_one_emulator(self):
        self.apply_both()
        self.cli("restore", "--emulator", "retroarch")
        self.assertEqual(tree(self.ra), tree(RETROARCH))
        self.assertNotEqual(tree(self.dolphin), tree(DOLPHIN))

    def test_dry_run_changes_nothing(self):
        self.apply_both()
        before = (tree(self.ra), tree(self.dolphin), tree(self.state))
        code, out = self.cli("restore", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn(f"would delete   retroarch: {REMAP}", out)
        self.assertIn("would restore  dolphin: GCPadNew.ini", out)
        self.assertEqual((tree(self.ra), tree(self.dolphin), tree(self.state)), before)

    def test_a_created_file_someone_replaced_is_left_alone(self):
        # EmuDeck's abxy toggle renames Snes9x.rmp.disabled over the Snes9x.rmp we created
        self.apply_both()
        shutil.copy(self.ra / (REMAP + ".disabled"), self.ra / REMAP)
        code, out = self.cli("restore", "--emulator", "retroarch")
        self.assertEqual(code, 1)
        self.assertIn(f"skipped        retroarch: {REMAP}", out)
        self.assertTrue((self.ra / REMAP).exists())
        self.cli("restore", "--emulator", "retroarch", "--force")
        self.assertFalse((self.ra / REMAP).exists())

    def test_apply_over_a_replaced_created_file_makes_it_pristine(self):
        self.apply_both()
        shutil.copy(self.ra / (REMAP + ".disabled"), self.ra / REMAP)
        emudeck = (self.ra / REMAP).read_bytes()
        self.apply_both()                                             # writes over EmuDeck's file now
        self.cli("restore", "--emulator", "retroarch")
        self.assertEqual((self.ra / REMAP).read_bytes(), emudeck)    # EmuDeck's, not deleted

    def test_retroarchs_own_save_is_still_ours(self):
        # remap_save_on_exit (on in the capture) saves the loaded remap over ours when content closes
        self.apply_both()
        retroarch_save(self.ra / REMAP)
        code, out = self.cli("restore", "--emulator", "retroarch")
        self.assertEqual(code, 0, out)
        self.assertIn(f"deleted        retroarch: {REMAP}", out)
        self.assertEqual(tree(self.ra), tree(RETROARCH))

    def test_apply_over_retroarchs_save_rewrites_the_whole_managed_set(self):
        self.apply_retroarch(players=2)
        ours = (self.ra / REMAP).read_text(encoding="utf-8")
        self.assertIn("input_player2_btn_b", ours)
        retroarch_save(self.ra / REMAP)                             # player 2's lines are gone
        self.apply_retroarch(players=2)                             # what mh-run does at the next launch
        saved = (self.ra / REMAP).read_text(encoding="utf-8").splitlines()
        self.assertTrue(set(ours.splitlines()) <= set(saved))
        self.assertTrue(self.created())
        self.cli("restore", "--emulator", "retroarch")
        self.assertFalse((self.ra / REMAP).exists())

    def test_an_edit_saved_from_retroarch_makes_it_theirs(self):
        self.apply_both()
        retroarch_save(self.ra / REMAP, edit={"input_player1_btn_b": '"1"'})   # B sends Y, set in the Quick Menu
        edited = (self.ra / REMAP).read_bytes()
        self.apply_both()
        self.assertFalse(self.created())
        self.cli("restore", "--emulator", "retroarch")
        self.assertEqual((self.ra / REMAP).read_bytes(), edited)

    def test_a_save_with_remap_save_on_exit_off_is_theirs(self):
        # Then RetroArch only saves when the user picks Save Remap File, which makes it theirs.
        cfg = self.ra / "retroarch.cfg"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace('remap_save_on_exit = "true"',
                                                                 'remap_save_on_exit = "false"'), encoding="utf-8")
        self.apply_both()
        retroarch_save(self.ra / REMAP)
        self.assertEqual(self.cli("restore", "--emulator", "retroarch")[0], 1)
        self.assertTrue((self.ra / REMAP).exists())

    def test_named_backup(self):
        self.apply_both()
        applied = (tree(self.ra), tree(self.dolphin))
        self.assertEqual(self.cli("backup", "--name", "good")[0], 0)
        self.assertEqual(self.cli("backup", "--list")[1].strip(), "good")
        self.cli("restore")                                          # back to pristine...
        code, out = self.cli("restore", "--from", "good")            # ...and forward to the backup
        self.assertEqual(code, 0, out)
        self.assertEqual((tree(self.ra), tree(self.dolphin)), applied)
        self.assertEqual(self.cli("restore", "--from", "nope")[0], 2)
        self.assertEqual(self.cli("backup", "--name", "good")[0], 2)  # names aren't reused

    def test_backup_of_an_absent_file_deletes_it(self):
        # Backed up after Dolphin only: the remap didn't exist then, so restoring the backup removes it.
        self.cli("apply", "--emulator", "dolphin", "--system", "gc", "--game", "GALE01",
                 "--config-root", str(self.dolphin), "--player", "sony.ds4.v2", "--rules", str(REPO / "examples"),
                 "--write")
        self.cli("backup", "--name", "dolphin-only")
        dolphin = tree(self.dolphin)
        self.apply_both()
        self.cli("restore", "--from", "dolphin-only")
        self.assertEqual((tree(self.ra), tree(self.dolphin)), (tree(RETROARCH), dolphin))

    def test_never_deletes_outside_the_config_root(self):
        self.apply_both()
        outside = self.tmp / "outside.rmp"
        outside.write_text("x\n", encoding="utf-8")
        manifest = json.loads((self.state / MANIFEST).read_text(encoding="utf-8"))
        manifest["retroarch"]["files"]["../outside.rmp"] = {"created": True, "hash": None}
        (self.state / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        code, out = self.cli("restore", "--force")
        self.assertEqual(code, 1)
        self.assertIn("outside the config root", out)
        self.assertTrue(outside.exists())

    def test_nothing_to_restore(self):
        self.assertEqual(self.cli("restore"), (0, "Nothing to restore: map-helper hasn't written any file.\n"))


if __name__ == "__main__":
    unittest.main()
