"""Player assignment: physical pad -> Steam slot -> the emulator's own joystick index (docs/04 §5.2)."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper import cli
from maphelper.adapters.dolphin import DolphinAdapter
from maphelper.adapters.retroarch import RetroArchAdapter
from maphelper.devices import (POLICY_EXTERNAL_FIRST, POLICY_STEAM_ORDER, SDL_ORDER_NODES, SDL_ORDER_SLOTS, docked,
                               parse_drm_status, parse_proc_input_devices,
                               parse_virtual_gamepad_info, player_order, sdl_joysticks, steam_order, steam_slots)

DEVICES = REPO / "tests" / "fixtures" / "devices"
GOLDEN = REPO / "tests" / "golden"

# Hand-written, shaped like the Game Mode session in docs/13 S1: after a reorder the DualSense is slot 0 but its
# virtual pad ("pad 0") is js5, while the Deck's ("pad 1") is js0. Handles and MACs are made up.
GAME_MODE_PROC = """I: Bus=0003 Vendor=28de Product=11ff Version=0001
N: Name="Microsoft X-Box 360 pad 1"
P: Phys=
U: Uniq=
H: Handlers=event18 js0
B: PROP=0

I: Bus=0005 Vendor=054c Product=0ce6 Version=8100
N: Name="DualSense Wireless Controller"
P: Phys=02:00:00:00:00:01
U: Uniq=02:00:00:aa:bb:01
H: Handlers=event20 js1
B: PROP=0

I: Bus=0005 Vendor=054c Product=0ce6 Version=8100
N: Name="DualSense Wireless Controller Motion Sensors"
P: Phys=02:00:00:00:00:01
U: Uniq=02:00:00:aa:bb:01
H: Handlers=event21 js2
B: PROP=40

I: Bus=0003 Vendor=28de Product=11ff Version=0001
N: Name="Microsoft X-Box 360 pad 0"
P: Phys=
U: Uniq=
H: Handlers=event25 js5
B: PROP=0
"""
GAME_MODE_INFO = """[slot 0]
name=DualSense Wireless Controller
VID=0x054c
PID=0x0ce6
handle=0x000d020000aabb01
type=ps5
[slot 1]
name=Steam Deck Controller
VID=0x28de
PID=0x1205
handle=0x000000ff00000001
type=steam
"""


def joysticks(proc, info, order, behind_steam=None):
    devices = parse_proc_input_devices(proc)
    slots = steam_slots(devices, parse_virtual_gamepad_info(info))
    live = {s.vid_pid for s in slots if s.virtual}
    return sdl_joysticks(devices, slots, live if behind_steam is None else behind_steam, order)


def fixture(scenario):
    root = DEVICES / scenario
    return ((root / "proc-bus-input-devices").read_text(encoding="utf-8"),
            (root / "virtualgamepadinfo.txt").read_text(encoding="utf-8"))


class SdlOrderTest(unittest.TestCase):
    def test_old_sdl_numbers_by_node(self):
        # What RetroArch did on the Deck: user 1 was js0 (the Deck), not "pad 0" (the DualSense).
        joys = joysticks(GAME_MODE_PROC, GAME_MODE_INFO, SDL_ORDER_NODES)
        self.assertEqual([(j.index, j.slot.slot, j.name) for j in joys],
                         [(0, 1, "Microsoft X-Box 360 pad 1"), (1, 0, "Microsoft X-Box 360 pad 0")])
        players = steam_order(joys)
        self.assertEqual([(j.slot.slot, j.index) for j in players], [(0, 1), (1, 0)])

    def test_new_sdl_numbers_by_slot_and_uses_steam_names(self):
        joys = joysticks(GAME_MODE_PROC, GAME_MODE_INFO, SDL_ORDER_SLOTS)
        self.assertEqual([(j.index, j.slot.slot, j.name) for j in joys],
                         [(0, 0, "DualSense Wireless Controller"), (1, 1, "Steam Deck Controller")])
        self.assertEqual([j.index for j in steam_order(joys)], [0, 1])

    def test_physical_pad_behind_steam_is_hidden_and_a_native_one_is_not(self):
        # Behind Steam, SDL drops the physical DualSense (ignore list); with Steam Input off for it, SDL sees it,
        # and its js1 comes between the two virtual pads in node order. Its motion node never counts.
        names = [j.device.name for j in joysticks(GAME_MODE_PROC, GAME_MODE_INFO, SDL_ORDER_NODES, set())]
        self.assertEqual(names, ["Microsoft X-Box 360 pad 1", "DualSense Wireless Controller",
                                 "Microsoft X-Box 360 pad 0"])
        joys = joysticks(GAME_MODE_PROC, GAME_MODE_INFO, SDL_ORDER_SLOTS, set())
        self.assertEqual([j.device.name for j in joys][-1], "DualSense Wireless Controller")   # after virtual pads
        self.assertIsNone(steam_order(joys)[-1].slot)                                          # and last player

    def test_stale_slot_is_skipped(self):
        # 8bitdo-u2-usb: slot 1 is a pad that went away (no "pad 1" node); the wired 8BitDo in slot 2 is player 2.
        for order in (SDL_ORDER_NODES, SDL_ORDER_SLOTS):
            players = steam_order(joysticks(*fixture("8bitdo-u2-usb"), order))
            self.assertEqual([(j.slot.slot, j.index) for j in players], [(0, 0), (2, 1)])

    def test_reorder_moves_players_not_nodes(self):
        # Steam's "Reorder controllers" re-feeds the virtual pads, so player K is still virtual pad K-1 in both orders.
        for scenario in ("all-three", "all-three-reordered", "docked", "deck-only", "dualsense-bt"):
            for order in (SDL_ORDER_NODES, SDL_ORDER_SLOTS):
                players = steam_order(joysticks(*fixture(scenario), order))
                self.assertEqual([j.index for j in players], list(range(len(players))), scenario)
        players = steam_order(joysticks(*fixture("all-three-reordered"), SDL_ORDER_SLOTS))
        self.assertEqual([j.slot.vid_pid for j in players], ["057e:2009", "2dc8:6012", "054c:0ce6", "28de:1205"])


class AdapterTest(unittest.TestCase):
    def test_dolphin_index_counts_only_same_named_pads(self):
        two = GAME_MODE_INFO.replace("name=Steam Deck Controller", "name=DualSense Wireless Controller")
        joys = joysticks(GAME_MODE_PROC, two, SDL_ORDER_SLOTS)
        dolphin = DolphinAdapter()
        self.assertEqual([dolphin.device_ref(j, joys) for j in joys],
                         ["SDL/0/DualSense Wireless Controller", "SDL/1/DualSense Wireless Controller"])
        joys = joysticks(GAME_MODE_PROC, GAME_MODE_INFO, SDL_ORDER_SLOTS)
        self.assertEqual([dolphin.device_ref(j, joys) for j in joys],
                         ["SDL/0/DualSense Wireless Controller", "SDL/0/Steam Deck Controller"])

    def test_dolphin_device_patches(self):
        rendered = DolphinAdapter().render({}, devices={1: "SDL/0/A", 2: "SDL/0/B", 5: "SDL/0/C"})
        self.assertEqual({(p.file, p.section, p.value) for p in rendered.patches},
                         {("GCPadNew.ini", "GCPad1", "SDL/0/A"), ("GCPadNew.ini", "GCPad2", "SDL/0/B"),
                          ("Hotkeys.ini", "Hotkeys", "SDL/0/A")})

    def test_retroarch_port_patches_are_managed(self):
        from maphelper.writer import is_managed
        adapter = RetroArchAdapter()
        core = adapter.core_for("snes")
        rendered = adapter.render({}, core, ports={1: 1, 2: 0, 12: 11})
        self.assertEqual([(p.file, p.key, p.value) for p in rendered.patches],
                         [("retroarch.cfg", "input_player1_joypad_index", '"1"'),
                          ("retroarch.cfg", "input_player2_joypad_index", '"0"'),
                          ("retroarch.cfg", "input_player12_joypad_index", '"11"')])
        self.assertTrue(all(is_managed(p, adapter.managed_keys(core)) for p in rendered.patches))
        from maphelper.writer import Patch
        self.assertFalse(is_managed(Patch("retroarch.cfg", None, "input_player1_btn_a", '"0"'),
                                    adapter.managed_keys(core)))

    def test_retroarch_port_checks(self):
        adapter = RetroArchAdapter()
        core = adapter.core_for("snes")
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        (root / "config" / core["core"]).mkdir(parents=True)
        (root / "config" / core["core"] / "Some Game.cfg").write_text('input_player1_joypad_index = "3"\n',
                                                                      encoding="utf-8")
        cfg = {"input_joypad_driver": '"udev"', "input_assign_ports_on_button_press": '"true"',
               "input_player2_device_reservation_type": '"1"'}
        warnings = adapter.check(root, core, lambda f, s, k: cfg.get(k) if f == "retroarch.cfg" else None, ports=True)
        self.assertEqual(len(warnings), 4, warnings)
        self.assertEqual(adapter.check(root, core, lambda *_: None), [])


class DockedTest(unittest.TestCase):
    def state(self, scenario):
        return docked(parse_drm_status((DEVICES / scenario / "drm-status.txt").read_text(encoding="utf-8")))

    def test_captures(self):
        self.assertEqual(self.state("docked"), (True, "DP-1 connected"))
        for scenario in ("deck-only", "all-three", "all-three-reordered", "dualsense-bt", "switchpro-usb"):
            self.assertFalse(self.state(scenario)[0], scenario)

    def test_no_display_is_handheld(self):
        # A dock with the TV off, or charging in handheld: power doesn't count, only a connected display does.
        drm = {"eDP-1": "connected", "DP-1": "disconnected", "Writeback-1": "unknown"}
        self.assertEqual(docked(drm), (False, "no external display connected"))
        self.assertEqual(docked({**drm, "Writeback-1": "connected"})[0], False)

    def test_undecided_without_connectors(self):
        self.assertIsNone(docked({})[0])
        self.assertIsNone(docked({"eDP-1": "connected"})[0])

    def test_external_first_moves_the_deck_last(self):
        # Steam's session put the Deck back in slot 0 (BOARD: switching sessions resets the order).
        deck_first = "[slot 0]" + GAME_MODE_INFO.split("[slot 1]")[1] + "[slot 1]" + \
            GAME_MODE_INFO.split("[slot 1]")[0].removeprefix("[slot 0]")
        joys = joysticks(GAME_MODE_PROC, deck_first, SDL_ORDER_NODES)
        self.assertEqual([j.slot.vid_pid for j in player_order(joys, POLICY_STEAM_ORDER)],
                         ["28de:1205", "054c:0ce6"])
        self.assertEqual([j.slot.vid_pid for j in player_order(joys, POLICY_EXTERNAL_FIRST)],
                         ["054c:0ce6", "28de:1205"])


class CliTest(unittest.TestCase):
    """End to end, against configs captured on the owner's Deck."""

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        self.assertEqual(code, 0, err.getvalue())
        return out.getvalue(), err.getvalue()

    def check_golden(self, path, text):
        if os.environ.get("UPDATE_GOLDEN"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_devices_shows_each_slots_player_and_emulator_index(self):
        for root in sorted(p for p in DEVICES.iterdir() if (p / "virtualgamepadinfo.txt").is_file()):
            out, _ = self.run_cli("devices", "--proc-file", str(root / "proc-bus-input-devices"),
                                  "--virtual-info", str(root / "virtualgamepadinfo.txt"), "--ignore-devices", "",
                                  "--drm-status", str(root / "drm-status.txt"),
                                  "--sys-root", str(root))
            with self.subTest(root.name):
                self.check_golden(GOLDEN / "devices" / f"{root.name}.txt", out)

    def game_mode_probe(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "proc").write_text(GAME_MODE_PROC, encoding="utf-8")
        (tmp / "info").write_text(GAME_MODE_INFO, encoding="utf-8")
        return tmp, ["--proc-file", str(tmp / "proc"), "--virtual-info", str(tmp / "info"), "--ignore-devices", "",
                     "--sys-root", str(tmp), "--policy", "steam-order"]

    def test_apply_retroarch_puts_the_dualsense_on_player_1(self):
        # The SNES test from docs/13 S1: DualSense in slot 0, the Deck's virtual pad enumerated first. Player 1 gets
        # the DualSense's remap (examples/09) and joypad port 1; player 2, the Deck, gets port 0.
        tmp, probe = self.game_mode_probe()
        shutil.copytree(DEVICES.parent / "retroarch" / "dualsense-bt", tmp / "retroarch")
        out, err = self.run_cli("apply", "--emulator", "retroarch", "--system", "snes",
                                "--config-root", str(tmp / "retroarch"), *probe)
        self.assertIn("player 1: DualSense Wireless Controller (steam slot 0)", err)
        self.check_golden(GOLDEN / "retroarch" / "game-mode-reorder.diff", out)

    def test_apply_dolphin_points_each_pad_at_its_player(self):
        tmp, probe = self.game_mode_probe()
        shutil.copytree(DEVICES.parent / "dolphin" / "dualsense-bt", tmp / "dolphin")
        out, _ = self.run_cli("apply", "--emulator", "dolphin", "--system", "gc",
                              "--config-root", str(tmp / "dolphin"), *probe)
        self.check_golden(GOLDEN / "dolphin" / "game-mode-reorder.diff", out)

    def test_doctor_does_not_flag_written_ports(self):
        # doctor's retroarch-autoconfig check warns on user binds in retroarch.cfg; a joypad port isn't one.
        from maphelper import doctor
        tmp, probe = self.game_mode_probe()
        shutil.copytree(DEVICES.parent / "retroarch" / "dualsense-bt", tmp / "retroarch")
        before = [f.message for f in doctor.check_retroarch(tmp / "retroarch") if f.check == "retroarch-autoconfig"]
        self.run_cli("apply", "--emulator", "retroarch", "--system", "snes", "--config-root", str(tmp / "retroarch"),
                     "--write", "--state-dir", str(tmp / "state"), *probe)
        cfg = (tmp / "retroarch" / "retroarch.cfg").read_text(encoding="utf-8")
        self.assertIn('input_player1_joypad_index = "1"', cfg)
        self.assertIn('input_player2_joypad_index = "0"', cfg)
        after = [f.message for f in doctor.check_retroarch(tmp / "retroarch") if f.check == "retroarch-autoconfig"]
        self.assertEqual(after, before)

    def test_docked_capture_puts_the_switch_pro_on_player_1(self):
        # docked: Steam's session left the Deck in slot 0; external-first moves it last.
        root = DEVICES / "docked"
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(DEVICES.parent / "retroarch" / "dualsense-bt", tmp / "retroarch")
        out, err = self.run_cli("apply", "--emulator", "retroarch", "--system", "snes",
                                "--config-root", str(tmp / "retroarch"), "--ignore-devices", "",
                                "--proc-file", str(root / "proc-bus-input-devices"),
                                "--virtual-info", str(root / "virtualgamepadinfo.txt"),
                                "--drm-status", str(root / "drm-status.txt"),
                                "--sys-root", str(tmp))
        self.assertIn("policy: external-first (docked: DP-1 connected)", err)
        self.assertIn("player 1: Nintendo Switch Pro Controller (steam slot 1)", err)
        self.assertIn('+input_player1_joypad_index = "1"', out)
        self.assertIn('+input_player2_joypad_index = "0"', out)

    def test_undecided_falls_back_to_steam_order(self):
        tmp, probe = self.game_mode_probe()
        probe = probe[:-2]                     # auto policy, but an empty sys root: no connectors
        out, _ = self.run_cli("devices", *probe)
        self.assertIn("policy: steam-order (can't tell docked from handheld (no external display connector found)",
                      out)

    def test_explicit_players_leave_ports_alone(self):
        tmp, probe = self.game_mode_probe()
        shutil.copytree(DEVICES.parent / "retroarch" / "dualsense-bt", tmp / "retroarch")
        out, _ = self.run_cli("apply", "--emulator", "retroarch", "--system", "snes", "--player", "sony.dualsense",
                              "--config-root", str(tmp / "retroarch"), *probe)
        self.assertNotIn("joypad_index", out)


if __name__ == "__main__":
    unittest.main()
