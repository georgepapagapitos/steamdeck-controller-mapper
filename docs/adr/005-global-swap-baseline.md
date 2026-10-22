# ADR-005: Global-swap is the baseline adapter strategy

**Status:** Proposed

## Context

Emulators differ widely in per-game input support (none, per-game files,
profile pointers). Writing per-game files needs reliable game ids, which are
expensive for compressed images (CHD/RVZ). We apply at every launch anyway
(ADR-001).

## Decision

Every adapter implements **global-swap**: at each launch, write the resolved
bindings for this launch into the emulator's global input config. Per-game
files and named profiles are optional enhancements, not required for
correctness. Game ids are only needed to resolve game-scoped rules; if no id is
available, those rules are skipped with a warning.

## Consequences

- ➕ One uniform strategy, simplest adapters, works for every emulator.
- ➕ Game id lookup failure degrades gracefully.
- ➖ Launching an emulator outside our hook gets whatever the last launch wrote. Mitigated by the optional `restore_after_exit` and by profile-select enhancements.
- ➖ Emulator-side per-game input overrides shadow us, so adapters must detect and report them.
