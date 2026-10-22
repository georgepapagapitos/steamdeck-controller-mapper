"""Controller classification and Linux input probing. See docs/04."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
            props=int(fields.get("props", "0"), 16),
        ))
    return devices


INPUT_PROP_ACCELEROMETER = 1 << 0x06


def is_gamepad(device: InputDevice) -> bool:
    """Gamepads expose a joystick handler (jsN); keyboards and mice don't. Sony and Nintendo motion-sensor nodes
    get one too (seen on a Deck, tests/fixtures/devices/dualsense-bt), but carry INPUT_PROP_ACCELEROMETER."""
    return any(h.startswith("js") for h in device.handlers) and not device.props & INPUT_PROP_ACCELEROMETER


def stable_id(device: InputDevice) -> str:
    """Preference order from docs/04 §1.2."""
    # The prefix doesn't depend on the transport: hid-playstation and hid-nintendo put the Bluetooth MAC in uniq
    # over USB too (seen on a Deck with a DualSense), so one pad keeps one id either way.
    uniq = device.uniq.strip().lower()
    if uniq and set(uniq.replace(":", "")) != {"0"} and uniq != "xxxxxxxxxx":
        return f"mac:{uniq}" if _MAC.fullmatch(uniq) else f"serial:{uniq}"
    return f"path:{device.vid_pid}:{device.phys}"


_MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")


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
