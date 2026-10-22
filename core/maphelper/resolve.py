"""The resolver: matching rules -> effective bindings + explanation trace. See docs/03 §3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .model import (CONTROLLER_RANK, INPUT_CAPABILITY, SOURCE_RANK, Controller, Rule, Target,
                    flatten_options)


@dataclass
class Choice:
    value: Any
    rule_id: str
    shadowed: list = field(default_factory=list)   # rule ids that also set this key, lower score
    via_meta: Optional[str] = None                 # "meta.confirm" when expanded from a meta-binding
    source: str = "user"                           # the winning rule's source: shipped, pack or user


@dataclass
class Resolution:
    bindings: dict = field(default_factory=dict)   # key -> Choice
    options: dict = field(default_factory=dict)    # flattened option key -> Choice
    warnings: list = field(default_factory=list)
    matched_rules: list = field(default_factory=list)


def score(rule: Rule, direct: bool = True) -> tuple:
    """Higher wins. Order: source, explicit priority, content scope, controller scope,
    direct-over-meta, then id for determinism."""
    return (SOURCE_RANK[rule.source], rule.explicit_priority, rule.content.rank,
            CONTROLLER_RANK[rule.controller.level], 1 if direct else 0, rule.id)


def resolve(rules: list, controller: Controller, target: Target, layouts: dict) -> Resolution:
    result = Resolution()
    layout = layouts.get(target.system)
    if layout is None:
        result.warnings.append(f"no layout for system {target.system!r}")
    prefix = f"{target.system}."

    # key -> list of (score, rule_id, value, via_meta, rule source)
    candidates: dict[str, list] = {}
    option_candidates: dict[str, list] = {}

    for rule in rules:
        if not (rule.enabled and controller.matches(rule.controller) and target.matches(rule.content)):
            continue
        missing = [c for c in rule.requires if c not in controller.capabilities]
        if missing:
            result.warnings.append(f"{rule.id}: skipped, controller lacks {missing}")
            continue
        result.matched_rules.append(rule.id)

        for key, source in rule.bindings.items():
            if key.startswith("meta."):
                expanded = _expand_meta(key, layout)
                if expanded is None:
                    continue
                entries = [(expanded, score(rule, direct=False), key)]
            elif key.startswith("hotkey.") or key.startswith(prefix):
                entries = [(key, score(rule), None)]
            else:
                continue   # binding for another system
            for k, s, via in entries:
                problem = _capability_problem(source, controller)
                if problem:
                    result.warnings.append(f"{rule.id}: {k} skipped, {problem}")
                    continue
                candidates.setdefault(k, []).append((s, rule.id, source, via, rule.source))

        for key, value in flatten_options(rule.options).items():
            option_candidates.setdefault(key, []).append((score(rule), rule.id, value, None, rule.source))

    result.bindings = {k: _pick(v) for k, v in sorted(candidates.items())}
    result.options = {k: _pick(v) for k, v in sorted(option_candidates.items())}
    result.warnings += _duplicate_source_warnings(result.bindings, layout)
    return result


def _pick(entries: list) -> Choice:
    entries.sort(key=lambda e: e[0], reverse=True)
    _, rule_id, value, via, source = entries[0]
    return Choice(value=value, rule_id=rule_id, shadowed=[e[1] for e in entries[1:]], via_meta=via, source=source)


def set_by_rules(resolution: Resolution) -> Resolution:
    """Only what a user or pack rule decides. A key that shipped defaults alone decide is left as the user's config
    has it: live configs often predate EmuDeck's current templates, and the user never asked to change them."""
    keep = lambda choices: {k: c for k, c in choices.items() if c.source != "shipped"}
    return Resolution(keep(resolution.bindings), keep(resolution.options), resolution.warnings,
                      resolution.matched_rules)


def _expand_meta(key: str, layout: Optional[dict]) -> Optional[str]:
    if not layout:
        return None
    alias = key.split(".", 1)[1]
    target = layout.get("meta", {}).get(alias)
    return f"{layout['system']}.{target}" if target else None


def _capability_problem(source: dict, controller: Controller) -> Optional[str]:
    inputs = source.get("chord") or [source.get("input")]
    for name in inputs:
        cap = INPUT_CAPABILITY.get(name)
        if cap and cap not in controller.capabilities:
            return f"controller has no {cap} ({name})"
    return None


def _duplicate_source_warnings(bindings: dict, layout: Optional[dict]) -> list:
    """Two console inputs on one physical input is usually a mistake, unless the layout allows it."""
    allowed = set()
    for pair in (layout or {}).get("controllers", {}).get(
            (layout or {}).get("default_controller", ""), {}).get("allow_shared_sources", []):
        allowed.add(frozenset(f"{layout['system']}.{layout['default_controller']}.{p}" for p in pair.split("+")))
    by_input: dict[str, list] = {}
    for key, choice in bindings.items():
        if key.startswith("hotkey.") or "input" not in choice.value or choice.value["input"] == "none":
            continue
        by_input.setdefault(choice.value["input"], []).append(key)
    return [f"{inp} drives several inputs: {keys}" for inp, keys in sorted(by_input.items())
            if len(keys) > 1 and frozenset(keys) not in allowed]


def explain(resolution: Resolution) -> str:
    """Human-readable trace, the output of `map-helper explain`."""
    lines = []
    width = max((len(k) for k in [*resolution.bindings, *resolution.options]), default=10)
    for title, table in (("Bindings", resolution.bindings), ("Options", resolution.options)):
        if not table:
            continue
        lines.append(f"{title}:")
        for key, choice in table.items():
            value = _format_value(choice.value)
            note = f"  (via {choice.via_meta})" if choice.via_meta else ""
            shadow = f"  shadows: {', '.join(choice.shadowed)}" if choice.shadowed else ""
            lines.append(f"  {key:<{width}}  {value:<22} <- {choice.rule_id}{note}{shadow}")
    if not resolution.bindings and not resolution.options:
        lines.append("No rules apply; the emulator keeps its own config.")
    for warning in resolution.warnings:
        lines.append(f"warning: {warning}")
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        if "chord" in value:
            return "+".join(value["chord"])
        extras = "".join(f" {k}={v}" for k, v in value.items() if k != "input")
        return f"{value['input']}{extras}"
    return str(value)
