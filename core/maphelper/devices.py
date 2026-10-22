"""Controller classification and Linux input probing. See docs/04."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from .model import Controller


@dataclass(frozen=True)
class InputDevice:
    """One entry from /proc/bus/input/devices."""
    name: str
    bus: str
    vendor: str
    product: str
    version: str
    phys: str
    uniq: str
    handlers: tuple
    props: int = 0  # "B: PROP=" bitmask, INPUT_PROP_* from linux/input-event-codes.h
    sysfs: str = ""  # "S: Sysfs=", the node's path under /sys (drivers/input/input.c, kobject_get_path)
    usb_serial: str = ""  # the USB device's serial, filled in by with_usb_serials()

    @property
    def vid_pid(self) -> str:
        return f"{self.vendor}:{self.product}"


_I_LINE = re.compile(r"Bus=(\w+) Vendor=(\w+) Product=(\w+) Version=(\w+)")


def parse_proc_input_devices(text: str) -> list[InputDevice]:
    devices = []
    for block in text.strip().split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if len(line) < 3 or line[1] != ":":
                continue
            tag, rest = line[0], line[3:].strip()
            if tag == "I":
                fields["I"] = rest
            elif tag == "N":
                fields["name"] = rest.removeprefix("Name=").strip('"')
            elif tag == "P":
                fields["phys"] = rest.removeprefix("Phys=")
            elif tag == "U":
                fields["uniq"] = rest.removeprefix("Uniq=")
            elif tag == "S":
                fields["sysfs"] = rest.removeprefix("Sysfs=")
            elif tag == "H":
                fields["handlers"] = rest.removeprefix("Handlers=")
            elif tag == "B" and rest.startswith("PROP="):
                fields["props"] = rest.removeprefix("PROP=")
        match = _I_LINE.search(fields.get("I", ""))
        if not match:
            continue
        bus, vendor, product, version = (g.lower() for g in match.groups())
        devices.append(InputDevice(
            name=fields.get("name", ""), bus=bus, vendor=vendor, product=product, version=version,
            phys=fields.get("phys", ""), uniq=fields.get("uniq", ""),
            handlers=tuple(fields.get("handlers", "").split()),
            props=int(fields.get("props", "0"), 16), sysfs=fields.get("sysfs", ""),
        ))
    return devices


INPUT_PROP_ACCELEROMETER = 1 << 0x06


def is_gamepad(device: InputDevice) -> bool:
    """Gamepads expose a joystick handler (jsN); keyboards and mice don't. Sony and Nintendo motion-sensor nodes
    get one too (seen on a Deck, tests/fixtures/devices/dualsense-bt), but carry INPUT_PROP_ACCELEROMETER."""
    return any(h.startswith("js") for h in device.handlers) and not device.props & INPUT_PROP_ACCELEROMETER


def stable_id(device: InputDevice) -> str:
    """Preference order from docs/04 §1.2: uniq (MAC or serial), then the USB serial, then the port path."""
    # The prefix doesn't depend on the transport: hid-playstation and hid-nintendo put the Bluetooth MAC in uniq
    # over USB too (seen on a Deck with a DualSense), so one pad keeps one id either way.
    uniq = device.uniq.strip().lower()
    if uniq and set(uniq.replace(":", "")) != {"0"} and uniq != "xxxxxxxxxx":
        return f"mac:{uniq}" if _MAC.fullmatch(uniq) else f"serial:{uniq}"
    # A USB serial is only unique within one VID:PID, so the id carries both.
    if device.usb_serial:
        return f"usb-serial:{device.vid_pid}:{device.usb_serial}"
    return f"path:{device.vid_pid}:{device.phys}"


_MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")

# Serials a cheap pad might ship on every unit. Anything shorter than 4 characters or one character repeated is
# treated the same way.
_PLACEHOLDER_SERIALS = {"xxxxxxxxxx", "0123456789", "123456789", "1234567890", "12345678", "0123456789abcdef"}


def _usb_device_serial(device: InputDevice, sys_root: Path) -> tuple[Optional[Path], str]:
    """The USB device behind an input node and its serial, read from sysfs; (None, "") when there's none.

    xpad sets no uniq (drivers/input/joystick/xpad.c sets name and phys only), so for a wired X-input pad the USB
    device's `serial` is the only per-unit id. sysfs nests the input node under the USB interface and the interface
    under the USB device (seen on a Deck: `.../usb1/1-1/1-1:1.0/input/input53`, tests/fixtures/devices/8bitdo-u2-usb),
    so walking up from the node, the first directory with an `idVendor` is the USB device. Its `serial` exists only
    when the device has a serial-number string (drivers/usb/core/sysfs.c, usb_string_attr(serial) and
    dev_string_attrs_are_visible). usbhid copies the same string into hid->uniq (drivers/hid/usbhid/hid-core.c), which
    is why the 8BitDo's keyboard and mouse nodes show it (docs/13 S8)."""
    if device.bus != "0003" or not device.sysfs.startswith("/devices/"):
        return None, ""
    top = sys_root / "devices"
    node = sys_root / device.sysfs.lstrip("/")
    for d in (node, *node.parents):
        if d == top or top not in d.parents:
            break
        try:
            if not (d / "idVendor").is_file():
                continue
            vid_pid = ((d / "idVendor").read_text(encoding="utf-8").strip() + ":"
                       + (d / "idProduct").read_text(encoding="utf-8").strip()).lower()
            serial_file = d / "serial"
            serial = serial_file.read_text(encoding="utf-8", errors="replace").strip() if serial_file.is_file() else ""
        except OSError:
            return None, ""
        # Not the pad itself (a hub, say): its serial says nothing about which pad this is.
        return (d, serial) if vid_pid == device.vid_pid else (None, "")
    return None, ""


def usable_serial(serial: str) -> str:
    """Lower-cased serial, or "" for one that can't tell units apart (docs/04 §1.2)."""
    s = serial.strip().lower()
    clean = all(c.isprintable() and not c.isspace() for c in s)
    return s if clean and len(s) >= 4 and len(set(s)) > 1 and s not in _PLACEHOLDER_SERIALS else ""


def with_usb_serials(devices: list[InputDevice], sys_root: Path = Path("/sys")) -> list[InputDevice]:
    """Fill in usb_serial for USB input nodes from sysfs. Two connected USB devices of one VID:PID reporting the same
    serial both keep none: that serial isn't per-unit, so those pads stay port-bound (path ids)."""
    found = {}
    for i, dev in enumerate(devices):
        usb_dir, serial = _usb_device_serial(dev, sys_root)
        serial = usable_serial(serial)
        if usb_dir is not None and serial:
            found[i] = (usb_dir, serial)
    owners: dict[tuple, set] = {}
    for i, (usb_dir, serial) in found.items():
        owners.setdefault((devices[i].vid_pid, serial), set()).add(usb_dir)
    return [replace(dev, usb_serial=found[i][1]) if i in found and len(owners[(dev.vid_pid, found[i][1])]) == 1
            else dev for i, dev in enumerate(devices)]


STEAM_VIRTUAL_PAD = "28de:11ff"
_VIRTUAL_SLOT = re.compile(r"\bpad (\d+)$")


@dataclass(frozen=True)
class SteamSlot:
    """One Steam virtual pad, linked to the physical model Steam says is behind it (docs/04 §5.2)."""
    slot: int
    vid_pid: str          # physical controller's VID:PID
    type: str             # SDL gamepad type string: ps4, ps5, xboxone, switchpro, ...
    name: str             # Steam's display name for the physical pad
    virtual: Optional[InputDevice] = None
    handle: int = 0

    @property
    def device_id(self) -> Optional[str]:
        """The physical pad's stable id (as stable_id() gives it), so two pads of one model can be told apart.

        Seen on a Deck: a Bluetooth-capable pad's handle is a small prefix plus its MAC (0x000d<MAC> DualSense,
        0x0000<MAC> Switch Pro and 8BitDo Ultimate 2 over BT). A wired X-input pad's is 0x1<VID><PID><7 hex>,
        and the Deck's own is 0x000000ff<...> with type "steam"; neither holds a MAC, so they give None."""
        if self.type == "steam" or not self.handle or self.handle >> 48 > 0xff:
            return None
        return "mac:" + ":".join(re.findall("..", f"{self.handle & 0xFFFFFFFFFFFF:012x}"))


def parse_virtual_gamepad_info(text: str) -> dict[int, dict]:
    """Parse the file named by $SteamVirtualGamepadInfo (format per SDL_steam_virtual_gamepad.c)."""
    slots: dict[int, dict] = {}
    current: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        header = re.fullmatch(r"\[slot (\d+)\]", line)
        if header:
            current = slots.setdefault(int(header.group(1)), {})
        elif current is not None and "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            current[key] = value
    return slots


def parse_ignore_devices(value: str) -> set[str]:
    """$SDL_GAMECONTROLLER_IGNORE_DEVICES "0x054c/0x09cc,..." -> {"054c:09cc"}: pads behind Steam Input."""
    out = set()
    for item in value.split(","):
        vid, sep, pid = item.strip().partition("/")
        if sep:
            out.add(f"{int(vid, 16):04x}:{int(pid, 16):04x}")
    return out


def steam_slots(devices: list[InputDevice], info: dict[int, dict]) -> list[SteamSlot]:
    """Link each Steam virtual pad's evdev node (name ends in "pad <N>") to slot N in the info file."""
    nodes = {}
    for dev in devices:
        m = _VIRTUAL_SLOT.search(dev.name)
        if dev.vid_pid == STEAM_VIRTUAL_PAD and m and is_gamepad(dev):
            nodes[int(m.group(1))] = dev
    out = []
    for slot, entry in sorted(info.items()):
        try:
            vid_pid = f"{int(entry['VID'], 16):04x}:{int(entry['PID'], 16):04x}"
        except (KeyError, ValueError):
            continue
        try:
            handle = int(entry.get("handle", "0"), 16)
        except ValueError:
            handle = 0
        out.append(SteamSlot(slot, vid_pid, entry.get("type", ""), entry.get("name", ""), nodes.get(slot), handle))
    return out


class ControllerDB:
    def __init__(self, doc: dict):
        self.doc = doc
        self.families = doc.get("families", {})
        self.models = doc.get("models", {})
        self._by_id = {}
        for model_id, model in self.models.items():
            for vid_pid in model.get("ids", []):
                self._by_id.setdefault(vid_pid.lower(), model_id)
        self.virtual_ids = {i.lower() for v in doc.get("virtual_devices", {}).values() for i in v.get("ids", [])}

    def model_for(self, vid_pid: str) -> Optional[str]:
        return self._by_id.get(vid_pid.lower())

    def is_ambiguous(self, model_id: Optional[str]) -> bool:
        return bool(model_id and self.models.get(model_id, {}).get("ambiguous"))

    def is_virtual(self, vid_pid: str) -> bool:
        return vid_pid.lower() in self.virtual_ids

    def classify(self, device_ids: tuple, vid_pid: str = "", name: str = "",
                 claimed_model: Optional[str] = None) -> Controller:
        """User claims beat DB detection (docs/04 §3)."""
        model_id = claimed_model or self.model_for(vid_pid)
        model = self.models.get(model_id or "", {})
        family_id = model.get("family")
        family = self.families.get(family_id or "", {})
        caps = set(self.doc.get("capabilities_by_family", {}).get(family_id or "", []))
        caps |= set(model.get("caps_add", []))
        return Controller(
            device_ids=tuple(device_ids),
            model=model_id,
            family=family_id,
            brand=family.get("brand"),
            style=family.get("style") or infer_style(name),
            capabilities=frozenset(caps),
            name=name,
        )


def infer_style(name: str) -> str:
    """Fallback when no family is known (docs/04 §4)."""
    lowered = name.lower()
    if any(s in lowered for s in ("xbox", "x-box", "xinput")):
        return "xbox"
    if "wireless controller" in lowered or "dualshock" in lowered or "dualsense" in lowered:
        return "playstation"
    if "pro controller" in lowered or "joy-con" in lowered:
        return "nintendo"
    return "xbox"
