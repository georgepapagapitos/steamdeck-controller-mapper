"""Dolphin adapter, GameCube pads + hotkeys (prototype). See docs/adapters/dolphin.md.

All emulator facts come from data/adapters/dolphin.json. This module only
translates resolved canonical bindings into those tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..resolve import Resolution
from ..store import load_json
from ..writer import Patch

TABLE = Path(__file__).resolve().parents[3] / "data" / "adapters" / "dolphin.json"
_LETTERS_ONLY = re.compile(r"^[A-Za-z]+$")
AXES = ("ls_x", "ls_y", "rs_x", "rs_y")


@dataclass
class Rendered:
    patches: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class DolphinAdapter:
    id = "dolphin"
    systems = {"gc"}          # Wii targets exist in the table; rendering them is not prototyped yet

    def __init__(self, table: Optional[dict] = None):
        self.table = table or load_json(TABLE)
        self.tokens = self.table["physical_tokens"]

    @property
    def managed_keys(self) -> dict:
        managed = dict(self.table["managed_keys"])
        hotkeys = [k for k in self.table["hotkeys"]["targets"].values() if k]
        managed["Hotkeys.ini"] = {**managed["Hotkeys.ini"], "keys": ["Device", *hotkeys]}
        return managed

    def render(self, players: dict[int, Resolution], system: str = "gc",
               current: Optional[Callable[[str, str, str], Optional[str]]] = None) -> Rendered:
        """players: 1-based player number -> resolution for that player's controller.
        current(file, section, key) returns the value on disk, so we can avoid needless rewrites."""
        self._current = current or (lambda *_: None)
        out = Rendered()
        if system not in self.systems:
            out.warnings.append(f"dolphin: rendering for {system!r} is not implemented")
            return out
        for player, resolution in sorted(players.items()):
            self._render_pad(player, resolution, out)
            if player == 1:
                self._render_hotkeys(resolution, out)
        return out

    # -- pads ------------------------------------------------------------------

    def _render_pad(self, player: int, resolution: Resolution, out: Rendered) -> None:
        for target, choice in resolution.bindings.items():
            if not target.startswith("gc."):
                continue
            spec = self.table["targets"].get(target)
            if spec is None:
                out.warnings.append(f"dolphin: no key for {target}")
                continue
            section = spec["section"].format(n=player)
            if "keys" in spec:
                for key, value in self._axis_values(target, spec["keys"], choice.value, out):
                    out.patches.append(Patch(spec["file"], section, key, value))
            else:
                value = self._button_value(target, choice.value, out)
                if value is not None:
                    out.patches.append(Patch(spec["file"], section, spec["key"], value))
        self._render_options(player, resolution, out)

    def _button_value(self, target: str, source: dict, out: Rendered) -> Optional[str]:
        if "chord" in source:
            return " & ".join(self._quote(self._token(i, out)) for i in source["chord"])
        name = source["input"]
        if name == "none":
            return ""
        if name in AXES:
            out.warnings.append(f"dolphin: {target} is a button; bind a half-axis (e.g. {name[:2]}_up), not {name}")
            return None
        token = self._token(name, out)
        return None if token is None else self._quote(token)

    def _axis_values(self, target: str, keys: dict, source: dict, out: Rendered) -> list:
        name = source.get("input")
        if name == "none":
            return [(keys["neg"], ""), (keys["pos"], "")]
        token = self.tokens.get(name)
        if not isinstance(token, dict) or "neg" not in token:
            out.warnings.append(f"dolphin: {target} needs a full axis (ls_x, ls_y, rs_x, rs_y), got {name!r}")
            return []
        neg, pos = token["neg"], token["pos"]
        if source.get("invert"):
            neg, pos = pos, neg
        return [(keys["neg"], self._quote(neg)), (keys["pos"], self._quote(pos))]

    def _render_options(self, player: int, resolution: Resolution, out: Rendered) -> None:
        options = {k: c.value for k, c in resolution.options.items()}
        section = f"GCPad{player}"
        if "rumble.enabled" in options:
            rumble = self.table["options"]["rumble"]
            existing = self._current("GCPadNew.ini", section, "Rumble/Motor")
            if not options["rumble.enabled"]:
                out.patches.append(Patch("GCPadNew.ini", section, "Rumble/Motor", rumble["off"]))
            elif not existing:   # keep an existing motor binding such as EmuDeck's "Strong"
                out.patches.append(Patch("GCPadNew.ini", section, "Rumble/Motor", rumble["on"]))
        deadzones = self.table["options"]["deadzone"]
        for option, dz_key in (("deadzones.ls", "gc.main_stick"), ("deadzones.rs", "gc.c_stick")):
            if option in options:
                spec = deadzones[dz_key]
                percent = min(max(options[option] * 100, spec["range"][0]), spec["range"][1])
                out.patches.append(Patch("GCPadNew.ini", section, spec["key"], f"{percent:.2f}"))

    # -- hotkeys ---------------------------------------------------------------

    def _render_hotkeys(self, resolution: Resolution, out: Rendered) -> None:
        spec = self.table["hotkeys"]
        for target, choice in resolution.bindings.items():
            if not target.startswith("hotkey."):
                continue
            key = spec["targets"].get(target)
            if key is None:
                out.warnings.append(f"dolphin: no hotkey for {target}")
                continue
            source = choice.value
            inputs = source.get("chord") or [source["input"]]
            tokens = [self._token(i, out) for i in inputs]
            if None in tokens:
                continue
            quoted = [self._quote(t) for t in tokens]
            # Ordered chord, the form EmuDeck's Hotkeys.ini uses: @(Back+`Button S`).
            # Replaces the whole value, including keyboard alternatives such as @(Alt+Return)|...
            value = f"@({'+'.join(quoted)})" if len(quoted) > 1 else quoted[0]
            out.patches.append(Patch(spec["file"], spec["section"], key, value))

    # -- helpers ---------------------------------------------------------------

    def _token(self, name: str, out: Rendered) -> Optional[str]:
        token = self.tokens.get(name)
        if not isinstance(token, str):
            out.warnings.append(f"dolphin: physical input {name!r} has no single Dolphin token")
            return None
        return token

    @staticmethod
    def _quote(token: str) -> str:
        """Backticks unless the name is letters only (MappingCommon::GetExpressionForControl)."""
        return token if _LETTERS_ONLY.match(token) else f"`{token}`"
