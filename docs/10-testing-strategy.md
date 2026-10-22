# 10 — Testing Strategy

## Layers

| Layer | What | How |
|-------|------|-----|
| Unit | Model, scoring, merge, meta expansion, capability checks | Plain `unittest` (stdlib); table-driven |
| Format round-trip | Each parser: `parse → serialize == original` for every fixture | Byte-equality tests over `tests/fixtures/**` |
| Adapter golden | `render(ctx)` applied to fixture → expected file | `tests/golden/<emu>/<version>/<case>/expected/...`; `UPDATE_GOLDEN=1` to regenerate, reviewed in PR |
| Adapter import | `read(fixture)` → canonical == expected JSON | Same structure |
| Import ↔ export | `render(read(x))` changes no managed values | Property-style over fixtures |
| Resolver properties | Determinism; adding a less-specific rule never changes a key a more-specific rule sets; disabling a rule = removing it | Randomized rule sets (stdlib `random` with fixed seeds) |
| Writer safety | Atomicity, no-op skip, lock contention, emulator-running abort, crash mid-write (kill between tmp and rename) | Temp dirs + fault injection |
| Launch wrapper | Time budget, fail-open on every exception, arg passthrough | Subprocess tests with fake launchers |
| Device probe | Parsing sysfs/procfs | Captured sysfs trees under `tests/fixtures/devices/<scenario>/` (DS4 USB, DS4 BT, 8BitDo X-mode, Deck + 2 pads, Steam virtual pads present) |
| UI | Component tests for wizard state machine | Vitest + React Testing Library (frontend) |
| On-device | Real emulators, real controllers | Manual checklist below, run per release |

## Fixtures: the most valuable asset

`tools/deck.sh capture <scenario>` (run from the Mac or Windows; the dump runs on the Deck):
- copies each detected emulator's config files into `tests/fixtures/<emu>/<scenario>/`, with RetroAchievements and netplay credentials blanked,
- records SteamOS, Python and emulator versions and install types in `tests/fixtures/devices/<scenario>/versions.txt`,
- dumps `/proc/bus/input/devices`, sysfs input/DRM/power-supply state and Steam's `virtualgamepadinfo.txt` into `tests/fixtures/devices/<scenario>/`, redacting MACs (the vendor half is kept for brand detection, the rest becomes a stable hash).

We need fixtures for: EmuDeck fresh defaults, after the user changes bindings in
the emulator UI, and multiple emulator versions where formats differ.

## CI

- GitHub Actions on Ubuntu with Python matching SteamOS's version (**[VERIFY]** the current SteamOS Python version), plus the newest Python 3.
- Lint: `ruff` (dev-only dependency), type check: `mypy --strict` on core.
- Frontend: `pnpm build`, `vitest`.
- Package: build the Decky plugin zip as an artifact.

## On-device release checklist (abridged)

For each P0 emulator, with **Deck only**, **Deck + DS4 (USB)**, **Deck + DS4 (BT)**,
and **Deck + 8BitDo (X-mode, claimed)**:

- [ ] Fresh install → launch wrappers set (Steam launch options + ES-DE event script), AutoMap off → launch → bindings match shipped defaults (= EmuDeck behaviour, no visible change)
- [ ] Family rule for DS4 → launch → applied; Xbox pad → not applied
- [ ] Game override → only that game is affected
- [ ] Reconnect controllers in reverse order → same mapping per controller
- [ ] Docked policy `external-first` → DS4 is P1
- [ ] Change bindings in the emulator UI → next launch → drift prompt
- [ ] EmuDeck "reset configurations" → next launch → mappings restored, pristine re-baselined
- [ ] EmuDeck update / SRM shortcut regeneration → launch wrappers still present (or `doctor` flags them); AutoMap still off
- [ ] Uninstall (`current`) → configs == EmuDeck baseline for managed keys
- [ ] Launch with map-helper deliberately broken (corrupt rules) → emulator still launches
