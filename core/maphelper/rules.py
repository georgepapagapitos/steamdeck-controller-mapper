"""Editing the user's rules: "Change button", "Back to default", the resets and the rules list of the Decky plugin
(docs/08 Flow 2 and Flow 4). `map-helper rules` runs these, and the plugin's backend runs that.

Rules live in $DATA/rules, which mh-run loads, and $DATA/rules-off, which nothing loads: a rule there is parked
(off). A rule is on when its file is in rules/ and it doesn't say `"enabled": false`. Every write checks each rule
in the file against the schema (validate.validate_rule), replaces the file atomically, and refuses any path outside
those two folders.

Changes made here go into one rule per scope, `edit.<pads>.<system>.<games>` ("Button map changes"), unless a rule
of the user's with exactly that scope already sets the console input: then that rule is changed. Two rules with one
scope tie, and the tie goes to the later id, not to the newer change (resolve.score).

An edit is a list of ops, so a swap is one edit and its undo is one edit too:
  {"op": "set", "target": "n64.standard.c_down", "source": {"input": "face_north"},
   "scope": {"controller": {"level": "any"}, "content": {"level": "system", "system": "n64"}}}
  {"op": "set", ..., "rule": "<id>"}        into that rule instead of the scope's
  {"op": "unset", "target": ..., "rule": "<id>"}
A device scope names no device: {"level": "device", "player": 2, "model": "sony.dualsense"} is filled in from the
pads connected now, so no device id ever reaches the plugin.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import DATA
from .model import PHYSICAL_INPUTS
from .store import load_layouts, rule_from_doc
from .validate import ID_RE, validate_rule

DATA_HOME = Path.home() / ".local" / "share" / "map-helper"
RULES_DIR = DATA_HOME / "rules"            # $DATA/rules (docs/09); mh-run's USER_RULES
OFF_DIR = DATA_HOME / "rules-off"
EDIT_PREFIX = "edit."
EDIT_LABEL = "Button map changes"


class RuleError(Exception):
    """The change can't be made; nothing was written."""


@dataclass
class Entry:
    doc: dict
    path: Path
    index: Optional[int]          # position in a {"rules": [...]} bundle; None for a one-rule file
    parked: bool                  # in rules-off/

    @property
    def id(self) -> str:
        return self.doc["id"]

    @property
    def on(self) -> bool:
        return not self.parked and self.doc.get("enabled", True) is not False


@dataclass
class Book:
    """Every rule in the two folders, and the files they came from (written back whole)."""
    rules_dir: Path = RULES_DIR
    off_dir: Path = OFF_DIR
    entries: list = field(default_factory=list)
    problems: list = field(default_factory=list)     # (file name, message): unreadable or invalid, left alone
    files: dict = field(default_factory=dict)        # path -> the file's document (a rule, or a bundle)

    def __post_init__(self):
        self.rules_dir, self.off_dir = Path(self.rules_dir), Path(self.off_dir)
        for folder, parked in ((self.rules_dir, False), (self.off_dir, True)):
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*.json")):
                try:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    self.problems.append((path.name, f"unreadable: {e}"))
                    continue
                bundle = isinstance(doc, dict) and isinstance(doc.get("rules"), list)
                items = doc["rules"] if bundle else [doc]
                bad = [e for item in items for e in validate_rule(item)]
                if bad:
                    self.problems.append((path.name, "; ".join(bad)))
                    continue
                self.files[path] = doc
                self.entries += [Entry(item, path, i if bundle else None, parked) for i, item in enumerate(items)]

    def get(self, rule_id: str) -> Entry:
        found = [e for e in self.entries if e.id == rule_id]
        if not found:
            raise RuleError(f"no rule {rule_id!r}")
        return found[0]

    def ids(self) -> set:
        return {e.id for e in self.entries}

    # -- writing -----------------------------------------------------------------------------------------------

    def _check(self, path: Path) -> Path:
        """path, if it is a .json file directly or deeper inside one of the two folders and not a symlink."""
        path = Path(path)
        if path.suffix != ".json" or path.is_symlink():
            raise RuleError(f"refusing to write {path.name}: not a plain .json rule file")
        real = path.parent.resolve() / path.name
        for folder in (self.rules_dir, self.off_dir):
            base = folder.resolve()          # not strict: resolves what exists of it, as for path
            if real.parent == base or base in real.parents:
                return path
        raise RuleError(f"refusing to write outside the rule folders: {path}")

    def save(self, path: Path) -> None:
        """Write one file back from self.files, or delete it when it holds no rule any more."""
        path = self._check(path)
        doc = self.files[path]
        items = doc["rules"] if isinstance(doc, dict) and isinstance(doc.get("rules"), list) else [doc]
        if not items:
            path.unlink()
            del self.files[path]
            return
        problems = [f"{item.get('id')}: {e}" for item in items for e in validate_rule(item)]
        if problems:
            raise RuleError("the rule would be invalid: " + "; ".join(problems))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def add(self, doc: dict) -> Entry:
        path = self._check(self.rules_dir / f"{doc['id']}.json")
        if path.exists() or path in self.files:
            raise RuleError(f"{path.name} already exists")
        self.files[path] = doc
        entry = Entry(doc, path, None, False)
        self.entries.append(entry)
        return entry

    def remove(self, entry: Entry) -> None:
        doc = self.files[entry.path]
        if entry.index is None:
            self.files[entry.path] = {"rules": []}
        else:
            doc["rules"] = [r for r in doc["rules"] if r is not entry.doc]
        self.entries.remove(entry)
        self.save(entry.path)

    def move(self, path: Path, parked: bool) -> Path:
        """Move a file between rules/ and rules-off/ (same name), keeping its entries pointed at it."""
        source = self._check(path)
        folder = self.off_dir if parked else self.rules_dir
        dest = self._check(folder / source.name)
        if dest.exists():
            raise RuleError(f"{dest.name} is already in {folder.name}/")
        self.files[dest] = self.files.pop(source)
        for entry in self.entries:
            if entry.path == source:
                entry.path, entry.parked = dest, parked
        self.save(dest)
        source.unlink()
        return dest


# -- edits ---------------------------------------------------------------------------------------------------------

def edit(book: Book, ops: list, devices: Optional[Callable[[int, Optional[str]], str]] = None,
         layouts: Optional[dict] = None) -> dict:
    """Carry out ops; returns {"rules": [ids touched], "undo": [ops]}. devices(player, model) gives the device id of
    the pad that is that player now (RuleError when it isn't that model)."""
    layouts = layouts if layouts is not None else load_layouts(DATA / "layouts")
    touched, undo = [], []
    for op in _checked(ops, layouts):
        if op["op"] == "unset":
            entry = book.get(op["rule"])
            bindings = entry.doc.get("bindings", {})
            if op["target"] not in bindings:
                raise RuleError(f"{entry.id} doesn't set {op['target']}")
            previous = bindings.pop(op["target"])
            undo.insert(0, {"op": "set", "target": op["target"], "source": previous, "rule": entry.id})
            if not bindings:
                entry.doc.pop("bindings")
            # An empty edit rule is clutter: remove it, and undo makes it again in the same scope. Not one for a
            # device: its undo couldn't name the scope without the device id, so it stays, empty.
            applies = entry.doc["applies_to"]
            if (entry.id.startswith(EDIT_PREFIX) and not entry.doc.get("bindings") and not entry.doc.get("options")
                    and applies["controller"]["level"] != "device"):
                book.remove(entry)
                undo[0] = {"op": "set", "target": op["target"], "source": previous, "scope": applies}
            else:
                book.save(entry.path)
        else:
            entry = book.get(op["rule"]) if "rule" in op else _rule_for(book, op, devices)
            bindings = entry.doc.setdefault("bindings", {})
            previous = bindings.get(op["target"])
            bindings[op["target"]] = op["source"]
            book.save(entry.path)
            undo.insert(0, {"op": "set", "target": op["target"], "source": previous, "rule": entry.id} if previous
                        else {"op": "unset", "target": op["target"], "rule": entry.id})
        touched.append(entry.id)
    return {"rules": list(dict.fromkeys(touched)), "undo": undo}


def _checked(ops: object, layouts: dict) -> list:
    """The ops, or RuleError naming the first thing wrong with them. Only console inputs of a known layout can be
    set, from a single physical input (chords and options are edited by hand)."""
    if not isinstance(ops, list) or not ops:
        raise RuleError("ops must be a non-empty list")
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in ("set", "unset"):
            raise RuleError(f"not an op: {op!r}")
        target = op.get("target")
        if not isinstance(target, str) or target not in targets_by_key(layouts):
            raise RuleError(f"unknown console input: {target!r}")
        if "rule" in op and not (isinstance(op["rule"], str) and ID_RE.match(op["rule"])):
            raise RuleError(f"bad rule id: {op['rule']!r}")
        if op["op"] == "unset":
            if "rule" not in op:
                raise RuleError("unset needs the rule to take the binding out of")
            continue
        source = op.get("source")
        if not (isinstance(source, dict) and source.get("input") in PHYSICAL_INPUTS):
            raise RuleError(f"set needs a source with a physical input: {source!r}")
        if ("rule" in op) == ("scope" in op):
            raise RuleError("set needs either a rule or a scope")
        if "scope" in op:
            _check_scope(op["scope"], target)
    return ops


def _check_scope(scope: object, target: str) -> None:
    if not isinstance(scope, dict) or set(scope) != {"controller", "content"}:
        raise RuleError("scope needs controller and content")
    pad, games = scope["controller"], scope["content"]
    system = target.split(".", 1)[0]
    if not isinstance(games, dict) or games.get("level") not in ("system", "game") or games.get("system") != system:
        raise RuleError(f"content scope must be this system ({system}) or one of its games")
    if games["level"] == "game" and not (isinstance(games.get("game_id"), str) and games["game_id"]):
        raise RuleError("a game scope needs the game id")
    if set(games) - {"level", "system", "game_id"}:
        raise RuleError("content scope takes level, system and game_id only")
    level = pad.get("level") if isinstance(pad, dict) else None
    if level == "device":
        if set(pad) - {"level", "player", "model"} or not isinstance(pad.get("player"), int):
            raise RuleError("a device scope names the player, not the device")
    elif level in ("model", "family", "brand", "style"):
        if set(pad) != {"level", "value"} or not isinstance(pad["value"], str):
            raise RuleError(f"a {level} scope needs its value")
    elif not (level == "any" and set(pad) == {"level"}):
        raise RuleError(f"unknown controller scope: {pad!r}")


def _rule_for(book: Book, op: dict, devices) -> Entry:
    """The rule a scoped set goes into: the user's own rule with this exact scope that sets the target, else this
    scope's edit rule, made when there is none."""
    pad, games = dict(op["scope"]["controller"]), dict(op["scope"]["content"])
    if pad["level"] == "device":
        if devices is None:
            raise RuleError("a change for one pad needs the pads connected now")
        pad = {"level": "device", "value": devices(pad["player"], pad.get("model"))}
    applies = {"controller": pad, "content": games}
    same = [e for e in book.entries if e.on and e.doc["applies_to"] == applies]
    setting = [e for e in same if op["target"] in e.doc.get("bindings", {})]
    if setting:
        return max(setting, key=lambda e: (e.doc.get("explicit_priority", 0), e.id))
    base = _edit_id(book, pad, games)
    for entry in same:
        if entry.id == base or entry.id.startswith(base + "-"):
            return entry
    taken, n, rule_id = book.ids(), 1, base
    while rule_id in taken or (book.rules_dir / f"{rule_id}.json").exists():
        n += 1
        rule_id = f"{base}-{n}"
    return book.add({"schema_version": 1, "id": rule_id, "label": EDIT_LABEL, "applies_to": applies, "bindings": {}})


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _edit_id(book: Book, pad: dict, games: dict) -> str:
    """edit.any.n64.all, edit.family-sony-dualsense.n64.game-legend-of-zelda-the-ocarina-of-time-usa-6c1f02,
    edit.pad-2.n64.all. A device gets a number, not its id: rule ids show up in the plugin and in logs."""
    if pad["level"] == "any":
        who = "any"
    elif pad["level"] == "device":
        numbers = {}
        for e in book.entries:
            m = re.match(r"^edit\.pad-(\d+)\.", e.id)
            if m and e.doc["applies_to"]["controller"].get("level") == "device":
                numbers[e.doc["applies_to"]["controller"]["value"]] = int(m.group(1))
        who = f"pad-{numbers.get(pad['value']) or max(numbers.values(), default=0) + 1}"
    else:
        who = f"{pad['level']}-{_slug(pad['value'])}"
    where = "all"
    if games["level"] == "game":
        game = games["game_id"]
        where = f"game-{_slug(game)[:40].strip('-')}-{hashlib.sha1(game.encode('utf-8')).hexdigest()[:6]}"
    return f"{EDIT_PREFIX}{who}.{games['system']}.{where}"


# -- on, off, delete, reset ----------------------------------------------------------------------------------------

def enable(book: Book, rule_id: str) -> list:
    """Turn a rule on. A parked file moves to rules/; the other rules in it stay off. Returns warnings: another rule
    that is on with the same scope and sets some of the same console inputs (only one of them can win)."""
    entry = book.get(rule_id)
    if entry.parked:
        for other in book.entries:
            if other.path == entry.path and other is not entry:
                other.doc["enabled"] = False
        entry.doc.pop("enabled", None)
        book.move(entry.path, parked=False)
    elif not entry.on:
        entry.doc.pop("enabled", None)
        book.save(entry.path)
    return clashes(book, entry)


def disable(book: Book, rule_id: str) -> None:
    entry = book.get(rule_id)
    if entry.on:
        entry.doc["enabled"] = False
        book.save(entry.path)


def delete(book: Book, rule_id: str) -> None:
    book.remove(book.get(rule_id))


def reset(book: Book, system: str, game: Optional[str] = None, write: bool = True) -> list:
    """Turn off every rule that is on and only applies to this system (game is None) or to this one game. Returns
    their ids: `enable` on each undoes it. Nothing is deleted."""
    hits = []
    for entry in book.entries:
        content = entry.doc["applies_to"]["content"]
        if not entry.on or content.get("system") != system:
            continue
        if game is None or (content["level"] == "game" and content.get("game_id") == game):
            hits.append(entry.id)
            if write:
                disable(book, entry.id)
    return hits


def clashes(book: Book, entry: Entry) -> list:
    out = []
    keys = set(entry.doc.get("bindings", {}))
    for other in book.entries:
        if other is entry or not other.on or other.doc["applies_to"] != entry.doc["applies_to"]:
            continue
        shared = keys & set(other.doc.get("bindings", {}))
        if shared:
            winner = max((entry, other), key=lambda e: (e.doc.get("explicit_priority", 0), e.id))
            out.append(f"{_name(other)} also sets {len(shared)} of the same buttons for the same games and pads; "
                       f"{_name(winner)} wins.")
    return out


def _name(entry: Entry) -> str:
    return entry.doc.get("label") or entry.id


# -- what the plugin lists -----------------------------------------------------------------------------------------

def targets_by_key(layouts: dict) -> dict:
    """Every console input map-helper can bind: "<system>.<controller>.<input>" -> (layout, kind)."""
    out = {}
    for layout in layouts.values():
        for pad, spec in layout.get("controllers", {}).items():
            for kind in ("buttons", "dpad", "analog"):
                for name in spec.get(kind, []):
                    out[f"{layout['system']}.{pad}.{name}"] = (layout, kind)
    return out


def targets(system: str, layouts: Optional[dict] = None) -> list:
    """The default controller's console inputs, for "Give it a job": [{target, label, kind}]."""
    from .show import _target_label
    layouts = layouts if layouts is not None else load_layouts(DATA / "layouts")
    layout = layouts.get(system)
    if layout is None:
        raise RuleError(f"no layout for system {system!r}")
    pad = layout["default_controller"]
    spec = layout["controllers"][pad]
    return [{"target": f"{system}.{pad}.{name}", "label": _target_label(f"{system}.{pad}.{name}", layout),
             "kind": {"buttons": "button", "dpad": "dpad", "analog": "axis"}[kind]}
            for kind in ("buttons", "dpad", "analog") for name in spec.get(kind, [])]


def listing(book: Book, db, layouts: Optional[dict] = None) -> dict:
    """Every rule in both folders, for the rules list. No device ids: a device scope reads "one pad"."""
    from .show import _target_label, describe_scope
    layouts = layouts if layouts is not None else load_layouts(DATA / "layouts")
    rules = []
    for entry in book.entries:
        rule = rule_from_doc(entry.doc, "user")
        layout = layouts.get(rule.content.system or "")
        rules.append({
            "id": entry.id, "label": entry.doc.get("label", ""), "on": entry.on, "parked": entry.parked,
            "edit": entry.id.startswith(EDIT_PREFIX), "file": entry.path.name,
            "system": rule.content.system, "system_name": (layout or {}).get("name"),
            "content_level": rule.content.level, "game": rule.content.game_id,
            "controller_level": rule.controller.level,
            "scope": describe_scope(rule.controller, rule.content, (layout or {}).get("name"), db),
            "bindings": [{"target": k, "label": _target_label(k, layout) if layout else k,
                          "input": v.get("input") or "+".join(v.get("chord", []))}
                         for k, v in entry.doc.get("bindings", {}).items()],
            "options": len(entry.doc.get("options", {})),
            "notes": entry.doc.get("notes", ""),
            "clashes": clashes(book, entry) if entry.on else [],
        })
    return {"rules": rules, "problems": [{"file": f, "problem": p} for f, p in book.problems]}


# -- before and after ----------------------------------------------------------------------------------------------

def scratch_copy(book: Book) -> tuple:
    """A copy of both folders in a temp dir, for a dry run: (Book over the copy, the temp dir to remove)."""
    tmp = Path(tempfile.mkdtemp(prefix="map-helper-rules-"))
    for folder, name in ((book.rules_dir, "rules"), (book.off_dir, "rules-off")):
        if folder.is_dir():
            shutil.copytree(folder, tmp / name, symlinks=False)
    return Book(tmp / "rules", tmp / "rules-off"), tmp


def changes(before: dict, after: dict) -> list:
    """What each player's buttons do differently between two show documents (the same pads, before and after an
    edit): [{player, pad, input, glyph, name, before: [labels], after: [labels]}]."""
    old = {p["player"]: {r["input"]: r for r in p["inputs"]} for p in before.get("players", [])}
    out = []
    for player in after.get("players", []):
        rows = old.get(player["player"], {})
        for row in player["inputs"]:
            if row.get("steam_only"):
                continue
            was = [d["label"] for d in rows.get(row["input"], {}).get("drives", [])]
            now = [d["label"] for d in row["drives"]]
            if was != now:
                out.append({"player": player["player"], "pad": player["pad"]["name"], "input": row["input"],
                            "glyph": row["glyph"], "name": row["name"], "before": was, "after": now})
    return out

