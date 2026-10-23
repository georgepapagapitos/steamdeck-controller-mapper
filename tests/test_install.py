"""self-install (docs/14 §6) into a temp home, the installed tree run the way the shim runs it, uninstall's part, and
finding the data in both layouts."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper import DATA, cli, install, setup

FIXTURES = REPO / "tests" / "fixtures"
DEVICES = FIXTURES / "devices" / "all-three-reordered"


def can_symlink(where: Path) -> bool:
    try:
        os.symlink("x", where / "link")
    except OSError:                                         # Windows without developer mode
        return False
    (where / "link").unlink()
    return True


def pythons() -> list:
    """sys.executable, and /usr/bin/python3 (the shims' Python) when it's there and new enough."""
    out = [sys.executable]
    system = "/usr/bin/python3"
    if os.path.exists(system) and subprocess.run(
            [system, "-I", "-c", "import sys; sys.exit(sys.version_info < (3, 11))"]).returncode == 0:
        out.append(system)
    return out


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        if not can_symlink(self.tmp):
            self.skipTest("no symlinks here")
        self.places = setup.Places(home=self.tmp / "home", proc_root=self.tmp)
        self.lib = self.places.lib

    def payload(self, name: str, readme: str = "") -> Path:
        """A payload laid out as tools/deck.sh ships it; `readme` makes it a different tree."""
        out = self.tmp / name
        out.mkdir()
        shutil.copy2(REPO / "core" / "mh_entry.py", out)
        shutil.copytree(REPO / "core" / "maphelper", out / "maphelper",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "data", out / "data")
        if readme:
            with open(out / "data" / "README.md", "a", encoding="utf-8") as f:
                f.write(readme)
        return out

    def record(self) -> dict:
        return json.loads((self.lib / "install.json").read_text(encoding="utf-8"))

    def versions(self) -> set:
        return {p.name for p in (self.lib / "versions").iterdir()}

    def test_fresh_install(self):
        version, changed = install.install(self.payload("a"), self.lib)
        self.assertTrue(changed)
        self.assertRegex(version, r"^\d+\.\d+\.\d+\+[0-9a-f]{8}$")
        self.assertEqual(os.readlink(self.lib / "current"), f"versions/{version}")
        self.assertTrue((self.lib / "current" / "mh_entry.py").is_file())
        self.assertTrue((self.lib / "current" / "data" / "controllers.json").is_file())
        record = self.record()
        self.assertEqual((record["version"], record["installed_by"], record["previous"]), (version, "cli", None))
        self.assertEqual(record["sha256"], install.tree_hash(install.payload(self.lib / "current")))
        self.assertTrue(version.endswith(record["sha256"][:8]))
        self.assertEqual(self.versions(), {version})

    def test_the_repo_and_its_payload_are_the_same_version(self):
        self.assertEqual(install.tree_hash(install.payload(REPO / "core")),
                         install.tree_hash(install.payload(self.payload("a"))))

    def test_reinstalling_the_same_version_changes_nothing(self):
        src = self.payload("a")
        version, _ = install.install(src, self.lib)
        before = (self.lib / "install.json").read_bytes()
        self.assertEqual(install.install(src, self.lib), (version, False))
        self.assertEqual((self.lib / "install.json").read_bytes(), before)
        self.assertEqual(self.versions(), {version})
        # From the installed tree itself, too (what `current/mh_entry.py self-install` does).
        self.assertEqual(install.install(self.lib / "current", self.lib), (version, False))

    def test_a_third_version_prunes_the_oldest(self):
        a, _ = install.install(self.payload("a"), self.lib)
        b, _ = install.install(self.payload("b", "b\n"), self.lib)
        self.assertEqual(self.versions(), {a, b})
        c, _ = install.install(self.payload("c", "c\n"), self.lib)
        self.assertEqual(self.versions(), {b, c})
        self.assertEqual(os.readlink(self.lib / "current"), f"versions/{c}")
        self.assertEqual(self.record()["previous"], b)
        install.install(self.payload("c2", "c\n"), self.lib)          # same tree again: b is still the previous
        self.assertEqual((self.versions(), self.record()["previous"]), ({b, c}, b))

    def test_a_damaged_version_is_replaced(self):
        version, _ = install.install(self.payload("a"), self.lib)
        (self.lib / "current" / "data" / "controllers.json").write_text("{}", encoding="utf-8")
        self.assertEqual(install.install(self.payload("a2"), self.lib), (version, True))
        self.assertEqual(self.versions(), {version})
        self.assertEqual(install.tree_hash(install.payload(self.lib / "current")), self.record()["sha256"])

    def test_refuses_a_current_that_isnt_a_symlink(self):
        (self.lib / "current").mkdir(parents=True)
        with self.assertRaises(install.InstallError):
            install.install(self.payload("a"), self.lib)

    def test_not_a_payload(self):
        with self.assertRaises(install.InstallError):
            install.install(self.tmp, self.lib)

    def test_installed_entry_runs_mh_run_from_the_installed_tree(self):
        install.install(self.payload("a"), self.lib)
        shutil.rmtree(self.tmp / "a")                               # nothing left to fall back on
        entry = self.lib / "current" / "mh_entry.py"
        config = self.tmp / "retroarch"
        shutil.copytree(FIXTURES / "retroarch" / "dualsense-bt", config)
        for python in pythons():
            with self.subTest(python=python):
                state = self.tmp / f"state-{len(python)}"
                run = subprocess.run(
                    [python, "-I", str(entry), "mh-run", "--hook", "--emulator", "retroarch", "--core", "snes9x",
                     "--rom", "/r/roms/snes/a.sfc", "--config-root", str(config), "--state-dir", str(state),
                     "--rules", str(REPO / "examples"), "--proc-file", str(DEVICES / "proc-bus-input-devices"),
                     "--virtual-info", str(DEVICES / "virtualgamepadinfo.txt"), "--ignore-devices", "",
                     "--sys-root", str(self.tmp), "--policy", "steam-order"],
                    capture_output=True, text=True, encoding="utf-8", cwd=str(self.tmp))
                self.assertEqual(run.returncode, 0, run.stderr)
                log = (state / "logs" / "launch.log").read_text(encoding="utf-8")
                self.assertIn("hook emulator=retroarch system=snes core=snes9x", log)
                self.assertRegex(log, r"(changed: |no changes)")

    def test_uninstall_removes_the_install_and_only_with_its_record(self):
        version, _ = install.install(self.payload("a"), self.lib)
        (self.lib / "notes.txt").write_text("mine", encoding="utf-8")
        report = setup.uninstall(self.places)
        self.assertIn(f"would remove map-helper {version}", setup.render(report))
        self.assertTrue((self.lib / "current").is_symlink())
        setup.uninstall(self.places, write=True)
        self.assertEqual([p.name for p in self.lib.iterdir()], ["notes.txt"])
        # No install.json: not ours, and nothing is reported.
        (self.lib / "versions").mkdir()
        report = setup.uninstall(self.places, write=True)
        self.assertTrue((self.lib / "versions").is_dir())
        self.assertEqual([c.part for c in report.changes], ["setup"])

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["self-install", "--from", str(self.payload("a")), "--home", str(self.places.home)])
        self.assertEqual(code, 0)
        self.assertIn("installed map-helper 0.", out.getvalue())
        self.assertIn(f"{self.places.entry} setup", out.getvalue())


class DataTest(unittest.TestCase):
    def test_repo_layout(self):
        self.assertEqual(DATA, REPO / "data")
        self.assertEqual(install.payload(REPO / "core")["data"], REPO / "data")

    def test_installed_layout(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copy2(REPO / "core" / "mh_entry.py", tmp)
        shutil.copytree(REPO / "core" / "maphelper", tmp / "maphelper", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "data" / "frontends", tmp / "data" / "frontends")
        run = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                              "import maphelper; print(maphelper.DATA)", str(tmp)],
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(Path(run.stdout.strip()), (tmp / "data").resolve(), run.stderr)
        self.assertEqual(install.payload(tmp)["data"], (tmp / "data").resolve())
