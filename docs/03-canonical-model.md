# 03 — Canonical Mapping Model

This is the heart of the project. Everything else either feeds it (device
probe, import) or consumes it (adapters, UI).

## 1. Vocabulary

### 1.1 Physical inputs (source side)

A fixed, **positional** vocabulary modelled on SDL's GameController layout,
plus extensions. Positional means `face_south` is the bottom face button
whatever is printed on it (Cross on PlayStation, A on Xbox, B on Nintendo).

| Group | Inputs |
|-------|--------|
| Face | `face_south`, `face_east`, `face_west`, `face_north` |
| D-pad | `dpad_up`, `dpad_down`, `dpad_left`, `dpad_right` |
| Shoulders | `l1`, `r1` (bumpers), `l2`, `r2` (triggers; analog where supported) |
| Sticks | `ls_x`, `ls_y`, `rs_x`, `rs_y` (axes), `ls_up/down/left/right`, `rs_up/...` (half-axes), `l3`, `r3` |
| Center | `start`, `select` (Back/Share/Minus), `guide` (Home/PS), `misc1` (Share on Xbox Series, Capture on Switch, Mute on DualSense) |
| Extras | `paddle1`–`paddle4` (Deck L4/L5/R4/R5, Elite, Edge), `touchpad_click`, `touchpad` (surface), `gyro`, `accel` |
| Deck-only | `trackpad_l`, `trackpad_r`, `trackpad_l_click`, `trackpad_r_click`, `qam` (usually unavailable; Steam owns them) |

Source expressions can have modifiers:

```jsonc
{ "input": "l2", "mode": "digital", "threshold": 0.5 }   // analog → button
{ "input": "ls_y", "invert": true }
{ "input": "ls_x", "deadzone": 0.12, "sensitivity": 1.0 }
{ "chord": ["select", "r1"] }                              // hotkeys only
{ "input": "none" }                                        // explicitly unbound
```

### 1.2 Console layouts (target side)

Each system has a **layout file** listing its controller type(s) and their
inputs. Example (abridged) `data/layouts/gc.json`:

```jsonc
{
  "schema_version": 1,
  "system": "gc",
  "name": "Nintendo GameCube",
  "controllers": {
    "standard": {
      "buttons": ["a", "b", "x", "y", "z", "start", "l_digital", "r_digital"],
      "dpad":    ["up", "down", "left", "right"],
      "analog":  ["main_x", "main_y", "c_x", "c_y", "l_analog", "r_analog"],
      "rumble":  true
    }
  },
  "default_controller": "standard",
  "glyphs": { "a": "A", "b": "B", "x": "X", "y": "Y", "z": "Z" },
  "positional_default": { "standard": { "a": "face_east", "b": "face_south", "x": "face_north", "y": "face_west" } },
  "meta": { "confirm": "standard.a", "cancel": "standard.b" }
}
```

`positional_default` values are bare physical input names, or `"none"` for an
input that's unbound by default. Full source expressions (modifiers) belong in
rules, not layouts. The complete format, and the conventions chosen for every
system, are documented in [data/layouts/README.md](../data/layouts/README.md).

**Known gaps in the layout format:**
- `label_positions` is one map per system. That's ambiguous for systems where
  controller types have different labels (Wii Wiimote vs Classic). It should be
  keyed by controller type in schema v2.
- There's no shared target vocabulary yet for pointers and motion (Wii IR,
  touchscreens, tilt/shake). Each layout names its own (`pointer_x`, `shake`, ...);
  these should be standardised before the Dolphin Wii, DS/3DS and Vita adapters.

Systems with several controller types (Wii: Wiimote, Wiimote+Nunchuk, Classic;
N64 with Rumble Pak/Controller Pak; PS1 digital vs DualShock; Saturn standard vs
3D pad) list them all, and rules say which one they target.

Systems we need layouts for (v1 → later):
`nes, snes, n64, gc, wii, wiiu, switch, gb/gbc/gba, nds, 3ds, psx, ps2, ps3,
psp, psvita, genesis/megadrive, mastersystem, saturn, dreamcast, xbox, arcade
(mame, fbneo, naomi/atomiswave), pcengine, neogeo, atari2600, 3do, scummvm`.

### 1.3 Binding

```
Binding = (target: "<system>.<controller_type>.<input>", source: SourceExpr)
```

Example: `gc.standard.a ← face_south`.

### 1.4 Hotkeys

Hotkeys are a separate binding namespace: `hotkey.save_state`,
`hotkey.load_state`, `hotkey.menu`, `hotkey.exit`, `hotkey.fast_forward`,
`hotkey.fast_forward_hold`, `hotkey.rewind`, `hotkey.screenshot`, `hotkey.next_slot`, `hotkey.prev_slot`,
`hotkey.toggle_fullscreen`, `hotkey.pause`.
`hotkey.fast_forward` is always the **toggle** (EmuDeck's Select+R2);
`hotkey.fast_forward_hold` is fast-forward while held, for emulators that have
it (owner's decision, 2026-10-22). EmuDeck ships a consistent hotkey
scheme (**[VERIFY]** current combos per emulator). Our shipped defaults should
copy it exactly, so installing map-helper changes nothing the user can feel.

### 1.5 Options

Per-rule, non-binding settings: `rumble: on/off/strength`, `gyro: {source, mode:
"mouse"|"tilt"|"pointer", sensitivity}`, `deadzones`, `analog_trigger_mode`,
`controller_type` (e.g. PS1 DualShock vs digital), `motion_provider`
(emulator-specific DSU / cemuhook vs native SDL).

## 2. Rules and scopes

A **rule** is a partial set of bindings and options, plus *where it applies*.
Rules do not need to be complete. A rule can change just `gc.standard.a` and
`gc.standard.b`.

```jsonc
{
  "id": "user.ds4-family.gc.swap-ab",
  "label": "DS4: Cross = A, Circle = B on GameCube",
  "applies_to": {
    "controller": { "level": "family", "value": "sony.dualshock4" },
    "content":    { "level": "system", "system": "gc" }
  },
  "bindings": {
    "gc.standard.a": { "input": "face_south" },
    "gc.standard.b": { "input": "face_east" }
  },
  "options": { "rumble": { "enabled": true } },
  "enabled": true
}
```

### 2.1 Controller scope levels

From most to least specific:

| Level | Matches | Example value | Typical use |
|-------|---------|---------------|-------------|
| `device` | One physical unit (serial / BT MAC / stable path) | `"mac:a4:ae:12:..."` | "My blue DS4 has a worn stick, give it a bigger deadzone" |
| `model` | Exact hardware model (one or more VID:PID) | `"sony.ds4.v2"` | "DS4 v2 only" |
| `family` | A product line across revisions and connections | `"sony.dualshock4"` | "**All DualShock 4s**" |
| `brand` | All models from one manufacturer | `"8bitdo"` | "**All 8BitDo controllers**" |
| `style` | Layout style, whatever the brand | `"playstation"`, `"xbox"`, `"nintendo"`, `"sega6"`, `"arcade8"`, `"n64"`, `"snes"`, `"steamdeck"` | "Anything with Nintendo-style labels" |
| `any` | Every controller | — | Global defaults |

How a connected controller gets its model, family, brand and style is covered
in [04](04-controller-identification.md). That includes how to handle pads
that hide who they are, like 8BitDo in XInput mode.

### 2.2 Content scope levels

| Level | Matches | Fields |
|-------|---------|--------|
| `game` | One game on one system (optionally one emulator) | `system`, `game_id` (+ optional `emulator`) |
| `emulator` | One emulator, all its systems or one of them | `emulator` (+ optional `system`) |
| `system` | One system, every emulator for it | `system` |
| `global` | Everything | — |

Notes:

- **`system` scope is the main one users will pick.** "GameCube on my DS4" should
  apply in Dolphin *and* in a RetroArch core if one ever handles GC.
- `global` rules can only bind *physical-only* things like options
  (deadzone, rumble) and hotkeys. They can't bind console targets, because
  those are system-specific. One exception is **meta-bindings**: system-agnostic
  aliases such as `meta.confirm`, `meta.cancel`, `meta.primary`, `meta.secondary`,
  which each layout maps to concrete inputs. They make rules like "on all
  Nintendo-style pads, swap confirm/cancel everywhere" possible (see §5).
- `game_id` comes from the adapter (Dolphin game ID like `GALE01`, PS2 serial
  `SLUS-20312`, RetroArch content name, Switch title ID). See [06](06-emulator-adapters.md).

### 2.3 Sources (layers)

| Source | Location | Editable in UI |
|--------|----------|----------------|
| `shipped` | `data/defaults/` (inside the install, read-only) | No (you can "copy to user") |
| `pack` | `$DATA/packs/<pack-id>/` (community or imported packs) | No (enable/disable only) |
| `user` | `$DATA/rules/` | Yes |

## 3. Resolution

Input: player slot `p` with controller `c`, plus target `(system, emulator, game)`.

1. **Collect candidates**: every enabled rule whose controller scope matches
   `c` and whose content scope matches the target.
2. **Score** each candidate with a tuple, compared lexicographically:

   ```
   score = ( source_rank, explicit_priority, content_rank, controller_rank, direct, rule_id )
   source_rank:       user=3, pack=2, shipped=1
   explicit_priority: integer, default 0 (the "always win" escape hatch, see §3.1)
   content_rank:      game=5, emulator+system=4, emulator=3, system=2, global=1
   controller_rank:   device=6, model=5, family=4, brand=3, style=2, any=1
   direct:            1 for a direct binding, 0 for one expanded from a meta-binding (§5)
   rule_id:           final tie-break, so results are the same on every machine
   ```
   Implemented in `core/maphelper/resolve.py` (`score()`).

3. **Merge per key**. For each binding key and option key, the highest-scoring
   candidate that defines it wins. Keys no rule defines fall back to the
   **adapter baseline**: whatever EmuDeck or the emulator already has. In that
   case we don't write the key at all.
4. **Validate**. Check for duplicates (two targets on one source) per the
   layout's `allow_shared_sources` setting, missing required inputs, and
   capability mismatches (gyro rule but the controller has no gyro). Problems
   are warnings, never fatal.
5. **Emit the trace**: `binding → winning rule id, plus the rules it shadowed`.

### 3.1 Why content outranks controller (and how to override)

Ordering is the main judgment call. Two rules for a DS4 on Melee:

- A: `controller=family:dualshock4`, `content=system:gc` → `a ← face_south`
- B: `controller=any`, `content=game:GALE01` → `a ← face_east`

The default ordering is **content first**, so B wins. The reasoning: a
game-specific rule is a deliberate tweak for that game ("Melee needs this"),
while a family rule is a general preference. Users who disagree can set
`explicit_priority` on a rule, and the UI exposes this as "Always win over
game-specific rules". `map-helper explain` always shows the outcome, so the
ordering is never a mystery. This is still an open question; see [12](12-risks-open-questions.md).

### 3.2 Source outranks everything

A user rule at `any/global` beats a shipped rule at `model/game`. If that seems
wrong, remember shipped rules are defaults. Anything a user explicitly set
should beat something they never chose. Shipped rules are still useful because
they fill in keys the user hasn't touched (merging is per key).

## 4. Presets

Presets are **rule templates** offered in the UI. They're not a separate
concept: applying a preset creates a user rule at whatever scope you pick.

| Preset | Effect |
|--------|--------|
| `positional` (default) | Map by physical position, using the layout's `positional_default` (e.g. SNES B → `face_south`, SNES A → `face_east`). |
| `label-match` | Map by printed label where both sides use letters: Nintendo A = the controller's button labelled "A". With a Nintendo-style pad this matches positional for Nintendo systems. |
| `nintendo-confirm-swap` | For Nintendo systems, swap the east/south confirm behaviour. |
| `southpaw` | Swap sticks. |
| `fightpad-6` | Put a 6-button arcade layout on face + shoulders (Genesis, Saturn, Street Fighter on arcade). |
| `n64-c-buttons-on-right-stick` / `n64-c-buttons-on-face` | Common N64 options. |
| `trigger-as-digital` | Treat analog triggers as buttons. |
| `gyro-aim` | Turn on gyro → right stick or pointer where supported. |

## 5. Meta-bindings

So users can write one rule that works across all systems:

```jsonc
// data/layouts/snes.json (excerpt)
"meta": { "confirm": "standard.a", "cancel": "standard.b", "primary": "standard.b", "secondary": "standard.y" }
```

A rule binding `meta.confirm ← face_south` expands per system through each
layout's `meta` map. Expansion happens before merging, and expanded keys rank
**one notch below** directly-bound keys at the same scope, so explicit system
rules still win.

## 6. Multi-controller-type systems

- Wii: a rule targets `wii.wiimote_nunchuk.*` or `wii.classic.*`. The
  adapter's per-game or per-rule option `controller_type` picks which
  emulated device is plugged in.
- PS1: `psx.dualshock.*` vs `psx.digital.*`; `controller_type` defaults to DualShock.
- N64: `n64.standard.*` plus option `pak: rumble|memory|transfer|none`.

## 7. Versioning

Every rule file has `"schema_version": 1`. The store runs forward migrations on
load and writes back on the next save. The canonical vocabulary (input names,
layout keys) is versioned the same way. Renames go through an alias table and
are never broken.
