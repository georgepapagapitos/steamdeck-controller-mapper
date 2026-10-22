# ADR-004: Coexist with Steam Input; don't write Steam configs (v1)

**Status:** Proposed

## Context

Steam Input sits in front of every controller in Game Mode. We could also
manage Steam layouts and per-game Steam Input enablement.

## Decision

In v1, map-helper only writes emulator configs. It detects Steam Input mode
(passthrough vs native) and renders accordingly ([05](../05-steam-input-strategy.md)).
Anything to do with Steam Input is *advice* in the UI (status + instructions),
never writes.

## Consequences

- ➕ Avoids undocumented, changing Steam formats and fights with a running Steam client.
- ➕ Clear ownership boundary, easy to explain.
- ➖ Users wanting native gyro must flip Steam settings themselves.
- ➖ Double-remap confusion is possible; mitigate with guidance.
- Revisit: optional SRM controller-template integration (Phase 5).
