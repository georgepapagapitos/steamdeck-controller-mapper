"""Canonical data model. See docs/03-canonical-model.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

PHYSICAL_INPUTS = frozenset({
    "face_south", "face_east", "face_west", "face_north",
    "dpad_up", "dpad_down", "dpad_left", "dpad_right",
    "l1", "r1", "l2", "r2", "l3", "r3",
    "ls_x", "ls_y", "rs_x", "rs_y",
    "ls_up", "ls_down", "ls_left", "ls_right",
    "rs_up", "rs_down", "rs_left", "rs_right",
    "start", "select", "guide", "misc1",
    "paddle1", "paddle2", "paddle3", "paddle4",
    "touchpad_click", "touchpad", "gyro", "accel",
    "none",
})

# Physical inputs that only exist on controllers with a given capability.
INPUT_CAPABILITY = {
    "paddle1": "paddles", "paddle2": "paddles", "paddle3": "paddles", "paddle4": "paddles",
    "touchpad": "touchpad", "touchpad_click": "touchpad_click",
    "gyro": "gyro", "accel": "accel", "misc1": "misc1",
}

CONTROLLER_LEVELS = ("device", "model", "family", "brand", "style", "any")
CONTENT_LEVELS = ("game", "emulator", "system", "global")
SOURCES = ("shipped", "pack", "user")

SOURCE_RANK = {"shipped": 1, "pack": 2, "user": 3}
CONTROLLER_RANK = {"any": 1, "style": 2, "brand": 3, "family": 4, "model": 5, "device": 6}


@dataclass(frozen=True)
class ControllerScope:
    level: str
    value: Optional[str] = None


@dataclass(frozen=True)
class ContentScope:
    level: str
    system: Optional[str] = None
    emulator: Optional[str] = None
    game_id: Optional[str] = None

    @property
    def rank(self) -> int:
        if self.level == "game":
            return 5
        if self.level == "emulator":
            return 4 if self.system else 3
        if self.level == "system":
            return 2
        return 1


@dataclass
class Rule:
    id: str
    controller: ControllerScope
    content: ContentScope
    source: str = "user"
    label: str = ""
    enabled: bool = True
    explicit_priority: int = 0
    requires: tuple = ()
    bindings: dict = field(default_factory=dict)   # key -> source expression (dict)
    options: dict = field(default_factory=dict)    # nested options object
    path: Optional[str] = None                     # file it was loaded from


@dataclass(frozen=True)
class Controller:
    """A connected physical controller, classified against the controller DB."""
    device_ids: tuple                  # every linked identity, e.g. ("mac:aa:..", "path:054c:0ce6:..")
    model: Optional[str] = None
    family: Optional[str] = None
    brand: Optional[str] = None
    style: str = "generic"
    capabilities: frozenset = frozenset()
    name: str = ""

    def matches(self, scope: ControllerScope) -> bool:
        if scope.level == "any":
            return True
        if scope.level == "device":
            return scope.value in self.device_ids
        return getattr(self, scope.level) == scope.value


@dataclass(frozen=True)
class Target:
    """What is being launched."""
    system: str
    emulator: Optional[str] = None
    game_id: Optional[str] = None

    def matches(self, scope: ContentScope) -> bool:
        if scope.level == "global":
            return True
        if scope.level == "system":
            return scope.system == self.system
        if scope.level == "emulator":
            return scope.emulator == self.emulator and scope.system in (None, self.system)
        if scope.level == "game":
            return (scope.system == self.system and scope.game_id == self.game_id
                    and scope.emulator in (None, self.emulator))
        return False


def flatten_options(options: dict, prefix: str = "") -> dict:
    """{"rumble": {"enabled": True}} -> {"rumble.enabled": True}. Options merge per leaf key."""
    flat: dict[str, Any] = {}
    for key, value in options.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten_options(value, path + "."))
        else:
            flat[path] = value
    return flat
