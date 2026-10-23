"""A rule that's gone stops counting (core/maphelper/baseline.py), and a game rule stays in its game.

Found on the owner's Deck (2026-10-23): a Smash-only swap saved from the plugin was written into RetroArch's core
remap, so every N64 game got it, and taking the rule out left the swap in the file.
"""

import json
import shutil
import unittest
from pathlib import Path

from tests.test_show import FIXTURES, OCARINA, Base, run_cli
from maphelper.writer import load_manifest

MARIO_KART = "Mario Kart 64 (USA)"
CORE_RMP = Path("config/remaps/Mupen64Plus-Next/Mupen64Plus-Next.rmp")


def rule(rule_id, content, bindings):
    return {"schema_version": 1, "id": rule_id, "applies_to": {"controller": {"level": "any"}, "content": content},
            "bindings": bindings}


SWAP = {"n64.standard.a": {"input": "face_west"}, "n64.standard.b": {"input": "face_south"}}
OCARINA_ONLY = {"level": "game", "system": "n64", "game_id": OCARINA}
ALL_N64 = {"level": "system", "system": "n64"}


class BaselineTest(Base):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "retroarch"
        shutil.copytree(FIXTURES / "retroarch" / "dualsense-bt", self.root)
        self.rules = self.tmp / "rules"
        self.rules.mkdir()

    def put(self, *docs):
        for f in self.rules.glob("*.json"):
            f.unlink()
        for doc in docs:
            (self.rules / f"{doc['id']}.json").write_text(json.dumps(doc), encoding="utf-8")

    def launch(self, game):
        code, out = run_cli(["apply", "--emulator", "retroarch", "--core", "mupen64plus_next", "--system", "n64",
                             "--game", game, "--config-root", str(self.root), "--rules", str(self.rules), "--write",
                             "--state-dir", str(self.state), *self.probe()])
        self.assertEqual(code, 0, out)

    def game_rmp(self, game):
        return self.root / "config/remaps/Mupen64Plus-Next" / f"{game}.rmp"

    def south_drives(self, game, player=3):
        """What the DualSense's south button (✕) does in a game, as show reads the config after this launch."""
        code, out = run_cli(["show", "--emulator", "retroarch", "--core", "mupen64plus_next", "--system", "n64",
                             "--game", game, "--config-root", str(self.root), "--rules", str(self.rules),
                             "--state-dir", str(self.state), *self.probe(), "--json"])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        row = next(r for r in doc["players"][player - 1]["inputs"] if r["input"] == "face_south")
        return [d["label"] for d in row["drives"]]

    def test_a_game_rule_goes_into_the_games_remap_only(self):
        self.put(rule("game-swap", OCARINA_ONLY, SWAP))
        self.launch(OCARINA)
        self.assertTrue(self.game_rmp(OCARINA).is_file())
        self.assertFalse((self.root / CORE_RMP).exists())
        self.assertEqual(self.south_drives(OCARINA), ["B"])
        # Another N64 game: RetroArch loads no game remap for it, and the core remap was never written.
        self.launch(MARIO_KART)
        self.assertFalse((self.root / CORE_RMP).exists())
        self.assertEqual(self.south_drives(MARIO_KART), ["A"])
        self.assertTrue(self.game_rmp(OCARINA).is_file())         # Ocarina keeps its own

    def test_taking_the_rule_out_deletes_the_game_remap_it_made(self):
        self.put(rule("game-swap", OCARINA_ONLY, SWAP))
        self.launch(OCARINA)
        self.put()
        self.launch(OCARINA)
        self.assertFalse(self.game_rmp(OCARINA).exists())
        self.assertEqual(self.south_drives(OCARINA), ["A"])
        files = load_manifest(self.state)["retroarch"]["files"]
        self.assertNotIn(str(self.game_rmp(OCARINA).relative_to(self.root)), files)

    def test_the_decks_state_moves_into_the_game_remap(self):
        # What the owner's Deck had: the swap in a core remap map-helper created (here from a system rule), then
        # the rule is a game rule. The core remap goes, the game's has the swap.
        self.put(rule("swap", ALL_N64, SWAP))
        self.launch(OCARINA)
        self.assertTrue((self.root / CORE_RMP).is_file())
        self.put(rule("game-swap", OCARINA_ONLY, SWAP))
        self.launch(OCARINA)
        self.assertFalse((self.root / CORE_RMP).exists())
        self.assertTrue(self.game_rmp(OCARINA).is_file())
        self.assertEqual(self.south_drives(OCARINA), ["B"])
        self.assertEqual(self.south_drives(MARIO_KART), ["A"])

    def test_retroarchs_save_on_exit_keeps_a_created_remap_ours(self):
        # remap_save_on_exit rewrites the loaded .rmp at quit, normalised (docs/adapters/retroarch.md): that's not
        # someone else's edit, so taking the rule out still removes the file.
        self.put(rule("game-swap", OCARINA_ONLY, SWAP))
        self.launch(OCARINA)
        rmp = self.game_rmp(OCARINA)
        rmp.write_text(rmp.read_text(encoding="utf-8").replace(" = ", "=") + 'input_libretro_device_p1 = "1"\n',
                       encoding="utf-8")
        self.put()
        self.launch(OCARINA)
        self.assertFalse(rmp.exists())

    def hotkey(self, value):
        cfg = (self.root / "retroarch.cfg").read_text(encoding="utf-8")
        line = next(l for l in cfg.splitlines() if l.startswith("input_toggle_fast_forward_btn ="))
        return line.split("=", 1)[1].strip().strip('"') if value is None else line

    def test_a_key_in_an_existing_file_goes_back_when_its_rule_is_gone(self):
        before = (self.root / "retroarch.cfg").read_text(encoding="utf-8")
        was = self.hotkey(None)
        self.put(rule("ff", {"level": "global"}, {"hotkey.fast_forward": {"chord": ["select", "r1"]}}))
        self.launch(OCARINA)
        self.assertNotEqual(self.hotkey(None), was)
        self.put()
        self.launch(OCARINA)
        self.assertEqual(self.hotkey(None), was)
        after = (self.root / "retroarch.cfg").read_text(encoding="utf-8")
        hotkeys = lambda text: [l for l in text.splitlines() if l.startswith("input_") and "_btn" in l]
        self.assertEqual(hotkeys(after), hotkeys(before))

    def test_a_key_someone_changed_since_is_left_alone(self):
        self.put(rule("ff", {"level": "global"}, {"hotkey.fast_forward": {"chord": ["select", "r1"]}}))
        self.launch(OCARINA)
        cfg = self.root / "retroarch.cfg"
        text = cfg.read_text(encoding="utf-8")
        cfg.write_text(text.replace(self.hotkey("line"), 'input_toggle_fast_forward_btn = "7"'), encoding="utf-8")
        self.put()
        self.launch(OCARINA)
        self.assertEqual(self.hotkey(None), "7")


if __name__ == "__main__":
    unittest.main()
