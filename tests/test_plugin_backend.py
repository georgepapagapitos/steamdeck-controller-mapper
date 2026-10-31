"""The Decky plugin's backend (decky/main.py): what it accepts from the UI and what it reads from disk. It runs
on the Deck inside Decky, so a stand-in `decky` module gives it a home, a data folder and a logger here."""

import asyncio
import importlib.util
import json
import logging
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

from tests.helpers import REPO


def load_backend(home: Path, runtime: Path):
    fake = types.ModuleType("decky")
    fake.DECKY_USER_HOME, fake.DECKY_PLUGIN_RUNTIME_DIR, fake.DECKY_USER = str(home), str(runtime), "deck"
    fake.logger = logging.getLogger("decky-test")
    fake.logger.addHandler(logging.NullHandler())
    fake.logger.propagate = False
    sys.modules["decky"] = fake
    spec = importlib.util.spec_from_file_location("map_helper_backend", REPO / "decky" / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home, self.runtime = self.tmp / "home", self.tmp / "runtime"
        self.home.mkdir()
        self.runtime.mkdir()
        self.main = load_backend(self.home, self.runtime)
        self.addCleanup(sys.modules.pop, "decky", None)
        self.plugin = self.main.Plugin()

    def call(self, name, *args):
        return asyncio.run(getattr(self.plugin, name)(*args))

    def test_steam_glyphs_take_plain_names_only(self):
        folder = self.home.joinpath(*self.main.GLYPH_DIR)
        folder.mkdir(parents=True)
        (folder / "xbox_lb.svg").write_text("<svg/>", encoding="utf-8")
        (self.home / "secret.svg").write_text("no", encoding="utf-8")
        self.assertEqual(self.call("get_steam_glyphs", ["xbox_lb", "missing"]), {"ok": True, "data": {"xbox_lb": "<svg/>"}})
        for bad in (["../secret"], ["xbox_lb/../../x"], "xbox_lb", ["x"] * 201, [3]):
            with self.subTest(bad):
                self.assertFalse(self.call("get_steam_glyphs", bad)["ok"])

    def test_controller_art_only_known_names(self):
        self.assertEqual(self.call("get_controller_art", "xboxone")["code"], "no-art")      # not on this "Deck"
        self.assertEqual(self.call("get_controller_art", "../../etc/passwd")["code"], "refused")

    def test_console_art_from_the_shipped_photos_and_the_data_folder(self):
        got = self.call("get_console_art", "snes", "standard")
        self.assertTrue(got["ok"])
        self.assertTrue(got["data"]["url"].startswith("data:image/"))
        self.assertEqual(got["data"]["edge"], {"l": 0.23, "r": 0.77})
        self.assertEqual(self.call("get_console_art", "psx", "dualshock")["ok"], True)        # <system>-<controller>
        self.assertEqual(self.call("get_console_art", "wiiu", "gamepad")["code"], "no-art")
        self.assertEqual(self.call("get_console_art", "../x", "standard")["code"], "refused")
        # A developer copy in the data folder, with no `edge`: the key is left out, never sent as null.
        dev = self.runtime / "consoles"
        dev.mkdir()
        shutil.copy(REPO / "decky" / "assets" / "consoles" / "nes.jpg", dev / "zz.jpg")
        (dev / "zz.json").write_text(json.dumps({"file": "zz.jpg", "width": 1, "height": 1, "spots": {}}),
                                     encoding="utf-8")
        got = self.call("get_console_art", "zz", "standard")
        self.assertTrue(got["ok"])
        self.assertNotIn("edge", got["data"])
        # A photo file that names something outside its folder is never read.
        (dev / "zz.json").write_text(json.dumps({"file": "../../home/secret.png", "width": 1, "height": 1}),
                                     encoding="utf-8")
        self.assertFalse(self.call("get_console_art", "zz", "standard")["ok"])

    def test_player_order_refuses_odd_input_before_running_anything(self):
        for bad in ("8bitdo.ultimate2", ["../x"], [3], ["a"] * 17):
            with self.subTest(bad):
                self.assertEqual(self.call("set_player_order", bad)["code"], "refused")
        self.assertEqual(self.call("set_player_order", ["sony.dualsense"])["code"], "not-installed")


    def test_health_keeps_only_what_stops_map_helper_working(self):
        findings = [{"severity": "error", "check": "launch-hooks", "message": "es-de: no game-start script"},
                    {"severity": "warning", "check": "launch-hooks", "message": "mh-run: the shim runs an old core"},
                    {"severity": "error", "check": "steam-input", "message": 'steam: "Disable Steam Input" is set'},
                    {"severity": "warning", "check": "steam-input", "message": "couldn't read localconfig.vdf"},
                    {"severity": "warning", "check": "retroarch-shadow", "message": "a game remap"},
                    {"severity": "info", "check": "emudeck-automap", "message": "AutoMap is on for Cemu"}]

        async def fake_core(*args, timeout=None):
            self.assertEqual(args, ("doctor", "--json"))
            return 0, json.dumps({"findings": findings}).encode(), b""

        self.main._run_core, self.main._entry = fake_core, lambda: __file__
        got = self.call("get_health")
        self.assertEqual([(p["check"], p["severity"]) for p in got["data"]["problems"]],
                         [("launch-hooks", "error"), ("launch-hooks", "warning"), ("steam-input", "error")])


if __name__ == "__main__":
    unittest.main()
