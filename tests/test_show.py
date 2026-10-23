"""map-helper show and $STATE/last-launch.json (docs/08 "The data: map-helper show and $STATE/last-launch.json")."""

import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import REPO
from maphelper import cli, mhrun, show

FIXTURES = REPO / "tests" / "fixtures"
DEVICES = FIXTURES / "devices" / "all-three-reordered"   # Switch Pro, 8BitDo Ultimate 2, DualSense, Deck
GOLDEN = REPO / "tests" / "golden" / "show"
OCARINA = "Legend of Zelda, The - Ocarina of Time (USA) (Rev 2)"
MAC = re.compile(r"(?i)\b[0-9a-f]{2}(:[0-9a-f]{2}){5}\b")


def run_cli(argv) -> tuple:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"

    def probe(self):
        return ["--proc-file", str(DEVICES / "proc-bus-input-devices"),
                "--virtual-info", str(DEVICES / "virtualgamepadinfo.txt"), "--ignore-devices", "",
                "--sys-root", str(self.tmp), "--policy", "steam-order"]

    def n64_rules(self) -> Path:
        rules = self.tmp / "rules"
        rules.mkdir()
        for f in REPO.glob("examples/1[01]-*.json"):
            shutil.copy(f, rules)
        return rules

    def show(self, *argv) -> dict:
        code, out = run_cli(["show", *argv, *self.probe(), "--state-dir", str(self.state), "--json"])
        self.assertEqual(code, 0)
        return json.loads(out)

    def assert_no_device_ids(self, text: str):
        """No MAC-shaped string, `uniq` or Steam handle from the capture (compared, never printed)."""
        self.assertIsNone(MAC.search(text), "a MAC-shaped string")
        proc = (DEVICES / "proc-bus-input-devices").read_text(encoding="utf-8")
        info = (DEVICES / "virtualgamepadinfo.txt").read_text(encoding="utf-8")
        secrets = [v for v in re.findall(r"^U: Uniq=(.+)$", proc, re.M) if v.strip()]
        for handle in re.findall(r"^handle=0x([0-9a-fA-F]+)$", info, re.M):
            secrets += [handle, handle.lstrip("0"), str(int(handle, 16))]
        self.assertTrue(secrets)
        leaked = [s for s in secrets if len(s) >= 6 and s.lower() in text.lower()]
        self.assertEqual(len(leaked), 0, "a uniq or handle value is in the output")


def row(player: dict, name: str) -> dict:
    return next(r for r in player["inputs"] if r["input"] == name)


class N64Test(Base):
    """RetroArch, Mupen64Plus-Next, the captured config, examples/10 + 11 only, four pads."""

    def doc(self):
        doc = self.show("--emulator", "retroarch", "--core", "mupen64plus_next", "--system", "n64", "--game", OCARINA,
                        "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt"), "--rules", str(self.n64_rules()))
        doc["launch"].update(ts="2026-10-23T10:55:49", ms=0)       # the only parts that change between runs
        return doc

    def test_golden(self):
        text = json.dumps(self.doc(), indent=2, ensure_ascii=False) + "\n"
        path = GOLDEN / "n64-ocarina.json"
        if os.environ.get("UPDATE_GOLDEN"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_effective_mapping(self):
        doc = self.doc()
        self.assertEqual(doc["schema"], 1)
        self.assertEqual((doc["launch"]["system_name"], doc["launch"]["outcome"]), ("Nintendo 64", "changed"))
        self.assertEqual([p["pad"]["model"] for p in doc["players"]],
                         ["nintendo.switch-pro", "8bitdo.ultimate2", "sony.dualsense", "valve.steamdeck"])
        dualsense = doc["players"][2]
        self.assertEqual(dualsense["pad"]["shape"], "playstation")
        south, east = row(dualsense, "face_south"), row(dualsense, "face_east")
        self.assertEqual(south["glyph"], "✕")
        self.assertEqual(south["drives"], [{"target": "n64.standard.a", "label": "A",
                                            "source": {"kind": "emulator", "detail": "Mupen64Plus-Next default"}}])
        self.assertEqual(east["drives"][0]["target"], "n64.standard.c_down")
        self.assertEqual(east["drives"][0]["source"]["kind"], "rule")
        self.assertEqual(east["drives"][0]["source"]["rule_id"], "user.any.n64.layout-live-faces")
        self.assertEqual(east["drives"][0]["source"]["scope"], "all Nintendo 64 games, any pad")
        # A Switch Pro's south button is the one marked B, and it still gives N64 A (positional).
        self.assertEqual(row(doc["players"][0], "face_south")["glyph"], "B")
        self.assertEqual(row(doc["players"][0], "face_south")["drives"][0]["target"], "n64.standard.a")

    def test_hotkey_note_and_steam_only_paddles(self):
        doc = self.doc()
        select = row(doc["players"][0], "select")
        self.assertEqual(select["drives"], [])
        self.assertIn("hotkey button", select["note"])
        self.assertEqual(select["note_source"]["kind"], "emudeck")
        self.assertNotIn("note", row(doc["players"][1], "select"))       # hotkeys are player 1's
        u2 = doc["players"][1]
        paddles = [r for r in u2["inputs"] if r["input"].startswith("paddle")]
        self.assertEqual([r["input"] for r in paddles], ["paddle1", "paddle2"])
        self.assertTrue(all(r["steam_only"] and r["drives"] == [] for r in paddles))
        deck = doc["players"][3]
        self.assertEqual(deck["pad"]["shape"], "deck")
        self.assertEqual([r["glyph"] for r in deck["inputs"] if r.get("steam_only")], ["R4", "L4", "R5", "L5"])

    def test_options(self):
        options = {o["key"]: o for o in self.doc()["players"][0]["options"]}
        self.assertEqual((options["pak"]["value"], options["pak"]["label"]), ("rumble", "Rumble pak"))
        self.assertEqual(options["pak"]["source"]["rule_id"], "user.any.n64.stick-rumble")
        self.assertEqual(options["deadzones.ls"]["value"], 0.05)

    def test_without_rules_the_core_and_its_options_file_decide(self):
        empty = self.tmp / "none"
        empty.mkdir()
        doc = self.show("--emulator", "retroarch", "--system", "n64", "--core", "mupen64plus_next",
                        "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt"), "--rules", str(empty))
        player = doc["players"][0]
        self.assertEqual(row(player, "face_east")["drives"], [])       # the core reads RetroPad A only with R2 held
        self.assertIn("C-button modifier", row(player, "r2")["note"])
        options = {o["key"]: o for o in player["options"]}
        self.assertEqual(options["pak"]["value"], "memory")
        self.assertEqual(options["pak"]["source"], {"kind": "emulator", "detail": "Mupen64Plus-Next.opt"})
        self.assertEqual(doc["launch"]["outcome"], "no-changes")

    def test_no_device_ids_in_json_or_text(self):
        argv = ["show", "--emulator", "retroarch", "--core", "mupen64plus_next", "--system", "n64", "--game", OCARINA,
                "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt"), "--rules", str(self.n64_rules()),
                *self.probe(), "--state-dir", str(self.state)]
        for extra in ([], ["--json"]):
            code, out = run_cli(argv + extra)
            self.assertEqual(code, 0)
            self.assert_no_device_ids(out)
        self.assertIn("C▼", out)


class MultiSystemCoreTest(Base):
    def test_only_the_launched_systems_targets(self):
        # Flycast's descriptor lists Dreamcast, Naomi and Atomiswave targets; a Dreamcast launch must show Dreamcast's
        # only (seen on a Deck: every button "drove" three targets and the warnings filled the screen).
        doc = self.show("--emulator", "retroarch", "--core", "flycast", "--system", "dreamcast",
                        "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt"), "--rules", str(self.tmp / "none"))
        targets = {d["target"] for p in doc["players"] for i in p["inputs"] for d in i["drives"]}
        self.assertTrue(targets)
        self.assertTrue(all(t.startswith("dreamcast.") for t in targets), sorted(targets))
        self.assertEqual(doc["warnings"], [])


class DolphinTest(Base):
    def test_gc_pads_read_back_through_the_token_table(self):
        doc = self.show("--emulator", "dolphin", "--system", "gc",
                        "--config-root", str(FIXTURES / "dolphin" / "dualsense-bt"), "--rules", str(REPO / "examples"))
        p1 = doc["players"][0]
        self.assertEqual(p1["pad"]["emulator_port"], 1)
        gc = lambda name: [d["target"] for d in row(p1, name)["drives"]]
        self.assertEqual(gc("face_south"), ["gc.standard.a"])            # `Button S` in GCPadNew.ini
        self.assertEqual(gc("ls"), ["gc.standard.main_x", "gc.standard.main_y"])   # EmuDeck's legacy `Axis 0-`...
        self.assertEqual(gc("select"), ["gc.standard.z"])                # Z = `Shoulder R`|Back
        self.assertEqual(gc("l2"), ["gc.standard.l_digital", "gc.standard.l_analog"])
        self.assertEqual(row(p1, "face_south")["drives"][0]["source"], {"kind": "emulator", "detail": "GCPadNew.ini"})
        # The 8BitDo brand rule moves GC A to the south button; the live X stays on east: a clash, and said so.
        u2 = doc["players"][1]
        self.assertEqual(row(u2, "face_south")["drives"][0]["source"]["kind"], "rule")
        self.assertIn("player 2: face_east drives several inputs: gc.standard.a, gc.standard.x", doc["warnings"])
        self.assertNotIn("l2 drives several", " ".join(doc["warnings"]))  # L and L-Analog may share (layout)
        options = {o["key"]: o["value"] for o in p1["options"]}
        self.assertEqual(options, {"rumble.enabled": True, "deadzones.ls": 0.0, "deadzones.rs": 0.0})


class LastLaunchTest(Base):
    def mh_run(self, *argv):
        calls = []
        code = mhrun.main(["--state-dir", str(self.state), "--rules", str(REPO / "examples"), *self.probe(), *argv],
                          exec_fn=lambda f, a: calls.append(a))
        self.assertEqual(code, 0)
        return calls

    def last(self) -> dict:
        return json.loads((self.state / show.LAST).read_text(encoding="utf-8"))

    def copy(self, emulator: str) -> Path:
        root = self.tmp / emulator
        shutil.copytree(FIXTURES / emulator / "dualsense-bt", root)
        return root

    def test_wrap_writes_the_full_document(self):
        command = ["retroarch.sh", "-L", "snes9x_libretro.so", "/r/roms/snes/Super Metroid (USA).sfc"]
        self.assertEqual(self.mh_run("--emulator", "retroarch", "--config-root", str(self.copy("retroarch")), "--",
                                     *command), [command])
        doc = self.last()
        self.assertEqual({k: doc["launch"][k] for k in ("mode", "emulator", "core", "system", "game", "outcome")},
                         {"mode": "wrap", "emulator": "retroarch", "core": "snes9x", "system": "snes",
                          "game": "Super Metroid (USA)", "outcome": "changed"})
        self.assertEqual(len(doc["players"]), 4)
        self.assertEqual(doc["policy"]["name"], "steam-order")
        self.assertIn("show_ms=", (self.state / "logs" / "launch.log").read_text(encoding="utf-8"))
        self.assert_no_device_ids((self.state / show.LAST).read_text(encoding="utf-8"))

    def test_es_de_mode(self):
        (self.tmp / "ES-DE" / "gamelists").mkdir(parents=True)
        self.mh_run("--hook", "--config-root", str(self.copy("retroarch")), "--es-de-root", str(self.tmp / "ES-DE"),
                    "--es-de", "/r/roms/snes/Super\\ Metroid\\ \\(USA\\).sfc", "Super Metroid", "snes",
                    "Super Nintendo Entertainment System")
        doc = self.last()
        self.assertEqual((doc["launch"]["mode"], doc["launch"]["system_name"]), ("es-de", "Super Nintendo / Super Famicom"))
        self.assertEqual(row(doc["players"][0], "face_south")["drives"][0]["target"], "snes.standard.b")

    def test_skipped(self):
        self.mh_run("--hook", "--emulator", "retroarch", "--core", "snes9x", "--config-root", str(self.tmp / "missing"),
                    "--rom", "/r/roms/snes/a.sfc")
        doc = self.last()
        self.assertEqual(doc["launch"]["outcome"], "skipped")
        self.assertIn("no config at", doc["launch"]["detail"])
        self.assertEqual(doc["players"], [])

    def test_error_and_a_broken_show_never_stop_the_launch(self):
        self.mh_run("--emulator", "nope", "--", "x")
        self.assertEqual(self.last()["launch"]["outcome"], "error")
        root = self.copy("retroarch")
        with mock.patch.object(show, "document", side_effect=RuntimeError("boom")):
            calls = self.mh_run("--emulator", "retroarch", "--config-root", str(root), "--", "retroarch.sh", "-L",
                                "snes9x_libretro.so", "/r/roms/snes/a.sfc")
        self.assertEqual(len(calls), 1)
        log = (self.state / "logs" / "launch.log").read_text(encoding="utf-8")
        self.assertIn("show_error=RuntimeError: boom", log)
        self.assertIn("changed: ", log.splitlines()[-1])               # the mappings were still written
        self.assertEqual(self.last()["launch"]["outcome"], "changed")
        self.assertEqual(self.last()["players"], [])

    def test_show_last_round_trip(self):
        code, out = run_cli(["show", "--last", "--state-dir", str(self.state)])
        self.assertEqual(code, 0)
        self.assertIn("No launch recorded yet", out)
        self.mh_run("--emulator", "retroarch", "--config-root", str(self.copy("retroarch")), "--", "retroarch.sh",
                    "-L", "snes9x_libretro.so", "/r/roms/snes/a.sfc")
        code, out = run_cli(["show", "--last", "--json", "--state-dir", str(self.state)])
        self.assertEqual(json.loads(out), self.last())
        code, out = run_cli(["show", "--last", "--state-dir", str(self.state)])
        self.assertIn("Player 1: Nintendo Switch Pro Controller", out)
        self.assertEqual([p for p in self.state.iterdir() if p.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
