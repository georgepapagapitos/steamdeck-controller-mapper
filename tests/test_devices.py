import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO
from maphelper.cli import main
from maphelper.devices import (ControllerDB, infer_style, is_gamepad, parse_ignore_devices,
                               parse_proc_input_devices, parse_virtual_gamepad_info, stable_id, steam_slots,
                               usable_serial, with_usb_serials)
from maphelper.store import load_json

# Hand-written in the /proc/bus/input/devices format; replace with captured fixtures (spike S8).
PROC = """I: Bus=0005 Vendor=054c Product=09cc Version=8100
N: Name="Wireless Controller"
P: Phys=aa:bb:cc:00:11:22
S: Sysfs=/devices/virtual/misc/uhid/0005:054C:09CC.0003/input/input20
U: Uniq=a4:ae:12:34:56:78
H: Handlers=event18 js1
B: EV=20000b

I: Bus=0005 Vendor=054c Product=09cc Version=8100
N: Name="Wireless Controller Motion Sensors"
P: Phys=aa:bb:cc:00:11:22
U: Uniq=a4:ae:12:34:56:78
H: Handlers=event19

I: Bus=0003 Vendor=045e Product=028e Version=0114
N: Name="Microsoft X-Box 360 pad"
P: Phys=usb-0000:04:00.3-1/input0
U: Uniq=
H: Handlers=event20 js2
"""


class DevicesTest(unittest.TestCase):
    def setUp(self):
        self.devices = parse_proc_input_devices(PROC)
        self.db = ControllerDB(load_json(REPO / "data" / "controllers.json"))

    def test_parse(self):
        self.assertEqual(len(self.devices), 3)
        ds4 = self.devices[0]
        self.assertEqual((ds4.name, ds4.vid_pid, ds4.uniq), ("Wireless Controller", "054c:09cc", "a4:ae:12:34:56:78"))
        self.assertEqual(ds4.handlers, ("event18", "js1"))

    def test_gamepads_only(self):
        self.assertEqual([d.name for d in self.devices if is_gamepad(d)],
                         ["Wireless Controller", "Microsoft X-Box 360 pad"])

    def test_stable_ids(self):
        self.assertEqual(stable_id(self.devices[0]), "mac:a4:ae:12:34:56:78")
        self.assertEqual(stable_id(self.devices[2]), "path:045e:028e:usb-0000:04:00.3-1/input0")

    def test_classify_ds4(self):
        c = self.db.classify(("mac:x",), "054c:09cc", "Wireless Controller")
        self.assertEqual((c.family, c.brand, c.style), ("sony.dualshock4", "sony", "playstation"))
        self.assertIn("gyro", c.capabilities)

    def test_xbox360_id_is_ambiguous(self):
        self.assertTrue(self.db.is_ambiguous(self.db.model_for("045e:028e")))

    def test_claim_overrides_detection(self):
        c = self.db.classify(("usb:1",), "045e:028e", claimed_model="8bitdo.pro2.dinput")
        self.assertEqual(c.brand, "8bitdo")

    def test_infer_style(self):
        self.assertEqual(infer_style("Pro Controller"), "nintendo")
        self.assertEqual(infer_style("Generic USB Joystick"), "xbox")


# Format per SDL's SDL_steam_virtual_gamepad.c; hand-written until spike S1 captures a real one.
VIRTUAL_INFO = """[slot 0]
name=PS4 Controller
VID=0x054c
PID=0x09cc
type=ps4
handle=1234567890

[slot 1]
name=Steam Deck
VID=0x28de
PID=0x1205
type=steamdeck ; comment
handle=42
"""

VIRTUAL_PROC = """I: Bus=0003 Vendor=28de Product=11ff Version=0001
N: Name="Microsoft X-Box 360 pad 1"
P: Phys=
U: Uniq=
H: Handlers=event21 js3

I: Bus=0003 Vendor=28de Product=11ff Version=0001
N: Name="Microsoft X-Box 360 pad 0"
P: Phys=
U: Uniq=
H: Handlers=event22 js4
"""


class SteamSlotsTest(unittest.TestCase):
    def test_parse_info(self):
        info = parse_virtual_gamepad_info(VIRTUAL_INFO)
        self.assertEqual(info[0]["type"], "ps4")
        self.assertEqual(info[1]["type"], "steamdeck")

    def test_slots_link_virtual_nodes_by_name_suffix(self):
        slots = steam_slots(parse_proc_input_devices(VIRTUAL_PROC), parse_virtual_gamepad_info(VIRTUAL_INFO))
        self.assertEqual([(s.slot, s.vid_pid) for s in slots], [(0, "054c:09cc"), (1, "28de:1205")])
        self.assertEqual(slots[0].virtual.handlers, ("event22", "js4"))
        self.assertEqual(slots[1].virtual.name, "Microsoft X-Box 360 pad 1")

    def test_slot_without_node(self):
        slots = steam_slots([], parse_virtual_gamepad_info(VIRTUAL_INFO))
        self.assertIsNone(slots[0].virtual)

    def test_ignore_devices(self):
        self.assertEqual(parse_ignore_devices("0x054c/0x09cc, 0x28DE/0x1205,"), {"054c:09cc", "28de:1205"})
        self.assertEqual(parse_ignore_devices(""), set())


class CapturedDeckTest(unittest.TestCase):
    """Against tests/fixtures/devices/dualsense-bt, captured on a real Deck (SteamOS 3.8.28)."""

    def setUp(self):
        root = REPO / "tests" / "fixtures" / "devices" / "dualsense-bt"
        self.devices = parse_proc_input_devices((root / "proc-bus-input-devices").read_text(encoding="utf-8"))
        self.info = parse_virtual_gamepad_info((root / "virtualgamepadinfo.txt").read_text(encoding="utf-8"))

    def test_motion_sensor_node_is_not_a_gamepad(self):
        # On the Deck the DualSense's motion node has a js handler too; INPUT_PROP_ACCELEROMETER tells them apart.
        pads = [d.name for d in self.devices if is_gamepad(d) and d.vendor == "054c"]
        self.assertEqual(pads, ["DualSense Wireless Controller"])

    def test_same_id_over_usb_and_bluetooth(self):
        # hid-playstation reports the Bluetooth MAC as uniq over USB too (tests/fixtures/devices/dualsense-usb).
        usb = parse_proc_input_devices((REPO / "tests/fixtures/devices/dualsense-usb/proc-bus-input-devices")
                                       .read_text(encoding="utf-8"))
        ids = {stable_id(d) for d in self.devices + usb if is_gamepad(d) and d.vendor == "054c"}
        self.assertEqual(len(ids), 1)
        self.assertTrue(ids.pop().startswith("mac:"))

    def test_steam_slot_handle_names_the_exact_physical_pad(self):
        for scenario in ("dualsense-bt", "dualsense-usb", "switchpro-usb", "8bitdo-u2-bt"):
            root = REPO / "tests" / "fixtures" / "devices" / scenario
            devices = parse_proc_input_devices((root / "proc-bus-input-devices").read_text(encoding="utf-8"))
            info = parse_virtual_gamepad_info((root / "virtualgamepadinfo.txt").read_text(encoding="utf-8"))
            pads = {stable_id(d) for d in devices if is_gamepad(d) and d.vendor in ("054c", "057e", "2dc8")}
            linked = {s.device_id for s in steam_slots(devices, info)} - {None}
            self.assertEqual(linked, pads, scenario)

    def test_wired_xinput_handle_holds_no_mac(self):
        # 8BitDo Ultimate 2 wired (2dc8:310b): handle is 0x1<VID><PID>..., uniq is a USB serial. Slot 1 is the same
        # pad from before, over BT and now off: Steam keeps the slot, with no virtual node.
        root = REPO / "tests" / "fixtures" / "devices" / "8bitdo-u2-usb"
        devices = parse_proc_input_devices((root / "proc-bus-input-devices").read_text(encoding="utf-8"))
        slots = {s.slot: s for s in steam_slots(devices, parse_virtual_gamepad_info(
            (root / "virtualgamepadinfo.txt").read_text(encoding="utf-8")))}
        self.assertIsNone(slots[2].device_id)
        self.assertIsNotNone(slots[2].virtual)
        self.assertIsNone(slots[1].virtual)
        # xpad leaves uniq empty (only the pad's keyboard/mouse HID nodes carry the USB serial), so without sysfs
        # (as here: the capture has no USB serials) the id is port-bound. UsbSerialTest covers it with sysfs.
        self.assertTrue(stable_id(next(d for d in devices if is_gamepad(d) and d.vendor == "2dc8")).startswith("path:"))

    def test_reorder_moves_pads_between_virtual_pads(self):
        # Steam "Reorder controllers": Switch Pro, 8BitDo, DualSense, Deck. Virtual pad 0 (Deck before) is the Pro now.
        ids = {}
        for scenario in ("all-three", "all-three-reordered"):
            root = REPO / "tests" / "fixtures" / "devices" / scenario
            devices = parse_proc_input_devices((root / "proc-bus-input-devices").read_text(encoding="utf-8"))
            info = parse_virtual_gamepad_info((root / "virtualgamepadinfo.txt").read_text(encoding="utf-8"))
            ids[scenario] = [(s.slot, s.vid_pid, s.device_id, s.virtual is not None) for s in steam_slots(devices, info)]
        self.assertEqual([v for _, v, _, _ in ids["all-three"]], ["28de:1205", "054c:0ce6", "2dc8:6012", "057e:2009"])
        self.assertEqual([v for _, v, _, _ in ids["all-three-reordered"]],
                         ["057e:2009", "2dc8:6012", "054c:0ce6", "28de:1205"])
        self.assertEqual({d for _, _, d, _ in ids["all-three"]}, {d for _, _, d, _ in ids["all-three-reordered"]})
        self.assertTrue(all(live for *_, live in ids["all-three-reordered"]))

    def test_ignore_list_names_every_supported_pad_not_the_connected_ones(self):
        # Only a DualSense was connected, yet Steam's list covers hundreds of pads, and it's the same with Steam Input
        # disabled for the game, so it can't tell which pads are behind Steam.
        envs = {}
        for name in ("on", "off"):
            text = (REPO / f"tests/fixtures/devices/game-steam-input-{name}/env.txt").read_text(encoding="utf-8")
            env = dict(line.partition("=")[::2] for line in text.splitlines() if not line.startswith("#"))
            envs[name] = env
        ignored = parse_ignore_devices(envs["on"]["SDL_GAMECONTROLLER_IGNORE_DEVICES"])
        self.assertGreater(len(ignored), 500)
        self.assertTrue({"054c:0ce6", "057e:2009", "2dc8:6012"} <= ignored)
        self.assertEqual(envs["on"], envs["off"])

    def test_steam_slots_map_to_physical_pads(self):
        slots = {s.slot: (s.vid_pid, s.type) for s in steam_slots(self.devices, self.info)}
        self.assertEqual(slots, {0: ("28de:1205", "steam"), 1: ("054c:0ce6", "ps5")})


# The wired 8BitDo's USB device as the Deck's own port shows it (tests/fixtures/devices/8bitdo-u2-usb), and as it would
# sit behind the dock's hub (port 3, like the Switch Pro in tests/fixtures/devices/docked). No capture holds the sysfs
# serial yet, so the trees below are built here with made-up serials.
# Windows can't make directories with ":" in the name, so the constructed trees leave the PCI part out.
CAPTURED_PORT = "/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-1"
PORT = "/devices/pci/usb1/1-1"
DOCK = PORT + "/1-1.3"
SERIAL = "E1F2A3B4C5"  # made up: never put a real device id in a test


def make_sysfs(rows) -> Path:
    """A minimal sysfs tree: rows of (USB device path as in "S: Sysfs=", "vid:pid", serial or None)."""
    root = Path(tempfile.mkdtemp())
    for path, vid_pid, serial in rows:
        d = root / path.lstrip("/")
        d.mkdir(parents=True, exist_ok=True)
        vid, pid = vid_pid.split(":")
        (d / "idVendor").write_text(vid + "\n", encoding="utf-8")
        (d / "idProduct").write_text(pid + "\n", encoding="utf-8")
        if serial is not None:
            (d / "serial").write_text(serial + "\n", encoding="utf-8")
    return root


def xpad_node(usb_dir: str, phys: str, vid_pid: str = "2dc8:310b", uniq: str = "") -> str:
    vid, pid = vid_pid.split(":")
    return (f"I: Bus=0003 Vendor={vid} Product={pid} Version=0114\nN: Name=\"Pad\"\nP: Phys={phys}\n"
            f"S: Sysfs={usb_dir}/{usb_dir.rsplit('/', 1)[1]}:1.0/input/input53\nU: Uniq={uniq}\n"
            "H: Handlers=event23 js2\n")


class UsbSerialTest(unittest.TestCase):
    def ids(self, proc: str, sysfs: Path) -> list[str]:
        return [stable_id(d) for d in with_usb_serials(parse_proc_input_devices(proc), sysfs) if is_gamepad(d)]

    def test_wired_pad_keeps_its_id_when_docked(self):
        handheld = self.ids(xpad_node(PORT, "usb-0000:04:00.3-1/input0"), make_sysfs([(PORT, "2dc8:310b", SERIAL)]))
        docked = self.ids(xpad_node(DOCK, "usb-0000:04:00.3-1.3/input0"),
                          make_sysfs([(PORT, "2109:2817", "HUB0000042"), (DOCK, "2dc8:310b", SERIAL)]))
        self.assertEqual(handheld, ["usb-serial:2dc8:310b:e1f2a3b4c5"])
        self.assertEqual(docked, handheld)

    @unittest.skipIf(os.name == "nt", "the captured sysfs path has ':' in it")
    def test_captured_wired_8bitdo_gets_a_usb_serial_id_and_keeps_its_steam_slot(self):
        root = REPO / "tests" / "fixtures" / "devices" / "8bitdo-u2-usb"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["devices", "--json", "--proc-file", str(root / "proc-bus-input-devices"),
                  "--virtual-info", str(root / "virtualgamepadinfo.txt"),
                  "--sys-root", str(make_sysfs([(CAPTURED_PORT, "2dc8:310b", SERIAL)]))])
        row = next(r for r in json.loads(out.getvalue())["controllers"] if r["vid_pid"] == "2dc8:310b")
        self.assertEqual(row["id"], "usb-serial:2dc8:310b:e1f2a3b4c5")
        self.assertEqual(row["steam_slot"], 2)  # wired handle has no MAC: linked by VID:PID, now to the serial id

    def test_no_serial_or_only_a_hubs_stays_port_bound(self):
        self.assertEqual(self.ids(xpad_node(PORT, "p0"), make_sysfs([(PORT, "2dc8:310b", None)])),
                         ["path:2dc8:310b:p0"])
        # The pad has no serial; the hub above it does. The hub's serial must not become the pad's.
        self.assertEqual(self.ids(xpad_node(DOCK, "p3"),
                                  make_sysfs([(PORT, "2109:2817", "HUB0000042"), (DOCK, "2dc8:310b", None)])),
                         ["path:2dc8:310b:p3"])
        self.assertEqual(self.ids(xpad_node(PORT, "p0"), Path(tempfile.mkdtemp())), ["path:2dc8:310b:p0"])

    def test_usb_device_of_another_vid_pid_is_ignored(self):
        self.assertEqual(self.ids(xpad_node(PORT, "p0"), make_sysfs([(PORT, "045e:028e", SERIAL)])),
                         ["path:2dc8:310b:p0"])

    def test_uniq_beats_the_usb_serial(self):
        sysfs = make_sysfs([(PORT, "054c:0ce6", SERIAL)])
        self.assertEqual(self.ids(xpad_node(PORT, "", "054c:0ce6", "A0:B1:C2:D3:E4:F5"), sysfs),
                         ["mac:a0:b1:c2:d3:e4:f5"])

    def test_only_usb_nodes_are_read(self):
        sysfs = make_sysfs([("/devices/virtual/misc/uhid", "2dc8:6012", SERIAL)])
        bt = ("I: Bus=0005 Vendor=2dc8 Product=6012 Version=0001\nP: Phys=x\n"
              "S: Sysfs=/devices/virtual/misc/uhid/0005:2DC8:6012.000B/input/input48\nU: Uniq=\nH: Handlers=js1\n")
        self.assertEqual(self.ids(bt, sysfs), ["path:2dc8:6012:x"])

    def test_bogus_serials_are_not_ids(self):
        for bogus in ("", "   ", "123", "000000", "FFFFFFFF", "0123456789", "XXXXXXXXXX", "AB CD12", "AB\x01CD12"):
            self.assertEqual(usable_serial(bogus), "", repr(bogus))
        self.assertEqual(usable_serial(" A1B2C3D4\n"), "a1b2c3d4")

    def test_a_serial_two_connected_pads_share_is_not_an_id(self):
        two = xpad_node(PORT + "/1-1.1", "p1") + "\n" + xpad_node(PORT + "/1-1.2", "p2")
        same = make_sysfs([(PORT + "/1-1.1", "2dc8:310b", SERIAL), (PORT + "/1-1.2", "2dc8:310b", SERIAL)])
        self.assertEqual(self.ids(two, same), ["path:2dc8:310b:p1", "path:2dc8:310b:p2"])
        apart = make_sysfs([(PORT + "/1-1.1", "2dc8:310b", SERIAL), (PORT + "/1-1.2", "2dc8:310b", "E1F2A3B4C6")])
        self.assertEqual(self.ids(two, apart), ["usb-serial:2dc8:310b:e1f2a3b4c5", "usb-serial:2dc8:310b:e1f2a3b4c6"])


if __name__ == "__main__":
    unittest.main()
