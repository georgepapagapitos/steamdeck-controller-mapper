# Console layouts

One JSON file per system: `data/layouts/<system>.json`. A layout lists the
system's controller type(s) and their inputs (the **target** side of a binding),
plus the defaults and metadata that presets and meta-bindings use. The model is
described in [docs/03-canonical-model.md](../../docs/03-canonical-model.md) §1.2, §4, §5 and §6.

A binding target is `<system>.<controller_type>.<input>`, e.g.
`n64.standard.c_up` or `wii.classic.zl`.

## Format

```jsonc
{
  "schema_version": 1,
  "system": "saturn",                    // must equal the file name (saturn.json)
  "name": "Sega Saturn",                 // display name
  "controllers": {                       // one entry per emulated controller type
    "3d": {
      "buttons": ["a", "b", "c", "l", "r", "start"],   // digital targets
      "dpad":    ["up", "down", "left", "right"],      // d-pad targets ([] if none)
      "analog":  ["stick_x", "stick_y", "l_analog"],   // axes, triggers, pointers, motion ([] if none)
      "rumble":  false,                                // emulated device can rumble
      "allow_shared_sources": ["l+l_analog"]           // optional, see below
    }
  },
  "default_controller": "standard",      // the type used when a rule/option doesn't choose
  "glyphs": { "a": "A", "start": "START" },            // display label per button
  "positional_default": {                // per controller type: input -> physical source
    "3d": { "b": "face_south", "stick_x": "ls_x", "l_analog": "l2" }
  },
  "label_positions": { "a": "east" },    // optional, letter-labelled pads only
  "meta": { "confirm": "standard.c", "cancel": "standard.b", "primary": "standard.b", "secondary": "standard.c" },
  "_notes": "free text: conventions chosen, open questions, [VERIFY] items"
}
```

### Fields

| Field | Required | Meaning |
|-------|----------|---------|
| `schema_version` | yes | Layout schema version (currently `1`). Migrated like rule files (docs/03 §7). |
| `system` | yes | System id. Same as the file name and the first part of every target. |
| `name` | yes | Display name. |
| `controllers` | yes | Map of controller type id to its input lists. Several types when the system had genuinely different pads (docs/03 §6). An adapter picks the emulated device from the `controller_type` option. |
| `controllers.<t>.buttons` | yes | Digital targets. Every button has a `glyphs` entry. |
| `controllers.<t>.dpad` | yes | D-pad targets, always `up/down/left/right` when present; `[]` if the pad has none. Arcade joysticks are modelled as a d-pad. |
| `controllers.<t>.analog` | yes | Continuous targets: stick axes, analog triggers, pointers (touch, IR, mouse) and `motion`. `[]` if none. |
| `controllers.<t>.rumble` | yes | Whether the emulated device (or its usual accessory: Rumble Pak, Jump Pack, rumble carts) supports rumble. |
| `controllers.<t>.allow_shared_sources` | no | List of `"<input>+<input>"` pairs that may be bound to the same physical source without a duplicate warning (resolution step 4). Used for digital+analog trigger pairs (gc, wii classic, saturn 3d) and the two axes of a 2D surface bound to `touchpad` (3ds, wiiu, psvita). |
| `default_controller` | yes | The controller type assumed when nothing picks one. |
| `glyphs` | yes | Button id to short display label. Buttons only (not dpad/analog). One map per system, shared by every controller type. |
| `positional_default` | yes | Per controller type, a complete map of target input to a physical source name from docs/03 §1.1, or `"none"` (explicitly unbound). This is what the `positional` preset applies. |
| `label_positions` | no | Where each letter-labelled face button sits on the **original** pad, as `north/south/east/west`. Used by the `label-match` and `nintendo-confirm-swap` presets. Only on Nintendo systems. It is one flat map; on wii it describes the Classic Controller. |
| `meta` | yes | `confirm`, `cancel`, `primary`, `secondary`, each a `"<controller_type>.<input>"` button. Used to expand meta-bindings (docs/03 §5). |
| `_notes` | no | Human-readable notes on judgment calls. Ignored by code. |

### Source values in `positional_default`

Values are bare physical input names: `face_*`, `dpad_*`, `l1 r1 l2 r2 l3 r3`,
`ls_x ls_y rs_x rs_y`, half-axes `ls_up` … `rs_right`, `start select guide misc1`,
`touchpad touchpad_click gyro accel`, or `none`. They are shorthand for
`{ "input": "<name>" }`. Modifiers (threshold, invert, deadzone) belong in rules,
not layouts.

- Binding an analog target to a 2D source (`touchpad`, `gyro`) from both its
  `_x` and `_y` targets means "use the matching axis of that source".
- Binding a digital target to an analog source (`l2`) implies digital mode with
  the default threshold.
- Binding a button to a half-axis (`rs_up`) means "pressed when the stick is
  pushed that way".

## Naming conventions

- Everything is lowercase `snake_case`. Controller type ids describe the pad
  (`dualshock`, `six_button`, `wiimote_nunchuk`, `pro`, `generic`); use
  `standard` when the system has one pad.
- Button ids use the console's own label, spelled out where it is a symbol or
  number: `cross circle square triangle`, `one two`, `plus minus`, `i ii iii`,
  `button1`…`button8`. Native names (`l1`, `l3`, `zl`) are kept even when they
  collide with physical names. Targets are always namespaced, so they can't be confused.
- D-pad: `up down left right`.
- Sticks: `stick_x/stick_y` on single-stick pads, `lstick_x/lstick_y/rstick_x/rstick_y`
  on dual-stick pads; system-native names where they exist (gc `main_*`/`c_*`,
  3ds `circle_*`/`cstick_*`, wii `nunchuk_*`).
- Triggers: `l_digital`/`r_digital` + `l_analog`/`r_analog` when the hardware
  reports both; `l_trigger`/`r_trigger` when analog only; `l2`/`r2` in `analog`
  on ps3 (native name).
- Pointers: `<surface>_x` / `<surface>_y` analog plus `<surface>_press` button
  (`touch_*`, `front_touch_*`, `rear_touch_*`, `ir_*`, `pointer_*`).
- Motion: one analog target `motion` (gyro+accel), bound to `gyro`. Wii `tilt` binds to `accel`.

## Systems

| System | Controller types (default first) | Conventions chosen |
|--------|-----------------------------------|--------------------|
| nes | standard | RetroPad: B=south, A=east |
| snes | standard | B/A/Y/X = south/east/west/north (label positions) |
| n64 | standard | A=south, B=west, Z=l2, L=l1, R=r1, C buttons on right-stick half-axes; `pak` option |
| gc | standard | A=south, B=west, X=east, Y=north, Z=r1, L/R digital+analog on l2/r2 |
| wii | wiimote_nunchuk, wiimote, classic | IR pointer on right stick (gyro opt-in), Wiimote upright: A=south, B=r2, 1=west, 2=north, shake=r1; Nunchuk C=l1, Z=l2; Classic analog L/R on l2/r2, ZL/ZR on l1/r1 |
| wiiu | gamepad, pro | Nintendo positions, ZL/ZR=l2/r2, touch on touchpad, motion=gyro |
| switch | pro | Nintendo positions (Xbox A = Switch B), capture=misc1, motion=gyro |
| gb | standard | as nes |
| gbc | standard | as nes; rumble for rumble carts |
| gba | standard | as nes plus L/R=l1/r1; rumble for rumble carts |
| nds | standard | SNES positions; touch pointer on right stick, tap=r3; lid unbound |
| 3ds | standard | SNES positions; circle pad=ls, C-stick=rs, ZL/ZR=l2/r2, touch on touchpad, home=guide |
| psx | dualshock, digital | cross/circle/square/triangle = south/east/west/north; analog button unbound; cross confirms |
| ps2 | dualshock2 | as psx; pressure via source analog value |
| ps3 | dualshock3 | as psx; L2/R2 analog; ps=guide; sixaxis=gyro |
| psp | standard | as psx; L/R=l1/r1; home unbound |
| psvita | standard | as psx; front touch on touchpad, rear touch unbound |
| genesis | three_button, six_button | GPGX: A/B/C = west/south/east, X=l1, Y=north, Z=r1, Mode=select |
| mastersystem | standard | 1=south, 2=east, pause=start |
| saturn | standard, 3d | as genesis six_button, L/R=l2/r2 (analog on 3d pad) |
| dreamcast | standard | labels match Xbox positions; analog triggers on l2/r2 |
| xbox | standard | 1:1 with Xbox pad; white=l1, black=r1 |
| arcade | generic | MAME XInput order: B1–B4 = south/east/west/north, B5–B8 = l1/r1/l2/r2; coin=select |
| pcengine | two_button, six_button | II=south, I=east, run=start |
| neogeo | standard | A/B=south/east, C/D=west/north; select=coin |
| atari2600 | joystick, paddle | fire=south; console switches on start/select/l1/r1/l2; paddle=ls_x |
| 3do | standard | as genesis: A/B/C = west/south/east; P=start, X=select |
| scummvm | standard | pointer=ls; left click=south, right click=east, skip(Esc)=west, skip line=north, menu=start |

Items marked **[VERIFY]** in a file's `_notes` must be checked against
the emulator/core defaults EmuDeck ships (spike S7) before they become shipped defaults.
