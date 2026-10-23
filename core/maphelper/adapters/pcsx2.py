"""PCSX2 (Qt) adapter, DualShock 2 pads + hotkeys (prototype). See docs/adapters/pcsx2.md.

All emulator facts come from data/adapters/pcsx2.json. This module only
translates resolved canonical bindings into those tokens.

Unlike Dolphin, PCSX2 has no per-pad Device key: every binding names its pad (`SDL-0/FaceSouth`). So pointing a
player at a pad means rewriting the SDL-<n> in each of that player's bindings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .. import DATA
from ..devices import _VIRTUAL_SLOT, STEAM_VIRTUAL_PAD, Joystick
from ..resolve import Resolution
from ..store import load_json
from ..writer import Patch

TABLE = DATA / "adapters" / "pcsx2.json"
FILE = "inis/PCSX2.ini"
AXES = ("ls_x", "ls_y", "rs_x", "rs_y")
PORTS = 2                 # Pad1 = port 1, Pad2 = port 2; Pad3-8 need a multitap (sioConvertPadToPortAndSlot)
_SDL_REF = re.compile(r"\bSDL-(\d+)/")


@dataclass
class Rendered:
    patches: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class PCSX2Adapter:
    id = "pcsx2"
    systems = {"ps2"}

    def __init__(self, table: Optional[dict] = None):
        self.table = table or load_json(TABLE)
        self.tokens = self.table["physical_tokens"]
        self.sdl_order = self.table["device_ref"]["sdl_order"]
        hotkeys = self.table["hotkeys"]
        self.hotkey_keys = [k for k in hotkeys["targets"].values() if k] + hotkeys["device_keys"]
        self.pad_keys = []    # every binding key of a [PadN], in table order
        for spec in self.table["targets"].values():
            self.pad_keys += list(spec["keys"].values()) if "keys" in spec else [spec["key"]]
        self.pad_keys += list(self.table["options"]["rumble"]["keys"].values())

    @property
    def managed_keys(self) -> dict:
        pad, hotkeys = self.table["managed_keys"][FILE]
        return {FILE: [pad, {**hotkeys, "keys": self.hotkey_keys}]}

    def render(self, players: dict[int, Resolution], system: str = "ps2",
               current: Optional[Callable[[str, str, str], Optional[str]]] = None,
               devices: Optional[dict[int, str]] = None) -> Rendered:
        """players: 1-based player number -> resolution for that player's controller.
        current(file, section, key) returns the value on disk, so we can avoid needless rewrites.
        devices: player number -> PCSX2 device (device_ref, e.g. SDL-1) of that player's pad."""
        self._current = current or (lambda *_: None)
        out = Rendered()
        if system not in self.systems:
            out.warnings.append(f"pcsx2: rendering for {system!r} is not implemented")
            return out
        devices = devices or {}
        for player in sorted(set(players) | set(devices)):
            if player > PORTS:
                out.warnings.append(f"pcsx2: player {player} needs a multitap, which map-helper doesn't set up yet; "
                                    f"skipped")
                continue
            written = set()
            if player in players:
                written = self._render_pad(player, players[player], devices.get(player), out)
            if player in devices:
                self._repoint(f"Pad{player}", [k for k in self.pad_keys if k not in written], devices[player], out)
            self._check_type(player, written, out)
        # Hotkeys live on player 1's pad (EmuDeck's convention, data/defaults/README.md).
        written = self._render_hotkeys(players[1], devices.get(1), out) if 1 in players else set()
        if 1 in devices:
            self._repoint(self.table["hotkeys"]["section"], [k for k in self.hotkey_keys if k not in written],
                          devices[1], out)
        return out

    def device_ref(self, joystick: Joystick, joysticks: list[Joystick]) -> str:
        """SDL-<n>, n = the SDL player index PCSX2 reads (SDLInputSource::OpenDevice). SDL gives a Steam virtual pad its
        slot, the N in "pad N", and any other gamepad the first index free when it's added (SDL_PrivateJoystickAdded),
        in SDL's order: under SDL3 every virtual pad first, so the others fill the gaps."""
        taken = {n for n in map(_steam_slot, joysticks) if n is not None}
        for j in joysticks:
            n = _steam_slot(j)
            if n is None:
                n = next(i for i in range(len(taken) + 1) if i not in taken)
                taken.add(n)
            if j.index == joystick.index:
                return self.table["device_ref"]["format"].format(player_index=n)
        raise ValueError(f"{joystick.name} is not among the joysticks")

    # -- pads ------------------------------------------------------------------

    def _render_pad(self, player: int, resolution: Resolution, device: Optional[str], out: Rendered) -> set:
        """Patches for the rules' bindings and options; returns the keys written."""
        section = f"Pad{player}"
        written = set()

        def put(key, value):
            out.patches.append(Patch(FILE, section, key, value))
            written.add(key)

        for target, choice in resolution.bindings.items():
            if not target.startswith("ps2."):
                continue
            spec = self.table["targets"].get(target)
            if spec is None:
                out.warnings.append(f"pcsx2: no key for {target}")
                continue
            if "keys" in spec:
                for key, value in self._axis_values(player, target, spec["keys"], choice.value, device, out):
                    put(key, value)
            else:
                value = self._button_value(target, choice.value, device or self._device(section, spec["key"], player),
                                           out)
                if value is not None:
                    put(spec["key"], value)
        self._render_options(player, resolution, device, put, out)
        return written

    def _button_value(self, target: str, source: dict, device: str, out: Rendered) -> Optional[str]:
        if "chord" in source:
            tokens = [self._token(i, out) for i in source["chord"]]
            return None if None in tokens else " & ".join(f"{device}/{t}" for t in tokens)
        name = source["input"]
        if name == "none":
            return ""        # an empty value binds nothing (InputManager::SplitChord)
        if name in AXES:
            out.warnings.append(f"pcsx2: {target} is a button; bind a half-axis (e.g. {name[:2]}_up), not {name}")
            return None
        token = self._token(name, out)
        return None if token is None else f"{device}/{token}"

    def _axis_values(self, player: int, target: str, keys: dict, source: dict, device: Optional[str],
                     out: Rendered) -> list:
        name = source.get("input")
        if name == "none":
            return [(keys["neg"], ""), (keys["pos"], "")]
        token = self.tokens.get(name)
        if not isinstance(token, dict) or "neg" not in token:
            out.warnings.append(f"pcsx2: {target} needs a full axis (ls_x, ls_y, rs_x, rs_y), got {name!r}")
            return []
        neg, pos = token["neg"], token["pos"]
        if source.get("invert"):
            neg, pos = pos, neg
        pad = lambda key: device or self._device(f"Pad{player}", key, player)
        return [(keys["neg"], f"{pad(keys['neg'])}/{neg}"), (keys["pos"], f"{pad(keys['pos'])}/{pos}")]

    def _render_options(self, player: int, resolution: Resolution, device: Optional[str], put, out: Rendered) -> None:
        options = {k: c.value for k, c in resolution.options.items()}
        section = f"Pad{player}"
        if "rumble.enabled" in options:
            for motor, key in self.table["options"]["rumble"]["keys"].items():
                if not options["rumble.enabled"]:
                    put(key, "")
                elif not self._current(FILE, section, key):   # keep an existing motor binding
                    token = self.table["rumble_tokens"][motor]
                    put(key, f"{device or self._device(section, key, player)}/{token}")
        dz = {k: options[f"deadzones.{k}"] for k in ("ls", "rs") if f"deadzones.{k}" in options}
        if dz:
            # One Deadzone for both sticks: the larger of the two wins.
            if len(set(dz.values())) > 1:
                out.warnings.append(f"pcsx2: Pad{player} has one stick deadzone for both sticks; using the larger "
                                    f"({max(dz.values())})")
            spec = self.table["options"]["deadzone"]["stick"]
            value = min(max(max(dz.values()), spec["range"][0]), spec["range"][1])
            put(spec["key"], f"{value:.6f}")
        if "controller_type" in options:
            spec = self.table["options"]["controller_type"]
            name = options["controller_type"]
            value = spec["values"].get(name) or spec["values"].get(f"ps2.{name}")
            if value is None:
                out.warnings.append(f"pcsx2: controller type {name!r} is not supported")
            else:
                put(spec["key"], value)

    def _check_type(self, player: int, written: set, out: Rendered) -> None:
        """PCSX2 skips the bindings of a pad whose Type is None (InputManager::AddPadBindings)."""
        key = self.table["options"]["controller_type"]["key"]
        if key in written:
            return
        value = self._current(FILE, f"Pad{player}", key)
        if value is None:   # PCSX2's defaults: Pad1 DualShock2, the others None (Pad.cpp)
            value = "DualShock2" if player == 1 else "None"
        if value == "None":
            out.warnings.append(f"pcsx2: [Pad{player}] Type is None, so PCSX2 ignores player {player}'s bindings; "
                                f"set options.controller_type to dualshock2")

    # -- hotkeys ---------------------------------------------------------------

    def _render_hotkeys(self, resolution: Resolution, device: Optional[str], out: Rendered) -> set:
        spec = self.table["hotkeys"]
        written = set()
        for target, choice in resolution.bindings.items():
            if not target.startswith("hotkey."):
                continue
            key = spec["targets"].get(target)
            if key is None:
                out.warnings.append(f"pcsx2: no hotkey for {target}")
                continue
            source = choice.value
            tokens = [self._token(i, out) for i in (source.get("chord") or [source["input"]])]
            if None in tokens:
                continue
            pad = device or self._device(spec["section"], key, 1)
            # Replaces the whole value, including a keyboard binding such as HoldTurbo = Keyboard/Period.
            out.patches.append(Patch(FILE, spec["section"], key, " & ".join(f"{pad}/{t}" for t in tokens)))
            written.add(key)
        return written

    # -- show ------------------------------------------------------------------

    def describe(self, player: int, after: Callable, system: str = "ps2"):
        """What player's [PadN] drives once the patches are written (after: as current, after the write). A binding
        names its pad (SDL-<n>/<control>); keyboard bindings and chords (` & `) don't count."""
        from ..show import Described
        out = Described(port=player if player <= PORTS else None)
        if system not in self.systems or out.port is None:
            return out
        by_token = {t: name for name, t in self.tokens.items() if isinstance(t, str)}
        section = f"Pad{player}"
        for target, spec in self.table["targets"].items():
            for key in spec["keys"].values() if "keys" in spec else [spec["key"]]:
                value = after(FILE, section, key) or ""
                found = _SDL_REF.match(value)
                if found and "&" not in value and value[found.end():] in by_token:
                    out.drives.append((by_token[value[found.end():]], target,
                                       ("emulator", "PCSX2.ini", after.patched(FILE, section, key))))
        source = lambda key: (("emulator", "PCSX2 default", False) if after(FILE, section, key) is None
                              else ("emulator", "PCSX2.ini", after.patched(FILE, section, key)))
        large = self.table["options"]["rumble"]["keys"]["large"]
        out.options.append(("rumble.enabled", bool(after(FILE, section, large)), source(large), player))
        spec = self.table["options"]["deadzone"]["stick"]
        raw = after(FILE, section, spec["key"])
        for option in ("deadzones.ls", "deadzones.rs"):         # one Deadzone for both sticks
            out.options.append((option, round(float(raw), 4) if raw else spec["default"], source(spec["key"]),
                                player))
        return out

    # -- helpers ---------------------------------------------------------------

    def _repoint(self, section: str, keys: list, device: str, out: Rendered) -> None:
        """Move every SDL pad reference in these keys to `device`; keyboard and mouse bindings stay as they are."""
        for key in keys:
            value = self._current(FILE, section, key)
            if value and _SDL_REF.search(value):
                new = _SDL_REF.sub(f"{device}/", value)
                if new != value:
                    out.patches.append(Patch(FILE, section, key, new))

    def _device(self, section: str, key: str, player: int) -> str:
        """The pad a key already names, else EmuDeck's numbering (PadN on SDL-<N-1>, hotkeys on SDL-0)."""
        found = _SDL_REF.search(self._current(FILE, section, key) or "")
        n = int(found.group(1)) if found else player - 1
        return self.table["device_ref"]["format"].format(player_index=n)

    def _token(self, name: str, out: Rendered) -> Optional[str]:
        token = self.tokens.get(name)
        if not isinstance(token, str):
            out.warnings.append(f"pcsx2: physical input {name!r} has no single PCSX2 token")
            return None
        return token


def _steam_slot(joystick: Joystick) -> Optional[int]:
    """The N in a Steam virtual pad's evdev name "Microsoft X-Box 360 pad N" (SDL's GetSteamVirtualGamepadSlot)."""
    if joystick.device.vid_pid != STEAM_VIRTUAL_PAD:
        return None
    found = _VIRTUAL_SLOT.search(joystick.device.name)
    return int(found.group(1)) if found else None
