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

    def apply_both(self):
        self.cli("apply", "--emulator", "retroarch", "--system", "snes", "--config-root", str(self.ra),
                 "--player", "sony.dualsense", "--rules", str(REPO / "examples"), "--write")
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
