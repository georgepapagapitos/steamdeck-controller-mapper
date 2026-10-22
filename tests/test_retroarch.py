import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper.adapters.retroarch import RetroArchAdapter
from maphelper.formats.ini import IniDocument
from maphelper.resolve import Choice, Resolution
from maphelper.writer import apply_patches

REAL = REPO / "tests" / "fixtures" / "retroarch" / "dualsense-bt"   # the owner's Deck, captured
REMAP = "config/remaps/Snes9x/Snes9x.rmp"


def resolution(**bindings) -> Resolution:
    """snes_standard_a="face_south" -> {"snes.standard.a": Choice({"input": "face_south"})}."""
    return Resolution(bindings={k.replace("_", "."): Choice({"input": v}, "user.test") for k, v in bindings.items()})


class RetroArchTest(unittest.TestCase):
    def setUp(self):
        self.adapter = RetroArchAdapter()
        self.snes9x = self.adapter.core_for("snes")
        self.root = Path(tempfile.mkdtemp()) / "retroarch"
        shutil.copytree(REAL, self.root)

    def current(self, file, section, key):
        path = self.root / file
        return IniDocument.parse(path.read_text(encoding="utf-8")).get(section, key) if path.exists() else None

    def render(self, players):
        rendered = self.adapter.render(players, self.snes9x, self.current)
        return {(p.file, p.key): p.value for p in rendered.patches}, rendered.warnings

    def test_confirm_swap_writes_both_directions(self):
        # Remaps aren't swaps: A on south needs btn_b -> A and btn_a -> B, or east would still press A.
        patches, warnings = self.render({1: resolution(snes_standard_a="face_south", snes_standard_b="face_east")})
        self.assertEqual(patches, {(REMAP, "input_player1_btn_b"): '"8"', (REMAP, "input_player1_btn_a"): '"0"'})
        self.assertEqual(warnings, [])

    def test_a_displaced_source_is_unmapped(self):
        patches, _ = self.render({1: resolution(snes_standard_a="face_south")})
        self.assertEqual(patches, {(REMAP, "input_player1_btn_b"): '"8"', (REMAP, "input_player1_btn_a"): '"-1"'})

    def test_live_remap_decides_what_is_displaced(self):
        # EmuDeck's abxy remap, enabled: A->B, B->A, X->Y, Y->X. A rule puts SNES B on west (RetroPad Y).
        shutil.copy(self.root / (REMAP + ".disabled"), self.root / REMAP)
        patches, _ = self.render({1: resolution(snes_standard_b="face_west")})
        # btn_a still sends B live, so it lets go; btn_b, btn_x keep their live (unclaimed) targets untouched.
        self.assertEqual(patches, {(REMAP, "input_player1_btn_y"): '"0"', (REMAP, "input_player1_btn_a"): '"-1"'})

    def test_each_player_gets_its_own_keys(self):
        patches, _ = self.render({1: resolution(snes_standard_a="face_south", snes_standard_b="face_east"),
                                  2: resolution()})
        self.assertTrue(all(key.startswith("input_player1_") for _, key in patches))
        patches, _ = self.render({2: resolution(snes_standard_a="face_south", snes_standard_b="face_east")})
        self.assertEqual(set(key for _, key in patches), {"input_player2_btn_b", "input_player2_btn_a"})

    def test_writes_only_the_core_remap(self):
        rendered = self.adapter.render({1: resolution(snes_standard_a="face_south", snes_standard_b="face_east")},
                                       self.snes9x, self.current)
        result = apply_patches(self.root, rendered.patches, self.adapter.managed_keys(self.snes9x))
        self.assertEqual((result.changed_files, result.rejected), ([REMAP], []))
        self.assertEqual((self.root / REMAP).read_text(encoding="utf-8"),
                         'input_player1_btn_b = "8"\ninput_player1_btn_a = "0"\n')
        self.assertTrue((self.root / (REMAP + ".disabled")).exists())   # EmuDeck's file is left alone

    def test_unremappable_inputs_warn(self):
        bindings = {"snes.standard.a": Choice({"input": "guide"}, "u"),
                    "snes.standard.b": Choice({"chord": ["select", "start"]}, "u")}
        patches, warnings = self.render({1: Resolution(bindings=bindings)})
        self.assertEqual(patches, {})
        self.assertEqual(len(warnings), 2)

    def test_checks_flag_what_would_hide_our_remap(self):
        self.assertEqual(self.adapter.check(self.root, self.snes9x, self.current), [])   # the owner's Deck: clean
        (self.root / "config/remaps/Snes9x/snes.rmp").write_text('input_player1_btn_a = "0"\n', encoding="utf-8")
        cfg = self.root / "retroarch.cfg"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace('auto_remaps_enable = "true"',
                                                               'auto_remaps_enable = "false"'), encoding="utf-8")
        warnings = self.adapter.check(self.root, self.snes9x, self.current)
        self.assertTrue(any("snes.rmp" in w for w in warnings))
        self.assertTrue(any("auto_remaps_enable" in w for w in warnings))

    def test_core_choice(self):
        self.assertEqual(self.adapter.core_for("snes")["core"], "Snes9x")
        self.assertEqual(self.adapter.core_for("nes", "Mesen")["core"], "Mesen")
        with self.assertRaises(ValueError):
            self.adapter.core_for("nes")            # Mesen and Nestopia both run it


if __name__ == "__main__":
    unittest.main()
