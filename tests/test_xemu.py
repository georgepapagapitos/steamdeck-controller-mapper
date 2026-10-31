"""xemu (original Xbox): which Steam slot is in which Xbox port (docs/adapters/xemu.md). GUIDs are computed here
from the repo's device captures, never copied from a Deck."""

import contextlib
import io
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper import cli, esde
from maphelper.adapters.xemu import XemuAdapter, is_steam_virtual, sdl_linux_guid
from maphelper.devices import InputDevice, parse_proc_input_devices

DEVICES = REPO / "tests" / "fixtures" / "devices" / "all-three-reordered"   # Switch Pro, 8BitDo, DualSense, Deck


def pad(name: str) -> InputDevice:
    return InputDevice(name=name, bus="0003", vendor="28de", product="11ff", version="0001", phys="", uniq="",
                       handlers=())


class GuidTest(unittest.TestCase):
    def test_sdl_guid_of_a_steam_virtual_pad(self):
        # SDL_CreateJoystickGUID with CRC-16/ARC of the name (docs/adapters/xemu.md, the worked example).
        self.assertEqual(sdl_linux_guid(pad("Microsoft X-Box 360 pad 0")), "030079f6de280000ff11000001000000")
        self.assertNotEqual(sdl_linux_guid(pad("Microsoft X-Box 360 pad 1")), sdl_linux_guid(pad("Microsoft X-Box 360 pad 0")))
        self.assertTrue(is_steam_virtual("'030079f6de280000ff11000001000000'"))
        self.assertFalse(is_steam_virtual("keyboard"))
        self.assertFalse(is_steam_virtual("030000005e0400008e02000014010000"))   # an Xbox 360 pad SDL opened itself

    def test_es_de_runs_it(self):
        self.assertEqual(esde.classify("%INJECT%=%BASENAME%.esprefix %EMULATOR_XEMU% -dvd_path %ROM%"), ("xemu", None))
        self.assertEqual(esde.classify("/home/deck/.local/share/flatpak/exports/bin/app.xemu.xemu -dvd_path x.iso"),
                         ("xemu", None))
        self.assertEqual(esde.commands("xbox", root=Path("/nonexistent"))[0][0], "xemu (Standalone)")


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "xemu"
        self.root.mkdir()
        virtual = [d for d in parse_proc_input_devices((DEVICES / "proc-bus-input-devices").read_text(encoding="utf-8"))
                   if d.vendor == "28de" and d.product == "11ff"]
        self.guids = {d.name: sdl_linux_guid(d) for d in virtual}
        self.assertGreaterEqual(len(self.guids), 3)
        slots = sorted(self.guids.values())
        # As xemu leaves it: four slots in the wrong order, one stale, the 7-entry mapping array, a token.
        self.toml = (
            "[general]\nshow_welcome = false\nuser_token = 'not-a-real-token'\n\n"
            "[input]\ngamepad_mappings = [\n"
            + "".join(f"    {{ gamepad_id = '{g}'}},\n" for g in slots)
            + "    ]\n\n[input.bindings]\n"
            f"port1_driver = 'usb-xbox-gamepad'\nport1 = '{slots[-1]}'\n"
            f"port2 = '{slots[0]}'\nport3 = 'keyboard'\nport4 = '{sdl_linux_guid(pad('Microsoft X-Box 360 pad 9'))}'\n")
        (self.root / "xemu.toml").write_text(self.toml, encoding="utf-8")

    def apply(self, *extra) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["apply", "--emulator", "xemu", "--system", "xbox", "--config-root", str(self.root),
                             "--proc-file", str(DEVICES / "proc-bus-input-devices"),
                             "--virtual-info", str(DEVICES / "virtualgamepadinfo.txt"), "--ignore-devices", "",
                             "--sys-root", str(self.tmp), "--policy", "steam-order", "--rules", str(self.tmp / "none"),
                             "--state-dir", str(self.tmp / "state"), *extra])
        self.assertEqual(code, 0, out.getvalue())
        return out.getvalue()

    def test_ports_follow_the_players_and_nothing_else_changes(self):
        self.apply("--write")
        text = (self.root / "xemu.toml").read_text(encoding="utf-8")
        doc = tomllib.loads(text)
        ports = doc["input"]["bindings"]
        # Player K = Steam slot K-1 (steam-order) = the virtual pad named "... pad K-1".
        for k in (1, 2, 3):
            self.assertEqual(ports[f"port{k}"], self.guids[f"Microsoft X-Box 360 pad {k - 1}"], k)
        self.assertIn(ports["port4"], (self.guids.get("Microsoft X-Box 360 pad 3"), ""))
        # Everything but the port lines is byte for byte what it was.
        keep = lambda t: [l for l in t.splitlines() if not l.startswith("port") or l.startswith("port1_driver")]
        self.assertEqual(keep(text), keep(self.toml))
        self.assertEqual(doc["general"]["user_token"], "not-a-real-token")

    def test_the_keyboard_and_foreign_pads_keep_their_port(self):
        # With only one player the other ports are cleared only where they name a Steam virtual pad.
        one = self.tmp / "p.json"
        one.write_text('{"order": ["nintendo.switch-pro"]}', encoding="utf-8")
        foreign = "030000005e0400008e02000014010000"
        (self.root / "xemu.toml").write_text(self.toml.replace("port3 = 'keyboard'", f"port3 = '{foreign}'"),
                                             encoding="utf-8")
        adapter = XemuAdapter()
        out = adapter.render({1: None}, devices={1: self.guids["Microsoft X-Box 360 pad 0"]},
                             current=lambda f, s, k: tomllib.loads((self.root / f).read_text(encoding="utf-8"))
                             ["input"]["bindings"].get(k))
        patches = {p.key: p.value for p in out.patches}
        self.assertEqual(patches["port1"], f"'{self.guids['Microsoft X-Box 360 pad 0']}'")
        self.assertEqual(patches["port2"], "''")
        self.assertNotIn("port3", patches)            # a pad Steam doesn't virtualise
        self.assertEqual(patches["port4"], "''")      # a stale Steam slot

    def test_show_gives_the_default_layout_and_back_start(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["show", "--emulator", "xemu", "--system", "xbox", "--config-root", str(self.root),
                      "--proc-file", str(DEVICES / "proc-bus-input-devices"),
                      "--virtual-info", str(DEVICES / "virtualgamepadinfo.txt"), "--ignore-devices", "",
                      "--sys-root", str(self.tmp), "--policy", "steam-order", "--rules", str(self.tmp / "none"),
                      "--state-dir", str(self.tmp / "state"), "--json"])
        import json
        doc = json.loads(out.getvalue())
        p1 = doc["players"][0]
        rows = {r["input"]: [d["label"] for d in r["drives"]] for r in p1["inputs"]}
        self.assertEqual((rows["l1"], rows["r1"], rows["select"]), (["WHITE"], ["BLACK"], ["BACK"]))
        self.assertEqual(len(rows["face_south"]), 1)
        self.assertEqual([h["target"] for h in p1["hotkeys"]], ["hotkey.menu"])


if __name__ == "__main__":
    unittest.main()
