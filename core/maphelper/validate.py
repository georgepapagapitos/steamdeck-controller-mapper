"""Stdlib validation of rule documents.

Mirrors schema/rule.schema.json (ADR-003). The schema is the published contract;
this module is what runs on the device, where no JSON Schema library is available.
tests/test_validate.py checks that the two agree on the example files.
"""

from __future__ import annotations

import re

from .model import CONTENT_LEVELS, CONTROLLER_LEVELS, PHYSICAL_INPUTS

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
BINDING_KEY_RE = re.compile(r"^([a-z0-9]+\.[a-z0-9_]+\.[a-z0-9_]+|meta\.[a-z_]+|hotkey\.[a-z_]+)$")
TOP_LEVEL_KEYS = {"$schema", "schema_version", "id", "label", "notes", "enabled", "revision",
                  "explicit_priority", "requires", "applies_to", "bindings", "options"}
INPUT_SOURCE_KEYS = {"input", "mode", "threshold", "invert", "deadzone", "sensitivity"}


def validate_rule(doc: object) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    if not isinstance(doc, dict):
        return ["rule must be a JSON object"]
    errors: list[str] = []

    unknown = set(doc) - TOP_LEVEL_KEYS
    if unknown:
        errors.append(f"unknown keys: {sorted(unknown)}")
    if doc.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(doc.get("id"), str) or not ID_RE.match(doc["id"]):
        errors.append("id must match ^[a-z0-9][a-z0-9._-]*$")
    if "enabled" in doc and not isinstance(doc["enabled"], bool):
        errors.append("enabled must be a boolean")
    if "explicit_priority" in doc and not _is_int(doc["explicit_priority"]):
        errors.append("explicit_priority must be an integer")

    applies = doc.get("applies_to")
    if not isinstance(applies, dict):
        errors.append("applies_to is required")
    else:
        errors += _validate_controller_scope(applies.get("controller"))
        errors += _validate_content_scope(applies.get("content"))

    bindings = doc.get("bindings", {})
    if not isinstance(bindings, dict):
        errors.append("bindings must be an object")
    else:
        for key, source in bindings.items():
            if not BINDING_KEY_RE.match(key):
                errors.append(f"bad binding key: {key!r}")
            errors += [f"{key}: {e}" for e in _validate_source(source)]

    if "options" in doc and not isinstance(doc["options"], dict):
        errors.append("options must be an object")
    return errors


def _validate_controller_scope(scope: object) -> list[str]:
    if not isinstance(scope, dict):
        return ["applies_to.controller is required"]
    level = scope.get("level")
    if level not in CONTROLLER_LEVELS:
        return [f"applies_to.controller.level must be one of {CONTROLLER_LEVELS}"]
    if level == "any" and "value" in scope:
        return ["applies_to.controller.value must be omitted when level is 'any'"]
    if level != "any" and not isinstance(scope.get("value"), str):
        return [f"applies_to.controller.value is required for level {level!r}"]
    return []


def _validate_content_scope(scope: object) -> list[str]:
    if not isinstance(scope, dict):
        return ["applies_to.content is required"]
    level = scope.get("level")
    if level not in CONTENT_LEVELS:
        return [f"applies_to.content.level must be one of {CONTENT_LEVELS}"]
    required = {"game": ("system", "game_id"), "emulator": ("emulator",), "system": ("system",)}
    return [f"applies_to.content.{f} is required for level {level!r}"
            for f in required.get(level, ()) if not isinstance(scope.get(f), str)]


def _validate_source(source: object) -> list[str]:
    if not isinstance(source, dict):
        return ["source must be an object"]
    if "chord" in source:
        chord = source["chord"]
        if set(source) != {"chord"}:
            return ["chord sources take no other fields"]
        if not isinstance(chord, list) or len(chord) < 2:
            return ["chord needs at least 2 inputs"]
        bad = [i for i in chord if i not in PHYSICAL_INPUTS]
        return [f"unknown inputs in chord: {bad}"] if bad else []
    if source.get("input") not in PHYSICAL_INPUTS:
        return [f"unknown physical input: {source.get('input')!r}"]
    errors = []
    unknown = set(source) - INPUT_SOURCE_KEYS
    if unknown:
        errors.append(f"unknown source fields: {sorted(unknown)}")
    if "mode" in source and source["mode"] not in ("analog", "digital"):
        errors.append("mode must be 'analog' or 'digital'")
    return errors


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
