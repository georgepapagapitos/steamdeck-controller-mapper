"""Loading rules, layouts and the controller DB from disk. See docs/09."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .model import ContentScope, ControllerScope, Rule
from .validate import validate_rule


@dataclass
class LoadReport:
    rules: list = field(default_factory=list)
    problems: list = field(default_factory=list)   # (path, message); invalid files are skipped


def rule_from_doc(doc: dict, source: str, path: str | None = None) -> Rule:
    applies = doc["applies_to"]
    ctrl, content = applies["controller"], applies["content"]
    return Rule(
        id=doc["id"],
        controller=ControllerScope(ctrl["level"], ctrl.get("value")),
        content=ContentScope(content["level"], content.get("system"),
                             content.get("emulator"), content.get("game_id")),
        source=source,
        label=doc.get("label", ""),
        enabled=doc.get("enabled", True),
        explicit_priority=doc.get("explicit_priority", 0),
        requires=tuple(doc.get("requires", ())),
        bindings=dict(doc.get("bindings", {})),
        options=dict(doc.get("options", {})),
        path=path,
    )


def load_rules(directory: Path, source: str) -> LoadReport:
    """Load every *.json rule (or {"rules": [...]} bundle) under directory."""
    report = LoadReport()
    for path in sorted(Path(directory).rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report.problems.append((str(path), f"unreadable: {exc}"))
            continue
        docs = doc["rules"] if isinstance(doc, dict) and isinstance(doc.get("rules"), list) else [doc]
        for item in docs:
            errors = validate_rule(item)
            if errors:
                report.problems.append((str(path), "; ".join(errors)))
                continue
            report.rules.append(rule_from_doc(item, source, str(path)))
    return report


def load_sources(sources: Iterable[tuple[Path, str]]) -> LoadReport:
    combined = LoadReport()
    for directory, source in sources:
        if Path(directory).is_dir():
            part = load_rules(Path(directory), source)
            combined.rules += part.rules
            combined.problems += part.problems
    seen: dict[str, str] = {}
    for rule in combined.rules:
        if rule.id in seen:
            combined.problems.append((rule.path, f"duplicate rule id {rule.id!r} (also in {seen[rule.id]})"))
        seen[rule.id] = rule.path
    return combined


def load_layouts(directory: Path) -> dict:
    """system id -> layout document."""
    layouts = {}
    for path in sorted(Path(directory).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        layouts[doc["system"]] = doc
    return layouts


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
