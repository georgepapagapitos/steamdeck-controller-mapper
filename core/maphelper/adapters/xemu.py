"""xemu adapter (original Xbox), v1: player order. See docs/adapters/xemu.md.

xemu puts a pad in Xbox port K when `[input.bindings] portK` in xemu.toml holds that pad's SDL joystick GUID
(ui/xemu-input.c L349-L431 @ v0.8.136). Every Steam virtual pad has its own GUID, because SDL's CRC-16 of the
evdev name ("Microsoft X-Box 360 pad N") is part of it, so writing port K = the GUID of player K's Steam slot puts
the right pad there. Button remaps (`[input] gamepad_mappings`) aren't written yet: xemu keeps them per slot, as an
inline array of tables the line editor can't patch (docs/adapters/xemu.md "Managed keys", v1.1).
"""

from __future__ import annotations

import struct
from typing import Callable, Optional

from .. import DATA
from ..devices import SDL_ORDER_SLOTS, InputDevice, Joystick
from ..resolve import Resolution
from ..store import load_json
from ..writer import Patch
from .dolphin import Rendered

FILE = "xemu.toml"
SECTION = "input.bindings"
PORTS = 4


def crc16(data: bytes) -> int:
    """SDL_crc16: CRC-16/ARC, reflected polynomial 0xA001, initial value 0 (src/stdlib/SDL_crc16.c L33-L52)."""
    crc = 0
    for byte in data:
        r, c = (crc ^ byte) & 0xFF, 0
        for _ in range(8):
            c = (0xA001 if (c ^ r) & 1 else 0) ^ (c >> 1)
            r >>= 1
        crc = c ^ (crc >> 8)
    return crc


def sdl_linux_guid(device: InputDevice) -> Optional[str]:
    """The GUID SDL3's Linux backend gives an evdev joystick: bus, CRC-16 of the name, vendor, 0, product, 0,
    version, as little-endian u16s, then driver signature and data 0 (SDL_CreateJoystickGUID, SDL_joystick.c
    L2931-L2973 @ release-3.4.14; IsJoystick, SDL_sysjoystick.c L292-L363), as SDL_GUIDToString writes it."""
    try:
        bus, vendor, product, version = (int(v, 16) for v in (device.bus, device.vendor, device.product, device.version))
    except ValueError:
        return None
    return struct.pack("<7H", bus, crc16(device.name.encode("utf-8")), vendor, 0, product, 0, version).hex() + "0000"


def is_steam_virtual(guid: str) -> bool:
    """A GUID SDL made for a Steam virtual pad (VID 28de, PID 11ff), whatever its slot."""
    guid = guid.strip().strip("'\"").lower()
    return len(guid) == 32 and guid[8:12] == "de28" and guid[16:20] == "ff11"


class XemuAdapter:
    id = "xemu"
    systems = {"xbox"}
    # SDL3 in the Flatpak scans /dev/input itself, Steam virtual pads first by slot (LINUX_ScanSteamVirtualGamepads,
    # SDL_sysjoystick.c L867-L948 @ release-3.4.14), as in Dolphin's case.
    sdl_order = SDL_ORDER_SLOTS

    def __init__(self, layout: Optional[dict] = None):
        self.layout = layout or load_json(DATA / "layouts" / "xbox.json")

    @property
    def managed_keys(self) -> dict:
        return {FILE: {"section": SECTION, "keys": [f"port{k}" for k in range(1, PORTS + 1)]}}

    def device_ref(self, joystick: Joystick, joysticks: list[Joystick]) -> Optional[str]:
        """The port value for this joystick: its GUID, for a Steam virtual pad only (a pad Steam doesn't
        virtualise may be opened through HIDAPI, whose GUID differs: docs/adapters/xemu.md, left alone)."""
        return sdl_linux_guid(joystick.device) if joystick.slot is not None else None

    def render(self, players: dict[int, Resolution], system: str = "xbox",
               current: Optional[Callable] = None, devices: Optional[dict] = None) -> Rendered:
        out = Rendered()
        if any(not t.startswith("hotkey.") for r in players.values() if r for t in r.bindings):
            out.warnings.append("xemu: button changes aren't written for xemu yet; only the player order is")
        if not devices:
            return out                                 # no probe (--player): nothing says which pad is where
        guids = {n: g for n, g in devices.items() if g and 1 <= n <= PORTS}
        if not guids:
            out.warnings.append("xemu: no Steam virtual pads, so the ports were left as they are")
            return out
        for k in range(1, PORTS + 1):
            if k in guids:
                out.patches.append(Patch(FILE, SECTION, f"port{k}", f"'{guids[k]}'"))
                continue
            # A port that still names a Steam slot would bind that pad when no earlier port takes it: clear it.
            # The keyboard, and pads Steam doesn't virtualise, keep their ports.
            live = current(FILE, SECTION, f"port{k}") if current else None
            if live and is_steam_virtual(live):
                out.patches.append(Patch(FILE, SECTION, f"port{k}", "''"))
        return out

    def describe(self, player: int, after: Callable, system: str = "xbox"):
        """xemu's default mapping, which is the layout's positional default (docs/adapters/xemu.md "Console target
        table"): button remaps aren't written yet, so it's what every pad does. Back + Start opens xemu's menu on
        any pad (ui/xui/main.cc L272-L307); its other shortcuts are keyboard only."""
        from ..show import Described
        out = Described(port=player if player <= PORTS else None)
        source = ("emulator", "xemu default", False)
        pad = self.layout["default_controller"]
        for name, physical in self.layout["positional_default"][pad].items():
            out.drives.append((physical, f"xbox.{pad}.{name}", source))
        if player == 1:
            out.hotkeys.append(("hotkey.menu", ["select", "start"], ("emulator", "xemu (fixed)", False)))
        return out

