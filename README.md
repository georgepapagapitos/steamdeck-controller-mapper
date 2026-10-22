# map-helper

A controller mapping manager for the Steam Deck (and other SteamOS / Linux
handhelds), designed to sit alongside EmuDeck. Mappings can be set per
controller, per emulator, per system and per game.

Plug in a DualShock 4, pick "GameCube", press the buttons you want, and every
GameCube emulator you use gets that mapping whenever a DualShock 4 is the
controller in use. Or set it once for **all DualShock 4s**, **all 8BitDo
pads**, or **every PlayStation-style controller**, and override it only where
you care. Mappings are remembered and re-applied at every launch, so emulator
updates and EmuDeck resets don't silently wipe them.

> Status: **design + working prototype core.** The docs are the blueprint,
> with emulator, EmuDeck, SDL/kernel and Decky facts cited to pinned source
> commits. Desk research has answered all 13 spikes in
> [docs/13-research-spikes.md](docs/13-research-spikes.md) as far as source
> can go. What's left there, and every remaining **[VERIFY]** tag, needs a real Deck.
>
> The prototype (`core/`, stdlib Python 3.11+, 50 tests) has the rule
> model and validation, the resolver with `explain`, controller
> classification, Steam virtual-pad slot mapping, a round-trip INI editor, a
> safe writer, and a **Dolphin GameCube adapter** that writes EmuDeck's real
> `GCPadNew.ini` / `Hotkeys.ini`. See [CONTRIBUTING.md](CONTRIBUTING.md) to run it.

## The pitch

On a Steam Deck, controller input passes through two mapping layers: **Steam
Input** (physical pad → virtual Xbox pad) and the **emulator's own config**
(virtual pad → emulated console buttons). Steam Input already remembers layouts
per game and per controller type. The emulator layer is a mess of about 15
config formats with no shared idea of "which physical controller is this?".
map-helper owns that second layer. It keeps one canonical model of your
mappings, scoped by **controller** (exact pad → model → family → brand → layout
style → any) and by **content** (global → system → emulator → game). It
translates the result into each emulator's native format and applies it at
launch, based on the controllers that are actually connected.

## Documentation map

| # | Doc | What it answers |
|---|-----|-----------------|
| 01 | [Vision & scope](docs/01-vision-and-scope.md) | What we're building, for whom, and what we're explicitly *not* building |
| 02 | [Architecture](docs/02-architecture.md) | Components, data flow, process model, repo layout |
| 03 | [Canonical mapping model](docs/03-canonical-model.md) | Inputs, console layouts, rules, scopes, layering and resolution |
| 04 | [Controller identification](docs/04-controller-identification.md) | Which controller is this, which family/brand/style, and player ordering |
| 05 | [Steam Input strategy](docs/05-steam-input-strategy.md) | Coexisting with Steam Input (passthrough vs native modes) |
| 06 | [Emulator adapters](docs/06-emulator-adapters.md) | Adapter contract and the catalog of every emulator |
| 07 | [Launch integration](docs/07-launch-integration.md) | How mappings get applied before an emulator starts |
| 08 | [UI / UX](docs/08-ui-ux.md) | Decky plugin flows, screens, the press-to-bind wizard |
| 09 | [Storage, safety & sync](docs/09-storage-safety-sync.md) | Where state lives, backups, never corrupting a config |
| 10 | [Testing strategy](docs/10-testing-strategy.md) | Golden files, fixtures, on-device checklists |
| 11 | [Roadmap](docs/11-roadmap.md) | Phased delivery with exit criteria |
| 12 | [Risks & open questions](docs/12-risks-open-questions.md) | What can go wrong, what's undecided |
| 13 | [Research spikes](docs/13-research-spikes.md) | Every **[VERIFY]** item as an on-device checklist |
| 14 | [Packaging & permissions](docs/14-packaging-permissions.md) | Decky plugin structure, Python runtime, install layout, store policy, security |
| — | [Glossary](docs/glossary.md) | Terms used throughout |

More detail:

- [docs/adapters/](docs/adapters/): per-emulator deep dives and the adapter template
- [docs/adr/](docs/adr/): architecture decision records
- [schema/](schema/): JSON Schema for rule files
- [data/](data/): controller database, console layouts for 28 systems, per-emulator naming tables (`data/adapters/`, including 17 RetroArch cores), EmuDeck's default scheme (`data/defaults/`)
- [core/](core/): the prototype library and CLI; [tests/](tests/): unit tests, EmuDeck config fixtures and golden diffs
- [examples/](examples/): example rule files showing every scope level

## Quick mental model

```
┌──────────────┐    ┌──────────────────┐    ┌───────────────────┐    ┌──────────────┐
│ Physical pad │ →  │ Steam Input      │ →  │ Emulator config   │ →  │ Emulated     │
│ (DS4, Xbox,  │    │ (optional layer; │    │ ← map-helper      │    │ console pad  │
│  8BitDo...)  │    │  Steam owns it)  │    │   writes this     │    │ (GC, PS2...) │
└──────────────┘    └──────────────────┘    └───────────────────┘    └──────────────┘
        ▲                                             ▲
        └──── map-helper detects this at launch ──────┘
              and resolves the right rules

Rule scopes (most specific wins, merged per button):

  controller:  device  >  model  >  family  >  brand  >  style  >  any
  content:     game    >  emulator  >  system  >  global
  source:      user    >  community pack  >  shipped defaults
```

## License

GPL-3.0. See [LICENSE](LICENSE). EmuDeck config files under `tests/fixtures/` are GPL-3.0 from their original authors (see [tests/fixtures/README.md](tests/fixtures/README.md)).
