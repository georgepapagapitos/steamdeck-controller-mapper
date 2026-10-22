# 11 — Roadmap

Each phase has **exit criteria**. Don't start the next phase until they're met.

## Phase 0: Research spikes (on a Deck)

Run every spike in [13](13-research-spikes.md), at least the ones tagged
**blocking**. Capture fixtures for the P0 emulators and controller scenarios.

**Exit:** spike results written into each spike's "Findings" section; fixtures
committed; **[VERIFY]** tags in docs resolved or re-scoped.

## Phase 1: Core + CLI + RetroArch

- Canonical model, schema, store, validation, migrations scaffold
- Controller DB v0 (Sony, Microsoft, Nintendo, 8BitDo, Valve, plus a handful of others)
- Device probe + registry + claims + slot policies (`steam-order`, `pinned`)
- Resolver with scoring, per-key merge, meta-bindings, explain trace
- Writer (atomic, journal, pristine, drift hashing)
- RetroArch adapter: remaps for 6 cores (Snes9x, Mesen/Nestopia, mGBA, Genesis Plus GX, Beetle/SwanStation, Mupen64Plus-Next)
- CLI: `devices`, `rules`, `explain`, `apply --dry-run`, `apply`, `backup`, `doctor`

**Exit:** on a Deck, a `family:sony.dualshock4 / system:snes` rule applies via
`map-helper apply` and is correct in RetroArch, and goldens pass.

## Phase 2: Standalone P0 + launch integration

- Dolphin, PCSX2, DuckStation adapters (global-swap, [ADR-005](adr/005-global-swap-baseline.md))
- Launch integration per [ADR-001](adr/001-apply-at-launch.md): `mh-run` wrapper via Steam launch options / SRM parser, ES-DE `game-start` event script, AutoMap off; time budget and fail-open
- Wrapper health check after EmuDeck updates and SRM regeneration
- Drift detection + `prefer-mine` policy
- `external-first` slot policy + docked detection

**Exit:** the full on-device checklist ([10](10-testing-strategy.md)) passes
for the 4 P0 emulators.

## Phase 3: Decky plugin (MVP UI)

- QAM status panel, controllers screen (claim, rename, link, pin)
- Mapping wizard (press-to-bind, presets, test, scope picker with conflict preview)
- Rule list + editor, explain view
- Drift prompt, settings, uninstall
- Shipped defaults mirroring EmuDeck behaviour

**Exit:** a casual user maps a DS4 for GameCube in under 2 minutes in Game
Mode (usability test with 3+ people); no Desktop mode needed for any v1 flow.

**→ Public beta (v0.x)**

## Phase 4: Breadth

- P1 adapters: RPCS3, Cemu, yuzu-family, Ryujinx-family, Citra-family, PPSSPP
- More RetroArch cores
- Matrix view
- Export/import + community packs
- Gyro: native-mode guidance; investigate DSU passthrough for passthrough mode

**Exit:** P1 checklists pass. v1.0.

## Phase 5: Ecosystem

- Upstream pre-launch hook to EmuDeck (Option C); ideally an EmuDeck integration/partnership
- RetroDECK path provider + hook
- Bazzite / ChimeraOS / Legion Go / ROG Ally (SteamOS-based) validation
- P2/P3 adapters
- Optional SRM controller-template integration
- udev hotplug notifier for "new controller" toasts
- Community controller DB contributions workflow

## Work breakdown (Phase 1–3, rough sizing)

| Item | Size |
|------|------|
| Model + schema + store | M |
| Controller DB + probe + registry | L |
| Resolver + explain | M |
| Round-trip parsers (RA cfg, Dolphin INI, Qt-free INI for PCSX2/DS) | L |
| Writer + journal + drift | M |
| RetroArch adapter + 6 core descriptors | L |
| Dolphin / PCSX2 / DuckStation adapters | M each |
| Hooks + mh-run | M |
| Decky plugin scaffold + RPC | S |
| Wizard (incl. capture) | XL |
| Other screens | L |
| Fixtures + goldens + CI | M |

S ≈ ≤ 2 days, M ≈ ≤ 1 week, L ≈ 1–2 weeks, XL ≈ 2–4 weeks (one person, part-time multiplier not included).
