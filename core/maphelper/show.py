"""What each button does: `map-helper show` and $STATE/last-launch.json (docs/08 "The data", schema 1).

One document for both. The pipeline hands over its Context once the patches are rendered; document() reads the
config as it will be after the write (After: the live values with the patches over them) through each adapter's
describe(), and says where each binding comes from: a rule, the emulator's own config or default, or EmuDeck.
Nothing here probes or parses again what the pipeline already has, so mh-run can afford it at every launch.

No device ids, MACs, serials or Steam handles go into it: only names, model ids and slot numbers.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import DATA
from .store import load_json
from .writer import is_managed

SCHEMA = 1
LAST = "last-launch.json"
STICK_PARTS = {"ls": ("ls_x", "ls_y", "ls_up", "ls_down", "ls_left", "ls_right"),
               "rs": ("rs_x", "rs_y", "rs_up", "rs_down", "rs_left", "rs_right")}
OPTION_LABELS = {"deadzones.ls": "Stick deadzone", "deadzones.rs": "Right stick deadzone", "rumble.enabled": "Rumble"}
PAKS = {"rumble": "Rumble pak", "memory": "Memory pak", "transfer": "Transfer pak", "none": "No pak"}


@dataclass
class Described:
    """One player's pad as an adapter reads it from the after-write config. A source is (kind, detail, patched):
    kind emulator or emudeck, patched when this run's patches set the value (then a rule may have)."""
    port: Optional[int] = None
    drives: list = field(default_factory=list)     # (physical input, target, source)
    notes: dict = field(default_factory=dict)      # physical input -> (text, source, short text for a list row)
    chords: list = field(default_factory=list)     # (physical input, target, physical input to hold, source)
    options: list = field(default_factory=list)    # (option key, canonical value, source, player whose rules set it)


class After:
    """after(file, section, key): the value once this run's patches are written. A file the writer would create
    from a seed reads as the seed until a patch says otherwise."""

    def __init__(self, current: Callable, patches: list, managed: dict, config_root: Path, seeds: Optional[dict]):
        self.current, self.root, self.seeds = current, Path(config_root), seeds or {}
        self.values = {(p.file, p.section, p.key): p.value for p in patches if is_managed(p, managed)}
        self.files = {f for f, _, _ in self.values}

    def __call__(self, file: str, section: Optional[str], key: str) -> Optional[str]:
        if (file, section, key) in self.values:
            return self.values[file, section, key]
        if file in self.seeds and not (self.root / file).exists():
            file = self.seeds[file]
        return self.current(file, section, key)

    def patched(self, file: str, section: Optional[str], key: str) -> bool:
        return (file, section, key) in self.values


def document(ctx, glyphs: Optional[dict] = None) -> dict:
    """system_name, policy, players and warnings for a pipeline Context; assemble() adds the launch."""
    glyphs = glyphs or load_json(DATA / "glyphs.json")
    rendering = ctx.rendering
    after = After(ctx.current, rendering.rendered.patches, rendering.managed, ctx.req.config_root,
                  getattr(rendering.rendered, "seeds", None))
    rules = {r.id: r for r in ctx.rules}
    warnings = [w for p in ctx.players.values() for w in p.warnings] + rendering.rendered.warnings + rendering.checks
    players = []
    for n, controller in sorted(ctx.controllers.items()):
        joystick = ctx.assigned.get(n)
        described = rendering.describe(n, after) if rendering.describe else Described()
        source = _Sources(ctx, rules, n)
        inputs = _inputs(controller, glyphs, described, source, ctx.layout,
                         behind_steam=joystick is None or joystick.slot is not None, warnings=warnings, player=n)
        options = [{"key": key, "value": value, "label": _option_label(key, value),
                    "source": source.option(key, src, by)} for key, value, src, by in described.options]
        players.append({"player": n, "pad": _pad(ctx, controller, joystick, glyphs, described.port),
                        "inputs": inputs, "options": options})
    policy = None
    if ctx.probe is not None:
        policy = {"name": ctx.probe.policy, "reason": ctx.probe.policy_reason}
    return {"system_name": (ctx.layout or {}).get("name"), "policy": policy, "players": players,
            "warnings": list(dict.fromkeys(warnings))}


def assemble(launch: dict, shown: dict) -> dict:
    """The schema 1 document: launch (ts, mode, emulator, core, system, game, ms, outcome, detail) + document()."""
    launch = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **launch}
    keys = ("ts", "mode", "emulator", "core", "system", "system_name", "game", "ms", "outcome", "detail")
    launch["system_name"] = shown.get("system_name")
    return {"schema": SCHEMA, "launch": {k: launch.get(k) for k in keys}, "policy": shown.get("policy"),
            "players": shown.get("players", []), "warnings": shown.get("warnings", [])}


def _pad(ctx, controller, joystick, glyphs: dict, port: Optional[int]) -> dict:
    family = ctx.db.families.get(controller.family or "", {})
    name = joystick.slot.name if joystick is not None and joystick.slot else (joystick.name if joystick else "")
    if not name or name.startswith("#"):      # the Deck's slot is "#SettingsController_SteamController" on the desktop
        name = family.get("name") or controller.name or "Unknown controller"
    return {"name": name, "model": controller.model, "family": controller.family, "style": controller.style,
            "shape": glyphs["shapes"].get(controller.style, "generic"),
            "steam_slot": joystick.slot.slot if joystick is not None and joystick.slot else None,
            "emulator_port": port}


def _has(controller, name: str) -> bool:
    caps = controller.capabilities
    if name.startswith("paddle"):
        return "paddles" in caps or name in caps
    if name in ("misc1", "touchpad_click"):
        return name in caps
    return True


def _inputs(controller, glyphs: dict, described: Described, source: "_Sources", layout: Optional[dict],
            behind_steam: bool, warnings: list, player: int) -> list:
    style = glyphs["shapes"].get(controller.style, "generic")
    table = {**glyphs["styles"]["generic"], **glyphs["styles"].get(style, {}),
             **glyphs["families"].get(controller.family or "", {})}
    shared = _shared(layout)
    out = []
    for name in glyphs["order"]:
        if not _has(controller, name):
            continue
        glyph, label = table[name]
        row = {"input": name, "glyph": glyph, "name": label, "drives": []}
        if behind_steam and name in glyphs["steam_only"]:
            row["steam_only"] = True
            out.append(row)
            continue
        parts = STICK_PARTS.get(name, (name,))
        seen = set()
        for physical, target, src in described.drives:
            if physical in parts and target not in seen:
                seen.add(target)
                row["drives"].append({"target": target, "label": _target_label(target, layout),
                                      "source": source.binding(target, physical, src)})
        note = next((described.notes[p] for p in parts if p in described.notes), None)
        chord = next(((t, hold, src) for p, t, hold, src in described.chords if p in parts), None)
        if chord:
            # Mupen64Plus-Next's face buttons give C buttons while R2 is held: say so, in the pad's own glyph, on a
            # row that otherwise reads "Nothing".
            label, hold = _target_label(chord[0], layout), table.get(chord[1], (chord[1],))[0]
            text, short = f"{label} while {hold} is held (the core's C-button modifier)", f"{label} with {hold} held"
            note = (f"{note[0]}; {text}", note[1], f"{note[2]}; {short}") if note else (text, chord[2], short)
        if note:
            row["note"], row["note_source"] = note[0], source.note(name, note[1])
            row["note_short"] = note[2]
        if name not in STICK_PARTS and len(seen) > 1 and frozenset(seen) not in shared:
            warnings.append(f"player {player}: {name} drives several inputs: {', '.join(sorted(seen))}")
        out.append(row)
    return out


def _shared(layout: Optional[dict]) -> set:
    """The layout's allow_shared_sources pairs (GC L and L-Analog on one trigger), as sets of targets."""
    if not layout:
        return set()
    pad = layout["default_controller"]
    return {frozenset(f"{layout['system']}.{pad}.{p}" for p in pair.split("+"))
            for pair in layout["controllers"].get(pad, {}).get("allow_shared_sources", [])}


def _target_label(target: str, layout: Optional[dict]) -> str:
    name = target.rsplit(".", 1)[-1]
    if layout and name in layout.get("glyphs", {}):
        return layout["glyphs"][name]
    pad = (layout or {}).get("controllers", {}).get((layout or {}).get("default_controller", ""), {})
    if name in pad.get("dpad", []):
        return f"D-pad {name}"
    return name.replace("_", " ").title().replace("Lstick", "Left stick").replace("Rstick", "Right stick")


def _option_label(key: str, value) -> str:
    if key == "pak":
        return PAKS.get(value, f"{value} pak")
    return OPTION_LABELS.get(key, key)


class _Sources:
    """The `source` objects of one player's rows."""

    def __init__(self, ctx, rules: dict, player: int):
        self.ctx, self.rules, self.player = ctx, rules, player
        self.resolution = ctx.players.get(player)

    def binding(self, target: str, physical: str, src: tuple) -> dict:
        choice = self.resolution.bindings.get(target) if self.resolution else None
        if choice is not None and _same_input(choice.value.get("input"), physical):
            return self.rule(choice.rule_id)
        return self.plain(src)

    def option(self, key: str, src: tuple, by: int) -> dict:
        resolution = self.ctx.players.get(by)
        choice = resolution.options.get(key) if resolution else None
        return self.rule(choice.rule_id) if choice is not None and src[2] else self.plain(src)

    def note(self, physical: str, src: tuple) -> dict:
        """A patched note (RetroArch's hotkey enable) comes from the hotkey rule that put a chord on this input."""
        if src[2]:
            for key, choice in sorted((self.ctx.players.get(1) or self.resolution).bindings.items()):
                if key.startswith("hotkey.") and physical in (choice.value.get("chord") or []):
                    return self.rule(choice.rule_id)
        return self.plain(src)

    def rule(self, rule_id: str) -> dict:
        rule = self.rules.get(rule_id)
        return {"kind": "rule", "rule_id": rule_id, "rule_label": rule.label if rule else "",
                "scope": scope_words(rule, self.ctx) if rule else ""}

    @staticmethod
    def plain(src: tuple) -> dict:
        return {"kind": src[0], "detail": src[1]}


def _same_input(rule_input: Optional[str], physical: str) -> bool:
    """A rule's full axis (ls_x) covers both of its halves (ls_left, ls_right)."""
    if rule_input == physical:
        return True
    return rule_input in ("ls_x", "rs_x") and physical in (f"{rule_input[:2]}_left", f"{rule_input[:2]}_right") \
        or rule_input in ("ls_y", "rs_y") and physical in (f"{rule_input[:2]}_up", f"{rule_input[:2]}_down")


def scope_words(rule, ctx) -> str:
    """"all Nintendo 64 games, any pad"."""
    return describe_scope(rule.controller, rule.content, (ctx.layout or {}).get("name"), ctx.db)


def describe_scope(pad, content, system_name: Optional[str], db) -> str:
    """A rule's scope in words, from its ControllerScope and ContentScope. A device is "one pad", never its id."""
    system = system_name or content.system or ""
    games = {"global": "all games",
             "system": f"all {system} games",
             "emulator": f"{system} games in {content.emulator}" if content.system else f"all {content.emulator} games",
             "game": f"only {content.game_id}"}[content.level]
    if pad.level == "any":
        who = "any pad"
    elif pad.level == "device":
        who = "one pad"
    elif pad.level == "family":
        who = db.families.get(pad.value, {}).get("name", pad.value) + " pads"
    elif pad.level == "brand":
        who = db.doc.get("brands", {}).get(pad.value, {}).get("name", pad.value) + " pads"
    else:
        who = f"{pad.value} pads"
    return f"{games}, {who}"


# -- last-launch.json -------------------------------------------------------------

def last_launch(entry: dict) -> dict:
    """mh-run's log entry (and the document it built, under "show") -> the last-launch.json document."""
    if "error" in entry:
        outcome, detail = "error", entry["error"]
    elif "skipped" in entry:
        outcome, detail = "skipped", entry["skipped"]
    else:
        outcome = "changed" if entry.get("changed") else "no-changes"
        detail = ", ".join(entry.get("changed") or [])
    launch = {k: entry.get(k) for k in ("mode", "emulator", "core", "system", "game", "ms")}
    return assemble({**launch, "outcome": outcome, "detail": detail}, entry.get("show") or {})


def write_last(state_dir: Path, doc: dict) -> None:
    """Atomic replace, so the plugin never reads half a file."""
    path = Path(state_dir) / LAST
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{LAST}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_last(state_dir: Path) -> Optional[dict]:
    path = Path(state_dir) / LAST
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


# -- text --------------------------------------------------------------------------

def render(doc: dict) -> str:
    """The readable form of `show` (and `show --last`)."""
    launch = doc["launch"]
    head = " · ".join(str(v) for v in (launch.get("emulator") if not launch.get("core")
                                        else f"{launch['emulator']} ({launch['core']})",
                                        launch.get("system_name") or launch.get("system"), launch.get("game")) if v)
    lines = [head, f"{launch['mode']} {launch.get('ts', '')}: {launch['outcome']}"
             + (f" ({launch['detail']})" if launch.get("detail") else "")
             + (f", {launch['ms']} ms" if launch.get("ms") is not None else "")]
    if doc.get("policy"):
        lines.append(f"policy: {doc['policy']['name']} ({doc['policy']['reason']})")
    for p in doc["players"]:
        pad = p["pad"]
        where = [pad["model"] or "unknown model"]
        if pad["steam_slot"] is not None:
            where.append(f"steam slot {pad['steam_slot']}")
        where.append(f"port {pad['emulator_port']}" if pad["emulator_port"] else "no port in the emulator")
        lines.append(f"\nPlayer {p['player']}: {pad['name']} ({', '.join(where)})")
        steam = []
        for row in p["inputs"]:
            if row.get("steam_only"):
                steam.append(f"{row['glyph']}")
                continue
            what = ", ".join(d["label"] for d in row["drives"]) or "-"
            why = "; ".join(dict.fromkeys(_source_text(d["source"]) for d in row["drives"]))
            if row.get("note"):
                why = "; ".join(filter(None, (why, f"{row['note']} [{_source_text(row['note_source'])}]")))
            lines.append(f"  {row['glyph']:<8} {row['name']:<18} {what:<22} {why}".rstrip())
        if steam:
            lines.append(f"  not seen by emulators (set them in Steam Input): {' '.join(steam)}")
        for o in p["options"]:
            lines.append(f"  option {o['key']} = {o['value']} ({o['label']}): {_source_text(o['source'])}")
    for w in doc.get("warnings", []):
        lines.append(f"warning: {w}")
    return "\n".join(lines) + "\n"


def _source_text(source: dict) -> str:
    if source["kind"] == "rule":
        return f"rule {source['rule_id']} ({source['scope']})"
    return f"{source['kind']}: {source['detail']}"
