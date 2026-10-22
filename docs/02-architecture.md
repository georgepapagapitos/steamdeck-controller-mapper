# 02 — Architecture

## Components

```
                       ┌─────────────────────────────────────────────┐
                       │                 mh-core (Python)            │
                       │                                             │
 ┌──────────────┐      │  ┌───────────┐  ┌───────────┐  ┌─────────┐  │
 │ Decky plugin │─RPC─▶│  │ Rule store│  │ Resolver  │  │ Device  │  │
 │ (React UI +  │      │  │ (JSON +   │─▶│ (scopes,  │◀─│ probe   │  │
 │  Python      │      │  │  schema)  │  │  layering)│  │ (udev/  │  │
 │  backend)    │      │  └───────────┘  └─────┬─────┘  │  evdev) │  │
 └──────────────┘      │                       │        └─────────┘  │
                       │  ┌───────────┐  ┌─────▼─────┐  ┌─────────┐  │
 ┌──────────────┐      │  │ Controller│  │ Adapter   │  │ Path    │  │
 │ CLI          │─────▶│  │ DB        │  │ registry  │◀─│ provider│  │
 │ map-helper   │      │  │ (models,  │  │ (dolphin, │  │ (EmuDeck│  │
 └──────────────┘      │  │  families)│  │  pcsx2..) │  │  flatpak│  │
                       │  └───────────┘  └─────┬─────┘  │  appimg)│  │
 ┌──────────────┐      │                       │        └─────────┘  │
 │ Launch       │─────▶│  ┌───────────┐  ┌─────▼─────┐               │
 │ wrapper      │      │  │ Backup /  │◀─│ Writer    │               │
 │ mh-run       │      │  │ journal   │  │ (atomic,  │               │
 └──────────────┘      │  └───────────┘  │  managed  │               │
                       │                 │  regions) │               │
                       │                 └───────────┘               │
                       └─────────────────────────────────────────────┘
```

| Component | Responsibility |
|-----------|----------------|
| **Rule store** | Loads and validates rule files from three sources: shipped defaults, community packs, user. See [03](03-canonical-model.md) and [09](09-storage-safety-sync.md). |
| **Controller DB** | Shipped data: known VID:PID → model → family → brand → style, button glyphs, capabilities (gyro, touchpad, paddles). See [04](04-controller-identification.md). |
| **Device probe** | Enumerates connected *physical* controllers (it sees through Steam's virtual pads), gets the stable identity, and assigns player slots. |
| **Resolver** | Given (connected controllers, system, emulator, game), computes the effective binding set per player. Produces an *explanation trace*. |
| **Adapter registry** | One adapter per emulator: knows paths, formats, input naming, per-game support, how to read (import) and write (export). See [06](06-emulator-adapters.md). |
| **Path provider** | Finds where an emulator is installed and where its config lives (EmuDeck Flatpak, EmuDeck AppImage, RetroDECK, native, SD card). |
| **Writer** | Applies adapter output to config files atomically. Touches only managed keys or regions, and records a journal entry. |
| **Backup / journal** | Pristine snapshots, per-apply diffs, restore and uninstall. |
| **Launch wrapper (`mh-run`)** | Runs *before* the emulator: probe → resolve → write → exec the emulator. See [07](07-launch-integration.md). |
| **CLI (`map-helper`)** | Every feature, scriptable. The UI is a client of the same core. |
| **Decky plugin** | Game Mode UI: wizard, matrix view, rule editor, device list, settings. The Python backend runs as the normal user and talks to an `mh-core` worker process (`/usr/bin/python3 -I`, JSON over stdin/stdout), because Decky's bundled Python ships only part of the stdlib ([14](14-packaging-permissions.md)). |

## Language & runtime

- **Python 3.11+ (stdlib only for the core), run on SteamOS's system Python.**
  `/usr/bin/python3` is always present on a Deck (3.13 on SteamOS 3.8 Stable),
  so one core library serves the CLI, the wrapper and the plugin. The Decky
  backend runs it as a subprocess instead of importing it, because Decky's
  PyInstaller bundle includes only part of the stdlib ([14](14-packaging-permissions.md)). SteamOS's root filesystem is read-only, so we avoid pip dependencies;
  anything we need gets vendored. See [ADR-002](adr/002-python-stdlib-core.md).
- **Formats we must read and write:** INI (several dialects: Dolphin's backtick
  syntax, Qt `QSettings` escaping in the yuzu-family and Citra-family
  emulators), JSON, YAML (RPCS3), XML (Cemu), TOML (xemu, melonDS) and
  RetroArch `.cfg`. Each needs a **round-trip-preserving** parser that keeps
  comments, ordering and unknown keys. That rules out `configparser` for
  writing, so we write small purpose-built parsers per dialect, with tests.
  - YAML: RPCS3's input files are simple. Use a minimal subset parser, or vendor a
    pure-Python YAML library. **[VERIFY]** how complex RPCS3's YAML really is.
  - TOML: `tomllib` (3.11+) reads it. For writing, use a line-preserving editor over our managed keys.
- **Decky frontend:** TypeScript + React using `@decky/ui` and `@decky/api`.

## Data flow: apply at launch

```
Steam/ES-DE launches shortcut
        │
        ▼
mh-run --emulator dolphin --system gc --rom "/path/Melee.iso" -- <original cmd>
        │
        ├─ 1. probe: connected physical controllers → [DS4 v2 (054c:09cc, serial X), Deck (28de:1205)]
        ├─ 2. slots: apply player-order policy → P1 = DS4, P2 = Deck (docked policy)
        ├─ 3. game id: adapter.identify_game(rom) → "GALE01"
        ├─ 4. resolve: for each player → effective bindings + trace
        ├─ 5. render: adapter.render(bindings, slots, steam_input_mode) → patch set
        ├─ 6. write: writer.apply(patch set) → journal entry; skipped if unchanged (hash)
        └─ 7. exec original command (replace process; keep PID semantics for Steam)
```

If anything in steps 1–6 fails, **log it, leave configs untouched, and still
launch the emulator**. Failing safe means the emulator falls back to whatever
config it had. A launch must never be blocked by map-helper.

## Data flow: mapping wizard

```
Decky UI ─▶ backend.start_capture(device_id) ─▶ evdev reader (filtered to that device)
         ◀── stream of normalized input events (face_south pressed, l_stick_x -0.9 ...)
Decky UI ─▶ backend.save_rule(rule, scope) ─▶ rule store (validate, write, version)
Decky UI ─▶ backend.preview(system, emulator, game?) ─▶ resolver trace for display
```

## Process model

- **No resident daemon in v1.** Everything happens in the wrapper (short-lived)
  or in the Decky backend (already resident). Optional v2 idea: a udev hotplug
  notifier to show "New controller detected: map it?" toasts. That's UX only, and
  it never writes configs.
- **Concurrency:** writer takes an advisory lock (`flock`) on
  `$STATE/locks/<emulator>.lock`, so two quick launches don't interleave.

## Proposed repo layout

```
map-helper/
├── README.md
├── docs/                     # this documentation
├── schema/                   # JSON Schemas (rules, controller db, layouts)
├── data/
│   ├── controllers.json      # controller DB (models, families, brands, styles)
│   ├── layouts/              # console layouts (gc.json, ps2.json, ...)
│   ├── adapters/             # per-emulator naming tables; retroarch/cores/*.json core descriptors
│   └── defaults/             # shipped default rules
├── examples/                 # example rule files
├── core/
│   └── maphelper/
│       ├── model/            # dataclasses: Input, Binding, Rule, Scope ...
│       ├── store/            # loading, validation, migrations
│       ├── devices/          # probe, identity, slots
│       ├── resolve/          # resolver + explain trace
│       ├── formats/          # round-trip parsers: ini_dolphin, ini_qt, ra_cfg, yaml_min, xml, toml_edit
│       ├── adapters/         # one module per emulator
│       ├── paths/            # path providers (emudeck, retrodeck, native)
│       ├── writer/           # atomic writes, managed regions, journal, backup
│       └── cli/              # argparse entry points: map-helper, mh-run
├── decky/                    # Decky plugin (frontend src/, main.py backend)
├── tests/
│   ├── fixtures/<emulator>/<version>/   # real config files captured from devices
│   ├── golden/                          # expected outputs
│   └── ...
└── tools/                    # dev scripts: deck.sh (push, run, capture over ssh)
```

## Key interfaces (sketch)

```python
class Adapter(Protocol):
    id: str                      # "dolphin"
    systems: set[str]            # {"gc", "wii"}
    def detect(self, paths: PathProvider) -> Install | None: ...
    def capabilities(self, install: Install) -> Caps: ...      # per-game? gyro? max players? hotkeys?
    def identify_game(self, rom: Path) -> GameId | None: ...
    def read(self, install: Install) -> ImportedConfig: ...     # import → canonical
    def render(self, ctx: RenderContext) -> PatchSet: ...       # canonical → file patches
    def managed_keys(self, install: Install) -> KeySelector: ...

class Resolver:
    def resolve(self, players: list[PlayerSlot], target: Target) -> Resolution: ...
    # Resolution = per-player effective bindings + trace of rule ids per binding
```
