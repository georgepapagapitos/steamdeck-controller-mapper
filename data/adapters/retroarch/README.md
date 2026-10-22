# RetroArch adapter data

Data the RetroArch adapter reads. The prose explanation is in
[docs/adapters/retroarch.md](../../../docs/adapters/retroarch.md).

| File | What it holds |
|------|---------------|
| `retropad.json` | RetroPad ids, analog half-axis ids, canonical physical input → RetroPad (positional), `.rmp` key naming and value rules, `retroarch.cfg` bind value syntax, Steam virtual pad button indices per autoconfig profile |
| `hotkeys.json` | Hotkey target → `retroarch.cfg` base, the enable bind, every meta bind base (for conflict warnings), and per joypad driver (`sdl2` only) the button/axis index of each canonical input |
| `cores/<id>.json` | One descriptor per core: remap directory name, `.so` names, systems, device type ids, and canonical target → RetroPad |

Every fact was read from source at a pinned commit. The URLs in each
descriptor's `sources` point at those lines.

## Core descriptor shape

```jsonc
{
  "core": "Genesis Plus GX",               // retro_system_info.library_name = remap dir name
  "core_files": ["genesis_plus_gx_libretro.so"],
  "systems": ["genesis", "mastersystem"],
  "sources": ["https://github.com/..."],
  "device_types": {"genesis.6button": 513}, // optional: value for input_libretro_device_pN
  "core_options": {...},                    // optional: core options that change the pad type
  "targets": {"genesis.6button.x": "L"},   // canonical target -> RetroPad input the core reads
  "core_option_variants": {...},           // optional: target tables under non-default core options
  "c_button_chord": {...},                 // optional (N64 cores): chorded alternative bindings
  "notes": "..."
}
```

`targets` values use the names in `retropad.json`: `B Y SELECT START UP DOWN
LEFT RIGHT A X L R L2 R2 L3 R3` for buttons, `LEFT_X LEFT_Y RIGHT_X RIGHT_Y`
for full axes, and `LEFT_X+ LEFT_X- LEFT_Y+ LEFT_Y- RIGHT_X+ RIGHT_X- RIGHT_Y+
RIGHT_Y-` for half-axes (Y- is up). A trigger listed as `L2`/`R2` is read
both as a button and as an analog trigger (`RETRO_DEVICE_INDEX_ANALOG_BUTTON`)
by cores that support analog triggers.

`device_types` keys are canonical controller types (`<system>.<type>`), except
FBNeo, whose types are layout styles (`classic`, `modern`, `6panel`). Values are
libretro device ids: `RETRO_DEVICE_SUBCLASS(base, i) = ((i + 1) << 8) | base`,
with `JOYPAD = 1` and `ANALOG = 5`. The ids are **per core**: DualShock is 517
in Beetle PSX and 261 in SwanStation.

## Cores

| File | `core` (remap dir) | Systems |
|------|--------------------|---------|
| `snes9x.json` | `Snes9x` | snes |
| `mesen.json` | `Mesen` | nes, fds |
| `nestopia.json` | `Nestopia` | nes, fds |
| `mgba.json` | `mGBA` | gba, gb, gbc |
| `gambatte.json` | `Gambatte` | gb, gbc |
| `genesis_plus_gx.json` | `Genesis Plus GX` | genesis, segacd, mastersystem, gamegear, sg1000 |
| `picodrive.json` | `PicoDrive` | genesis, segacd, 32x, mastersystem, gamegear, sg1000 |
| `beetle_psx_hw.json` | `Beetle PSX HW` | psx |
| `swanstation.json` | `SwanStation` | psx |
| `mupen64plus_next.json` | `Mupen64Plus-Next` | n64 |
| `parallel_n64.json` | `ParaLLEl N64` | n64 |
| `beetle_saturn.json` | `Beetle Saturn` | saturn |
| `fbneo.json` | `FinalBurn Neo` | arcade, neogeo, cps1/2/3 |
| `flycast.json` | `Flycast` | dreamcast, naomi, atomiswave |
| `melonds_ds.json` | `melonDS DS` | nds |
| `ppsspp.json` | `PPSSPP` | psp |
| `dolphin.json` | `dolphin-emu` | gc, wii |

Not yet covered from the doc 06 list: bsnes, MAME 2003-Plus.

## Invented canonical input names

Only `snes` and `gc` have layout files today (`data/layouts/`). The names below
were invented for the descriptors and must be copied into the layout files
when those are written. Every controller type below also has
`up/down/left/right`.

| Controller type | Inputs |
|-----------------|--------|
| `nes.standard` | `a b turbo_a turbo_b start select` |
| `fds.standard` | as `nes.standard` + `insert_next_disk switch_disk_side eject_disk` |
| `gb.standard`, `gbc.standard` | `a b turbo_a turbo_b start select` |
| `gba.standard` | `a b l r turbo_a turbo_b turbo_l turbo_r start select` |
| `genesis.3button`, `segacd.3button`, `32x.3button` | `a b c start` |
| `genesis.6button`, `segacd.6button`, `32x.6button` | `a b c x y z mode start` |
| `mastersystem.standard` | `button_1 button_2 pause` |
| `gamegear.standard` | `button_1 button_2 start` |
| `sg1000.standard` | `button_1 button_2` |
| `psx.digital` | `cross circle square triangle l1 r1 l2 r2 start select` |
| `psx.dualshock` | as `psx.digital` + `l3 r3 left_x left_y right_x right_y` |
| `n64.standard` | `a b z l r start c_up c_down c_left c_right stick_x stick_y` |
| `saturn.standard` | `a b c x y z l r start` |
| `saturn.3d` | as `saturn.standard` + `analog_x analog_y l_analog r_analog mode` |
| `arcade.generic` | `button1`–`button9 coin start` |
| `arcade.sf6` | `lp mp hp lk mk hk coin start` |
| `neogeo.standard` | `a b c d coin start` |
| `dreamcast.standard` | `a b x y start analog_x analog_y l_trigger r_trigger` |
| `naomi.standard`, `atomiswave.standard` | `button1`–`button8 start coin test service` |
| `nds.standard` | `a b x y l r start select microphone` |
| `psp.standard` | `cross circle square triangle l r start select analog_x analog_y` |
| `wii.wiimote` | `a b one two plus minus home shake tilt_x tilt_y` |
| `wii.wiimote_sideways` | as `wii.wiimote` |
| `wii.wiimote_nunchuk` | `a b c z one two plus minus home shake nunchuk_shake nunchuk_x nunchuk_y tilt_x tilt_y` |
| `wii.classic`, `wii.classic_pro` | `a b x y l r zl zr plus minus home left_x left_y right_x right_y` |

`gc.standard` uses the names already in `data/layouts/gc.json`.

## Using a descriptor

For binding `T ← P` (canonical target `T`, physical input `P`):

1. `dst = core.targets[T]` (what the core must receive).
2. `src = retropad.physical_to_retropad[P]` (what autoconfig produces for `P`).
3. Write `input_player<N>_btn_<src> = "<id(dst)>"` (or `_stk_` for a half-axis source).
4. Every RetroPad source not used by any binding must be written explicitly:
   either to its identity id (if its own id is not claimed by another source)
   or to `-1`. A remap is not a swap (see `retropad.json` `remap_file.swap_rule`).
