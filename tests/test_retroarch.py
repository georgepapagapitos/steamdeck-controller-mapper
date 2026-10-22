import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper.adapters.retroarch import RetroArchAdapter
from maphelper.devices import ControllerDB
from maphelper.formats.ini import IniDocument
from maphelper.model import Target
from maphelper.resolve import Choice, Resolution, resolve, set_by_rules
from maphelper.store import load_json, load_layouts, load_rules
from maphelper.writer import apply_patches

REAL = REPO / "tests" / "fixtures" / "retroarch" / "dualsense-bt"   # the owner's Deck, captured
EMUDECK = REPO / "tests" / "fixtures" / "retroarch" / "emudeck-default"
GOLDEN = REPO / "tests" / "golden" / "retroarch" / "dualsense-snes.diff"
REMAP = "config/remaps/Snes9x/Snes9x.rmp"
CFG = "retroarch.cfg"


def resolution(**bindings) -> Resolution:
    """snes_standard_a="face_south" -> {"snes.standard.a": Choice({"input": "face_south"})}."""
    return Resolution(bindings={k.replace("_", "."): Choice({"input": v}, "user.test") for k, v in bindings.items()})


class OwnersDeck(unittest.TestCase):
    """A copy of the owner's captured config root, and render() against it."""

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


class RetroArchTest(OwnersDeck):
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


def hotkeys(**chords) -> Resolution:
    """save_state="select+r1" -> {"hotkey.save_state": Choice({"chord": ["select", "r1"]})}; a single name is an input."""
    def source(spec):
        return {"chord": spec.split("+")} if "+" in spec else {"input": spec}
    return Resolution(bindings={f"hotkey.{k}": Choice(source(v), "user.test") for k, v in chords.items()})


class RetroArchHotkeyTest(OwnersDeck):
    """Hotkeys in retroarch.cfg, against the owner's captured config (EmuDeck's, input_joypad_driver = "sdl2")."""

    def cfg_patches(self, players):
        patches, warnings = self.render(players)
        return {key: value for (file, key), value in patches.items() if file == CFG}, warnings

    def apply(self, players):
        rendered = self.adapter.render(players, self.snes9x, self.current)
        return apply_patches(self.root, rendered.patches, self.adapter.managed_keys(self.snes9x))

    def test_emudeck_scheme_is_a_noop(self):
        # EmuDeck's own Select+button binds, expressed as rules, change nothing.
        result = self.apply({1: hotkeys(exit="select+start", pause="select+face_south", save_state="select+r1",
                                        load_state="select+l1", prev_slot="select+dpad_left",
                                        next_slot="select+dpad_right", rewind="select+l2", menu="select+r3",
                                        fast_forward="select+r2", screenshot="select+face_east")})
        self.assertEqual((result.changed_files, result.rejected), ([], []))

    def test_moved_hotkey_writes_button_and_clears_axis(self):
        patches, warnings = self.cfg_patches({1: hotkeys(save_state="select+face_north", rewind="select+r1")})
        self.assertEqual(patches, {
            "input_enable_hotkey_btn": '"4"', "input_enable_hotkey_axis": '"nul"',
            "input_save_state_btn": '"3"', "input_save_state_axis": '"nul"',
            "input_rewind_btn": '"10"', "input_rewind_axis": '"nul"'})
        # R1 was save state's: managed, so it lets go (save state moved anyway). North is disk_next's: only flagged.
        self.assertEqual(warnings, ["retroarch: input_disk_next_btn is on the same input as input_save_state; "
                                    "both fire"])

    def test_trigger_is_an_axis_and_displaces_the_live_hotkey(self):
        patches, warnings = self.cfg_patches({1: hotkeys(screenshot="select+r2")})
        self.assertEqual(patches["input_screenshot_axis"], '"+5"')
        self.assertEqual(patches["input_screenshot_btn"], '"nul"')
        self.assertEqual(patches["input_toggle_fast_forward_axis"], '"nul"')   # EmuDeck's Select+R2 lets go
        self.assertEqual(len(warnings), 1)

    def test_chord_order_does_not_matter(self):
        patches, _ = self.cfg_patches({1: hotkeys(exit="start+select", pause="select+face_south")})
        self.assertEqual((patches["input_enable_hotkey_btn"], patches["input_exit_emulator_btn"]), ('"4"', '"6"'))

    def test_one_enable_button_for_all(self):
        patches, warnings = self.cfg_patches({1: hotkeys(save_state="l3+r1", load_state="l3+l1",
                                                         pause="select+face_south")})
        self.assertEqual(patches["input_enable_hotkey_btn"], '"7"')            # the button most chords share
        self.assertNotIn("input_pause_toggle_btn", patches)
        self.assertTrue(any("hotkey.pause" in w for w in warnings))
        self.assertTrue(any("input_reset_btn" in w for w in warnings))         # EmuDeck's reset is on L3
        self.assertTrue(any("enable button is now l3" in w for w in warnings))

    def test_shapes_retroarch_cannot_bind(self):
        patches, warnings = self.cfg_patches({1: hotkeys(pause="face_south", exit="select+start+face_east",
                                                         screenshot="select+paddle1")})
        self.assertEqual(patches, {})
        self.assertEqual(len(warnings), 3)

    def test_fast_forward_is_the_toggle(self):
        patches, _ = self.cfg_patches({1: hotkeys(fast_forward="select+r2")})
        self.assertEqual(patches["input_toggle_fast_forward_axis"], '"+5"')
        patches, _ = self.cfg_patches({1: hotkeys(fast_forward_hold="select+r2")})
        self.assertEqual(patches["input_hold_fast_forward_axis"], '"+5"')
        self.assertEqual(patches["input_toggle_fast_forward_axis"], '"nul"')  # would fire with it otherwise

    def test_moving_exit_warns_about_the_quit_combo(self):
        _, warnings = self.cfg_patches({1: hotkeys(exit="select+face_north")})
        self.assertTrue(any("Start+Select still quits" in w for w in warnings))
        _, warnings = self.cfg_patches({1: hotkeys(exit="start+select")})      # where EmuDeck's combo is
        self.assertFalse(any("quit_gamepad_combo" in w for w in warnings))
        cfg = self.root / CFG
        cfg.write_text(cfg.read_text(encoding="utf-8").replace('input_quit_gamepad_combo = "4"',
                                                               'input_quit_gamepad_combo = "0"'), encoding="utf-8")
        _, warnings = self.cfg_patches({1: hotkeys(exit="select+face_north")})
        self.assertFalse(any("quit_gamepad_combo" in w for w in warnings))

    def test_none_unbinds(self):
        patches, _ = self.cfg_patches({1: hotkeys(rewind="none")})
        self.assertEqual(patches, {"input_rewind_btn": '"nul"', "input_rewind_axis": '"nul"'})

    def test_other_driver_is_left_alone(self):
        cfg = self.root / CFG
        cfg.write_text(cfg.read_text(encoding="utf-8").replace('input_joypad_driver = "sdl2"',
                                                               'input_joypad_driver = "udev"'), encoding="utf-8")
        patches, warnings = self.cfg_patches({1: hotkeys(save_state="select+face_north")})
        self.assertEqual(patches, {})
        self.assertIn("udev", warnings[0])

    def test_only_player_one_and_managed_keys(self):
        patches, _ = self.cfg_patches({2: hotkeys(save_state="select+face_north")})
        self.assertEqual(patches, {})
        result = self.apply({1: hotkeys(save_state="select+face_north", screenshot="select+r2")})
        self.assertEqual((result.changed_files, result.rejected), ([CFG], []))


class RetroArchGoldenTest(unittest.TestCase):
    """examples/ rules, P1 = DualSense, launching an SNES game, against EmuDeck's shipped config."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "retroarch"
        shutil.copytree(EMUDECK, self.root)
        db = ControllerDB(load_json(REPO / "data" / "controllers.json"))
        rules = load_rules(REPO / "examples", "user").rules
        target = Target("snes", "retroarch", None)
        self.players = {1: set_by_rules(resolve(rules, db.classify((), claimed_model="sony.dualsense"), target,
                                                load_layouts(REPO / "data" / "layouts")))}
        self.adapter = RetroArchAdapter()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def current(self, file, section, key):
        path = self.root / file
        return IniDocument.parse(path.read_text(encoding="utf-8")).get(section, key) if path.exists() else None

    def test_matches_golden_diff(self):
        core = self.adapter.core_for("snes")
        rendered = self.adapter.render(self.players, core, self.current)
        result = apply_patches(self.root, rendered.patches, self.adapter.managed_keys(core), dry_run=True)
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(result.diff, encoding="utf-8")
        self.assertEqual(result.rejected, [])
        self.assertEqual(result.diff, GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
