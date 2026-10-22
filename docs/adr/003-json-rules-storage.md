# ADR-003: JSON rule files with a published JSON Schema

**Status:** Proposed

## Context

Rules must be human-readable, diffable, syncable and validated. Candidates:
JSON, TOML, YAML, SQLite.

## Decision

JSON files, one rule per file under `$DATA/rules/`, validated against
`schema/rule.schema.json`. The stdlib can read and write JSON. Validation uses a
small built-in validator for the subset of JSON Schema we use (or a vendored
validator).

## Consequences

- ➕ No dependencies; trivially syncable; editor support via `$schema`.
- ➕ Per-file layout keeps sync conflicts small.
- ➖ No comments in JSON, so use a `notes` field.
- ➖ Querying many rules means loading them all. That's fine at the expected scale (hundreds of rules).
