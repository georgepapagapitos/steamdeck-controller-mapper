"""mh-run: wrap and hook mode against captured configs, and every way it must fail open (docs/07 "mh-run behaviour")."""

import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import REPO
from maphelper import esde, mhrun, pipeline, setup
from maphelper.launch import dolphin_disc, parse_dolphin, parse_pcsx2, parse_retroarch, system_from_path
from maphelper.writer import Patch, apply_patches

FIXTURES = REPO / "tests" / "fixtures"
DEVICES = FIXTURES / "devices" / "all-three-reordered"   # Switch Pro, 8BitDo, DualSense, Deck


def disc(path: Path, game: bytes, wii: bool = False, container: bytes = b"") -> Path:
    """A made-up disc image: just the header Dolphin reads (DiscIO/Volume.cpp), optionally in a WIA/RVZ header."""
    header = game + b"\0" * (0x18 - len(game)) + struct.pack(">II", 0x5D1C9EA3 if wii else 0, 0 if wii else 0xC2339F3D)
    data = header + b"\0" * 0x40
    if container:
        data = container + b"\0" * (0x48 - len(container)) + b"\0" * 0x10 + data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def digest(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class Launch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.roots = {}
        for emulator, src in (("retroarch", "retroarch/dualsense-bt"), ("dolphin", "dolphin/dualsense-bt"),
                              ("pcsx2", "pcsx2/dualsense-bt")):
            shutil.copytree(FIXTURES / src, self.tmp / emulator)
            self.roots[emulator] = self.tmp / emulator
        self.state = self.tmp / "state"
        self.calls = []

    def probe(self, emulator=None):
        args = ["--state-dir", str(self.state), "--rules", str(REPO / "examples"),
                "--proc-file", str(DEVICES / "proc-bus-input-devices"),
                "--virtual-info", str(DEVICES / "virtualgamepadinfo.txt"), "--ignore-devices", "",
                "--sys-root", str(self.tmp), "--policy", "steam-order"]
        if emulator:
            args += ["--config-root", str(self.roots[emulator])]
        return args

    def run_mh(self, argv, **kw):
        return mhrun.main(argv, exec_fn=lambda f, a: self.calls.append((f, a)), **kw)

    def log(self) -> str:
        return (self.state / "logs" / "launch.log").read_text(encoding="utf-8")

    def configs(self) -> dict:
        return {e: digest(r) for e, r in self.roots.items()}


class WrapTest(Launch):
    def test_retroarch_applies_then_execs_the_command_unchanged(self):
        command = ["/home/deck/Emulation/tools/launchers/retroarch.sh", "-L",
                   "/home/deck/.var/app/org.libretro.RetroArch/config/retroarch/cores/snes9x_libretro.so",
                   "/home/deck/Emulation/roms/snes/Super Metroid (USA).sfc"]
        code = self.run_mh(["--emulator", "retroarch", *self.probe("retroarch"), "--", *command])
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, [(command[0], command)])
        self.assertIn("wrap emulator=retroarch system=snes core=snes9x game=Super Metroid (USA) players=4", self.log())
        self.assertIn("changed: ", self.log())
        self.assertTrue((self.roots["retroarch"] / "config/remaps/Snes9x/Snes9x.rmp").is_file())

    def test_the_log_names_each_players_model_and_how_old_steams_slots_are(self):
        # Steam seats pads at their first input in a game session; the log shows which order mh-run used and whether
        # the slot file had just been rewritten, to line up with Steam's console_log (docs/13 S1).
        self.run_mh(["--emulator", "retroarch", *self.probe("retroarch"), "--", "retroarch.sh", "-L",
                     "snes9x_libretro.so", "/r/roms/snes/a.sfc"])
        self.assertIn("players=4 order=nintendo.switch-pro,8bitdo.ultimate2,sony.dualsense,valve.steamdeck "
                      "slots_age=", self.log())

    def test_dolphin_reads_the_disc_header(self):
        rom = disc(self.tmp / "roms" / "gc" / "Melee.iso", b"GALE01")
        command = ["/home/deck/Emulation/tools/launchers/dolphin-emu.sh", "-b", "-e", str(rom)]
        self.run_mh(["--emulator", "dolphin", *self.probe("dolphin"), "--", *command])
        self.assertEqual(self.calls, [(command[0], command)])
        self.assertIn("system=gc game=GALE01 players=4", self.log())
        self.assertNotIn("error", self.log())

    def test_a_wii_disc_is_left_alone(self):
        # Dolphin's adapter renders GameCube pads only; a Wii game must not get GC bindings written over its config.
        rom = disc(self.tmp / "roms" / "gc" / "Wii Sports.rvz", b"RSPE01", wii=True, container=b"RVZ\x01")
        before = self.configs()
        self.run_mh(["--emulator", "dolphin", *self.probe("dolphin"), "--", "dolphin-emu.sh", "-b", "-e", str(rom)])
        self.assertEqual(self.configs(), before)
        self.assertIn("system=wii game=RSPE01", self.log())
        self.assertEqual(len(self.calls), 1)

    def test_pcsx2_with_legacy_single_quotes(self):
        command = ["/home/deck/Emulation/tools/launchers/pcsx2-qt.sh", "-batch", "-fullscreen", "-nogui",
                   "'/home/deck/Emulation/roms/ps2/Game.iso'"]
        self.run_mh(["--emulator", "pcsx2", *self.probe("pcsx2"), "--", *command])
        self.assertEqual(self.calls, [(command[0], command)])
        self.assertIn("wrap emulator=pcsx2 system=ps2 players=4", self.log())
        self.assertNotIn("error", self.log())

    def test_no_exec_leaves_the_command_to_the_shim(self):
        code = self.run_mh(["--no-exec", "--emulator", "retroarch", *self.probe("retroarch"), "--",
                            "retroarch.sh", "-L", "snes9x_libretro.so", "/r/roms/snes/a.sfc"])
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("changed: ", self.log())

    def test_a_missing_program_returns_127(self):
        def missing(f, a):
            raise FileNotFoundError(f)
        self.assertEqual(mhrun.main(["--emulator", "pcsx2", *self.probe("pcsx2"), "--", "/nope/pcsx2", "x.iso"],
                                    exec_fn=missing), 127)


class FailOpenTest(Launch):
    """Whatever goes wrong, the command still runs and no config is touched."""

    command = ["/x/retroarch.sh", "-L", "/c/snes9x_libretro.so", "/r/roms/snes/a.sfc"]

    def assert_launched_untouched(self, argv, before, expect):
        self.assertEqual(self.run_mh(argv), 0)
        self.assertEqual(self.calls, [(self.command[0], self.command)])
        self.assertEqual(self.configs(), before)
        self.assertIn(expect, self.log())
        self.assertEqual([p for p in self.tmp.rglob("*.mh-tmp")], [])

    def test_exception_in_resolve(self):
        before = self.configs()
        with mock.patch.object(pipeline.resolver, "resolve", side_effect=RuntimeError("boom")):
            self.assert_launched_untouched(["--emulator", "retroarch", *self.probe("retroarch"), "--", *self.command],
                                           before, "error: RuntimeError: boom")

    def test_unreadable_proc_file(self):
        before = self.configs()
        argv = ["--emulator", "retroarch", *self.probe("retroarch"), "--", *self.command]
        argv[argv.index("--proc-file") + 1] = str(self.tmp / "no-such-file")
        self.assert_launched_untouched(argv, before, "can't read the connected devices")

    def test_budget_exceeded(self):
        before = self.configs()
        ticks = iter(range(0, 10 ** 6, 300))            # every look at the clock is 300 ms later
        self.assertEqual(self.run_mh(["--emulator", "retroarch", *self.probe("retroarch"), "--", *self.command],
                                     clock=lambda: next(ticks) / 1000), 0)
        self.assertEqual(self.calls, [(self.command[0], self.command)])
        self.assertEqual(self.configs(), before)
        self.assertIn("error: BudgetExceeded", self.log())

    def test_watchdog(self):
        # A real clock and a 1 ms budget: the watchdog or a deadline check stops it, wherever it is.
        before = self.configs()
        self.run_mh(["--emulator", "retroarch", *self.probe("retroarch"), "--", *self.command], budget_ms=1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.configs(), before)
        self.assertIn("BudgetExceeded", self.log())
        self.assertEqual([p for p in self.tmp.rglob("*.mh-tmp")], [])

    def test_lock_held(self):
        before = self.configs()
        with mhrun.lock(self.state / "locks" / "retroarch.lock"):
            self.assert_launched_untouched(["--emulator", "retroarch", *self.probe("retroarch"), "--",
                                            *self.command], before, "skipped: another launch holds the lock")

    def test_missing_config(self):
        shutil.rmtree(self.roots["retroarch"])
        self.roots.pop("retroarch")
        self.assertEqual(self.run_mh(["--emulator", "retroarch", *self.probe(), "--config-root",
                                      str(self.tmp / "retroarch"), "--", *self.command]), 0)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("skipped: no config at", self.log())

    def test_bad_arguments(self):
        before = self.configs()
        self.assert_launched_untouched(["--emulator", "nope", "--frobnicate", "--state-dir", str(self.state), "--",
                                        *self.command], before,
                                       "error: ValueError: bad arguments")

    def test_unknown_core(self):
        before = self.configs()
        command = ["/x/retroarch.sh", "-L", "/c/puae_libretro.so", "/r/roms/amiga/a.adf"]
        self.run_mh(["--emulator", "retroarch", *self.probe("retroarch"), "--", *command])
        self.assertEqual(self.calls, [(command[0], command)])
        self.assertEqual(self.configs(), before)
        self.assertIn("skipped: no core descriptor for puae_libretro.so", self.log())

    def test_nothing_to_run(self):
        self.assertEqual(self.run_mh(["--emulator", "retroarch", *self.probe("retroarch")]), 0)
        self.assertEqual(self.calls, [])

    def test_gate_says_no(self):
        # The writer's two phases: a gate that says no after staging leaves every file as it was, no temp files.
        root = self.roots["dolphin"]
        before = digest(root)
        result = apply_patches(root, [Patch("GCPadNew.ini", "GCPad1", "Buttons/A", "`Nothing Real`")],
                               {"GCPadNew.ini": {"sections": "GCPad{n}", "keys": ["Buttons/*"]}},
                               state_dir=self.state, emulator="dolphin", gate=lambda: False)
        self.assertTrue(result.aborted)
        self.assertEqual(digest(root), before)
        self.assertFalse((self.state / "touched.json").exists())

    def test_backstop_term_aborts_before_the_gate_and_is_ignored_after(self):
        # The shim's `timeout -k 3 -s TERM 2`: before the gate TERM is a budget abort (nothing written); once the gate
        # says go, TERM can't cut the renames short.
        import signal
        saved = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, saved)
        budget = mhrun.Budget(0.0, 500, clock=lambda: 0.1)
        budget.arm()
        with self.assertRaises(mhrun.BudgetExceeded):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        self.assertTrue(budget.gate())
        self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_IGN)


class HookTest(Launch):
    def esde_root(self):
        root = self.tmp / "ES-DE"
        (root / "gamelists" / "gc").mkdir(parents=True)
        return root

    def test_es_de_snes_goes_to_retroarch_and_exits_0(self):
        rom = "/home/deck/Emulation/roms/snes/Super\\ Metroid\\ \\(USA\\).sfc"     # as ES-DE escapes it
        code = self.run_mh(["--hook", *self.probe(), "--config-root", str(self.roots["retroarch"]),
                            "--es-de-root", str(self.esde_root()),
                            "--es-de", rom, "Super Metroid", "snes", "Super Nintendo Entertainment System"])
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("es-de emulator=retroarch system=snes core=snes9x game=Super Metroid (USA)", self.log())
        self.assertIn("changed: ", self.log())

    def test_es_de_unknown_system_does_nothing(self):
        before = self.configs()
        code = self.run_mh(["--hook", *self.probe(), "--es-de-root", str(self.esde_root()),
                            "--es-de", "/r/roms/x68000/a.dim", "A", "x68000", "Sharp X68000"])
        self.assertEqual((code, self.calls), (0, []))
        self.assertEqual(self.configs(), before)
        self.assertIn("skipped: es-de system 'x68000'", self.log())

    def test_es_de_standalone_emulator_we_dont_manage(self):
        root = self.esde_root()
        (root / "gamelists" / "psx").mkdir()
        (root / "gamelists" / "psx" / "gamelist.xml").write_text(
            '<?xml version="1.0"?>\n<gameList />\n<alternativeEmulator><label>DuckStation (Standalone)</label>'
            '</alternativeEmulator>\n', encoding="utf-8")
        self.run_mh(["--hook", *self.probe(), "--es-de-root", str(root), "--es-de", "/r/roms/psx/a.chd", "A", "psx",
                     "Sony PlayStation"])
        self.assertIn("skipped: es-de runs 'DuckStation (Standalone)' for psx", self.log())

    def test_generic_hook(self):
        code = self.run_mh(["--hook", "--emulator", "retroarch", "--core", "snes9x", "--rom", "/r/roms/snes/a.sfc",
                            *self.probe("retroarch")])
        self.assertEqual((code, self.calls), (0, []))
        self.assertIn("hook emulator=retroarch system=snes core=snes9x game=a", self.log())


class EsdeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def gamelist(self, system, text):
        path = self.root / "gamelists" / system / "gamelist.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_default_is_the_first_command(self):
        # ES-DE's own default for gc is RetroArch's Dolphin core; EmuDeck's gamelist picks the standalone one.
        found = esde.launch("/r/roms/gc/a.iso", "gc", self.root)
        self.assertEqual((found.emulator, found.core_file, found.label), ("retroarch", "dolphin_libretro.so", "Dolphin"))

    def test_emudecks_system_choice(self):
        # ESDE_setEmu appends the label after the root element (emuDeckESDE.sh), which isn't well-formed XML.
        self.gamelist("gc", '<?xml version="1.0"?>\n<gameList>\n</gameList>\n'
                            '<alternativeEmulator><label>Dolphin (Standalone)</label></alternativeEmulator>\n')
        found = esde.launch("/r/roms/gc/a.iso", "gc", self.root)
        self.assertEqual((found.emulator, found.system), ("dolphin", "gc"))

    def test_per_game_choice_beats_the_systems(self):
        self.gamelist("snes", '<?xml version="1.0"?>\n<alternativeEmulator><label>Snes9x - Current</label>'
                              '</alternativeEmulator>\n<gameList>\n<game>\n<path>./Sub/A &amp; B.sfc</path>\n'
                              '<altemulator>bsnes</altemulator>\n</game>\n</gameList>\n')
        found = esde.launch("/r/roms/snes/Sub/A\\ \\&\\ B.sfc", "snes", self.root)
        self.assertEqual((found.label, found.core_file), ("bsnes", "bsnes_libretro.so"))   # no descriptor: mh-run skips
        self.assertEqual(esde.launch("/r/roms/snes/Other.sfc", "snes", self.root).emulator, "retroarch")

    def test_custom_system_replaces_the_bundled_one(self):
        custom = self.root / "custom_systems" / "es_systems.xml"
        custom.parent.mkdir(parents=True)
        custom.write_text('<?xml version="1.0"?>\n<systemList>\n<system>\n<name>snes</name>\n'
                          '<command label="Mine">%EMULATOR_RETROARCH% -L %CORE_RETROARCH%/mesen_libretro.so %ROM%'
                          '</command>\n</system>\n</systemList>\n', encoding="utf-8")
        self.assertEqual(esde.launch("/r/a.sfc", "snes", self.root).core_file, "mesen_libretro.so")

    def test_ps2_and_aliases(self):
        self.gamelist("ps2", '<alternativeEmulator><label>PCSX2 (Standalone)</label></alternativeEmulator>\n')
        self.assertEqual(esde.launch("/r/roms/ps2/a.iso", "ps2", self.root).emulator, "pcsx2")
        self.assertEqual(esde.launch("/r/roms/megadrive/a.md", "megadrive", self.root).system, "genesis")

    def test_unescape(self):
        self.assertEqual(esde.unescape_rom("/r/Zelda\\ \\(USA\\)\\ \\[\\!\\].zip"), Path("/r/Zelda (USA) [!].zip"))


class ArgsTest(unittest.TestCase):
    def test_retroarch_shapes(self):
        info = parse_retroarch(["/t/retroarch.sh", "-L", "/c/cores/genesis_plus_gx_libretro.so",
                                "/home/deck/Emulation/roms/megadrive/Sonic.md"])
        self.assertEqual((info.core_file, info.system, info.game), ("genesis_plus_gx_libretro.so", "genesis", "Sonic"))
        info = parse_retroarch(["flatpak", "run", "--branch=stable", "org.libretro.RetroArch", "--libretro=/c/mgba_libretro.so",
                                "'/r/roms/gbc/Zelda.gbc'"])
        self.assertEqual((info.core_file, str(info.rom), info.system), ("mgba_libretro.so", "/r/roms/gbc/Zelda.gbc", "gbc"))
        self.assertEqual(parse_retroarch(["ra", "-L", "x_libretro.so", "/r/a.zip#rom.sfc"]).game, "rom")

    def test_dolphin_shapes(self):
        self.assertEqual(str(parse_dolphin(["d", "-b", "-e", "'/r/x.iso'"]).rom), "/r/x.iso")
        self.assertEqual(str(parse_dolphin(["d", "--batch", "--exec=/r/x.iso"]).rom), "/r/x.iso")
        self.assertIsNone(parse_dolphin(["d"]).rom)

    def test_pcsx2_shapes(self):
        self.assertEqual(str(parse_pcsx2(["p", "-batch", "-fullscreen", "-nogui", "/r/a.chd"]).rom), "/r/a.chd")
        self.assertEqual(str(parse_pcsx2(["p", "-batch", "/r/a b.iso"]).rom), "/r/a b.iso")
        self.assertEqual(parse_pcsx2(["p"]).system, "ps2")

    def test_system_from_path(self):
        self.assertEqual(system_from_path(Path("/run/media/sd/Emulation/roms/sfc/a.sfc")), "snes")
        self.assertIsNone(system_from_path(Path("/home/deck/games/a.sfc")))

    def test_dolphin_disc_formats(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.assertEqual(dolphin_disc(disc(tmp / "a.iso", b"GALE01")), ("gc", "GALE01"))
        self.assertEqual(dolphin_disc(disc(tmp / "b.rvz", b"RSPE01", wii=True, container=b"RVZ\x01")),
                         ("wii", "RSPE01"))
        self.assertEqual(dolphin_disc(disc(tmp / "c.wia", b"GALE01", container=b"WIA\x01")), ("gc", "GALE01"))
        (tmp / "d.wbfs").write_bytes(b"WBFS" + b"\0" * 0x100)
        self.assertEqual(dolphin_disc(tmp / "d.wbfs"), ("wii", None))
        ciso = b"CISO" + struct.pack("<I", 0x200000) + b"\x01" + b"\0" * (0x8000 - 9)
        (tmp / "e.ciso").write_bytes(ciso + disc(tmp / "x", b"GALE01").read_bytes())
        self.assertEqual(dolphin_disc(tmp / "e.ciso"), ("gc", "GALE01"))
        (tmp / "f.gcz").write_bytes(struct.pack("<I", 0xB10BC001) + b"\0" * 0x60)
        self.assertEqual(dolphin_disc(tmp / "f.gcz"), (None, None))
        self.assertEqual(dolphin_disc(tmp / "missing.iso"), (None, None))


@unittest.skipUnless(shutil.which("sh") and os.name == "posix", "needs a POSIX sh")
class ShimTest(unittest.TestCase):
    """The shim runs the command whatever Python does (docs/14 §6)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def shim(self, entry, python):
        path = self.tmp / "mh-run"
        path.write_text(setup.shim_text(entry, python), encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_sh(self, *argv):
        return subprocess.run(["sh", *map(str, argv)], capture_output=True, text=True, timeout=30)

    def test_no_install_still_runs_the_command(self):
        out = self.run_sh(self.shim(self.tmp / "missing.py", "/usr/bin/python3"),
                          "--emulator", "dolphin", "--", "printf", "%s|", "a b", "'q'")
        self.assertEqual((out.returncode, out.stdout), (0, "a b|'q'|"))

    def test_a_failing_python_still_runs_the_command(self):
        entry = self.tmp / "mh_entry.py"
        entry.write_text("", encoding="utf-8")
        out = self.run_sh(self.shim(entry, shutil.which("false")), "--emulator", "x", "--", "printf", "ok")
        self.assertEqual(out.stdout, "ok")

    def test_real_entry_with_no_exec(self):
        out = self.run_sh(self.shim(REPO / "core" / "mh_entry.py", shutil.which("python3")), "--emulator", "nope",
                          "--state-dir", self.tmp / "state", "--", "printf", "ran")
        self.assertEqual(out.stdout, "ran")
        self.assertIn("bad arguments", (self.tmp / "state" / "logs" / "launch.log").read_text(encoding="utf-8"))

    def test_hook_exits_0_without_running_anything(self):
        out = self.run_sh(self.shim(self.tmp / "missing.py", "/usr/bin/python3"), "--hook", "--es-de", "--", "x",
                          "printf", "no")
        self.assertEqual((out.returncode, out.stdout), (0, ""))

    def test_es_de_script_always_exits_0(self):
        script = self.tmp / "map-helper.sh"
        script.write_text(setup.esde_script_text(self.tmp / "no-mh-run"), encoding="utf-8")
        self.assertEqual(self.run_sh(script, "/r/a.sfc", "A", "snes", "SNES").returncode, 0)
        script.write_text(setup.esde_script_text(Path(shutil.which("false"))), encoding="utf-8")
        self.assertEqual(self.run_sh(script, "/r/a.sfc", "A", "snes", "SNES").returncode, 0)


if __name__ == "__main__":
    unittest.main()
