# Adapter: RetroArch

## Summary

| Field | Value |
|-------|-------|
| Adapter id | `retroarch` |
| Systems | Many, via **core descriptors** (`data/adapters/retroarch/cores/*.json`) |
| EmuDeck install type | Flatpak `org.libretro.RetroArch` **[VERIFY]** (S7) |
| Versions covered | Source read at RetroArch master `eb7335f` (reports 1.22.2); remap and autoconfig logic checked against tag `v1.22.2` |
| Priority | **P0** |
| Strategy | global-swap of **core-level remap files**, rewritten at each launch |

Facts below are from source. Each section names the file and function, and the
[Sources](#sources) list pins the commits. Claims still tagged **[VERIFY]**
need a device or EmuDeck's shipped config.

## Paths

| What | Flatpak |
|------|---------|
| Config root | `~/.var/app/org.libretro.RetroArch/config/retroarch/` (RetroArch uses `$XDG_CONFIG_HOME/retroarch`, `frontend_unix_get_env`; Flatpak sets `XDG_CONFIG_HOME` to `~/.var/app/<id>/config`) **[VERIFY]** EmuDeck does not move it |
| Main config | `retroarch.cfg` in the config root |
| Remap dir | `input_remapping_directory`; default `<config root>/config/remaps` (`DEFAULT_DIR_REMAP` = `DEFAULT_DIR_MENU_CONFIG` + `remaps`) |
| Remaps | `<remap dir>/<library_name>/<game>.rmp`, `<remap dir>/<library_name>/<content dir name>.rmp`, `<remap dir>/<library_name>/<library_name>.rmp` |
| Overrides | `<config root>/config/<library_name>/<library_name>.cfg`, `<content dir>.cfg`, `<game>.cfg` |
| Autoconfig | `joypad_autoconfig_dir`, scanned as `<dir>/<input_joypad_driver>/*.cfg` (`udev`, `sdl2`, `sdl3`). Default is `$LIBRETRO_AUTOCONFIG_DIRECTORY`, else `/usr/local/share/libretro/autoconfig` or `/usr/share/libretro/autoconfig` if present, else `<config root>/autoconfig` **[VERIFY]** which one the Flatpak resolves to |

`<library_name>` is the core's `retro_system_info.library_name`, verbatim
(`config_load_remap`: `core_name = sys_info->info.library_name`). It is a
display string with spaces (`Genesis Plus GX`, `Beetle PSX HW`), not the `.so`
name. The table in [data/adapters/retroarch/README.md](../../data/adapters/retroarch/README.md)
lists it per core.

If `input_remap_sort_by_controller_enable = true` (default false), every remap
path gains a level: `<remap dir>/<library_name>/<sanitized display name of
user 1's device>/...`.

## How input flows in RetroArch

```
physical device ──autoconfig──▶ RetroPad (per user) ──remap──▶ core port ──core──▶ console button
```

1. **Autoconfig** maps a *device* onto the **RetroPad**. The RetroPad is
   SNES-positional: B = south, A = east, Y = west, X = north (`libretro.h`
   comments on `RETRO_DEVICE_ID_JOYPAD_*`).
2. **Remaps** (`.rmp`) re-route RetroPad inputs per user, and route users to
   core ports. One remap file is active at a time.
3. The **core** maps RetroPad ids onto the emulated console. The core
   descriptors record that mapping.

With Steam Input on, the device is always the Steam virtual pad, so autoconfig
is the same for every physical controller. **Per-controller differences must go
into remaps**, which we rewrite at each launch based on who is connected.

## Remap file format

Plain RetroArch config (`key = "value"`). Read by `input_remapping_load_file`
and written by `input_remapping_save_file` (`configuration.c`).

```
input_libretro_device_p1 = "513"
input_remap_port_p1 = "0"
input_player1_analog_dpad_mode = "0"
input_player1_btn_b = "8"
input_player1_btn_a = "0"
input_player1_stk_r_y- = "9"
```

### Key and value semantics (resolved)

- **The key is the source, the value is the target.** The key names the
  RetroPad input that user N's device produces (after autoconfig). The value is
  the RetroPad id the **core** receives. `input_player1_btn_b = "8"` means
  "pressing RetroPad B sends A to the core". In `input_driver_poll` the loop reads
  `remap_button = input_remap_ids[user][j]` for each pressed source `j` and sets
  bit `remap_button`. This is true at `v1.22.2` and master.
- **Absent key = identity.** Defaults are `remap_ids[i][j] = j`
  (`input_remapping_defaults_into`). The writer omits identity entries.
- **A source remapped away stops reaching its own id.** `input_state_device` drops the
  original bit when `remap_ids[id] != id`. So **remaps are not swaps**: to
  exchange A and B write both `btn_a = "0"` and `btn_b = "8"`. Writing only
  `btn_b = "8"` leaves both B and A driving A, and nothing driving B.
- **Values:** `0`–`15` = RetroPad button ids, `16`–`23` = analog half-axes
  (`RARCH_ANALOG_LEFT_X_PLUS` = 16 … `RARCH_ANALOG_RIGHT_Y_MINUS` = 23),
  `-1` = unmapped (`RARCH_UNMAPPED` = 1024 in memory). Out-of-range values
  are clamped to unmapped. A button may drive a half-axis (full deflection).
- **Key suffixes:** `btn_` + `b y select start up down left right a x l r l2
  r2 l3 r3`; `stk_` + `l_x+ l_x- l_y+ l_y- r_x+ r_x- r_y+ r_y-`. The stick keys
  contain literal `+`/`-`. `key_` + the same suffixes is the keyboard mapper
  (value = `RETROK_*`), which we do not manage.
- **Stick values:** an `stk_` source mapped to `16`–`23` copies the axis; the
  sign is flipped when source and target differ in parity. Mapped to `0`–`15`,
  it presses that button above `input_axis_threshold`.
- **`input_libretro_device_pN`** = libretro device id for core port N. The ids
  are core-specific subclasses, `((index + 1) << 8) | base` with JOYPAD = 1 and
  ANALOG = 5. Example: DualShock is 517 in Beetle PSX and 261 in SwanStation.
- **`input_remap_port_pN`** = the 0-based core port that **user** N feeds.
  Several users may feed one port. `N` in `input_playerN_*` is the RetroArch
  user, not the core port.
- **`input_playerN_analog_dpad_mode`**: 0 none, 1 left stick, 2 right stick,
  3/4 forced left/right, 5 left+right, 6 twinstick, 7/8 forced variants
  (`enum analog_dpad_mode`). While it is non-zero, the core's
  `RETRO_DEVICE_ANALOG` reads return 0.
- The writer also writes `input_turbo_*` keys. It always writes
  `input_libretro_device_pN`, `analog_dpad_mode` and `input_remap_port_pN` for
  users `1..input_max_users`, and writes `-1` only for ids the core declared a
  descriptor for.

Full rules: [data/adapters/retroarch/retropad.json](../../data/adapters/retroarch/retropad.json).

## Load precedence and save behaviour (resolved)

`config_load_remap` (`configuration.c`) runs at core init when
`auto_remaps_enable = true` (default true). It tries, in order:

1. game: `<remap dir>/<library_name>/<game basename>.rmp`
2. content dir: `<remap dir>/<library_name>/<parent dir name of the content>.rmp`
3. core: `<remap dir>/<library_name>/<library_name>.rmp`

**The first file that exists wins and the search stops.** Files do not layer:
`input_remapping_load_file` resets every remap to defaults before applying the
file. A game or directory `.rmp` therefore hides our core-level file
completely, not just the keys it sets.

With EmuDeck's `roms/<system>/` layout, the content-dir file is effectively a
per-system remap for that core (`remaps/Snes9x/snes.rmp`) **[VERIFY]** the
directory names EmuDeck uses.

**`remap_save_on_exit`** (default **true**, `DEFAULT_REMAP_SAVE_ON_EXIT`): when
content closes or RetroArch quits, `input_remapping_deinit(true)` rewrites
**whichever file was loaded** from memory (`runloop_event_deinit_core`,
`retroarch_main_quit_finish`). RetroArch normalises our file (drops comments,
adds turbo/device keys) and saves any change the user made in Quick Menu →
Controls into it. When it is false, the menu shows "Flush Remap File" instead.

What the save writes (`input_remapping_save_file`): a new file from memory,
keys sorted, with `input_libretro_device_pN`, `input_playerN_analog_dpad_mode`
and `input_remap_port_pN` for every port below `input_max_users`, the remap
keys that aren't identity (identity ones are left out; unmapped ones are `-1`,
or left out when the core doesn't describe that input), and the `input_turbo_*`
settings. On a Deck the save also lost player 2's lines, for reasons not yet
known **[VERIFY]** ([13](../13-research-spikes.md)). mh-run writes the whole
managed set at every launch, so the next launch puts them back.

**Telling RetroArch's save from a replacement.** The writer would otherwise
take a changed `.rmp` we created for someone else's file (see
[09](../09-storage-safety-sync.md), the manifest). `saved_on_exit` in the
adapter calls it RetroArch's own save, still ours, when all of these hold:

- `remap_save_on_exit` isn't `"false"` in `retroarch.cfg`;
- the file has `input_libretro_device_p1`, which every save writes;
- every `input_playerN_btn_*`/`_stk_*` key in it is one we last wrote, with
  our value. Keys of ours that are missing are fine (identity, or dropped).

EmuDeck's ABXY toggle renames its shipped `<core>.rmp.disabled` over the file:
four `input_player1_btn_*` lines and no device line, so it fails the second
test. A Quick Menu edit saved on quit fails the third, and a save made by hand
with `remap_save_on_exit` off fails the first; both make the file the user's.
Not covered: an EmuDeck file that RetroArch had loaded and saved, renamed over
ours, whose remaps all equal ours. Restore then deletes a file that holds the
same remaps as ours.

**`config_save_on_exit`** (default **true**): `retroarch.cfg` is rewritten at
quit (`CMD_EVENT_MENU_SAVE_CURRENT_CONFIG` in `retroarch_main_quit_finish`).
`config_save_file` reads the existing file and overwrites the keys it knows,
and skips the save while a config override is active. Settings from
`--appendconfig` files are written into the main config on save unless the
appended file sets `config_save_on_exit = "false"` (`retroarch --help` text).

## Autoconfig

`tasks/task_autodetect.c`, `input_autoconfigure_get_config_file_affinity`:

| Match | Score |
|-------|-------|
| `input_vendor_id` + `input_product_id` equal and non-zero | +30 |
| `input_device` equals the device name exactly | +20 |
| `input_phys` is a substring of the device's phys (only once one of the above matched) | +10, else −10 |

The highest score wins. Up to 9 alternatives (`input_device_alt1`,
`input_vendor_id_alt1`, …) are scored too. `input_driver` inside the file is
**not** part of matching; the directory is. In `v1.22.2` the
`<autoconfig dir>/<driver>/` directory is scanned, and the base directory only
if the driver directory is empty. On master both are scanned, base first, and
the first directory with a match ends the search. Files also carry binds
(`input_b_btn`, `input_l2_axis`, …), labels (`*_label`),
`input_device_display_name` and optional per-device deadzones.

A user bind in `retroarch.cfg` beats the autoconfig bind; the autoconfig bind
applies only when the user bind is `nul` (`input_key_pressed`).

Joypad driver default on Linux: `udev`; Steam builds with SDL: `sdl2`
(`JOYPAD_DEFAULT_DRIVER`). EmuDeck sets `input_joypad_driver = "sdl2"` (its
shipped `retroarch.cfg`, and the owner's captured one).

### Steam virtual pad profiles (shipped)

`retroarch-joypad-autoconfig` ships one for each driver. Both match the
virtual pad by VID 10462 (`0x28DE`) / PID 4607 (`0x11FF`), so they win on
VID/PID even if the name differs. Both are positional (B = south).

`sdl2/Steam Virtual Gamepad.cfg` (binds; labels omitted):

```
input_driver = "sdl2"
input_device = "Steam Virtual Gamepad"
input_vendor_id = "10462"
input_product_id = "4607"
input_b_btn = "0"
input_y_btn = "2"
input_select_btn = "4"
input_start_btn = "6"
input_up_btn = "11"
input_down_btn = "12"
input_left_btn = "13"
input_right_btn = "14"
input_a_btn = "1"
input_x_btn = "3"
input_l_btn = "9"
input_r_btn = "10"
input_l2_axis = "+4"
input_r2_axis = "+5"
input_l3_btn = "7"
input_r3_btn = "8"
input_l_x_plus_axis = "+0"
input_l_x_minus_axis = "-0"
input_l_y_plus_axis = "+1"
input_l_y_minus_axis = "-1"
input_r_x_plus_axis = "+2"
input_r_x_minus_axis = "-2"
input_r_y_plus_axis = "+3"
input_r_y_minus_axis = "-3"
```

`udev/Steam Input x-box.cfg` (binds; labels omitted):

```
input_driver = "udev"
input_device = "Microsoft X-Box 360 pad"
input_vendor_id = "10462"
input_product_id = "4607"
input_up_btn = "h0up"
input_down_btn = "h0down"
input_left_btn = "h0left"
input_right_btn = "h0right"
input_a_btn = "1"
input_b_btn = "0"
input_y_btn = "2"
input_x_btn = "3"
input_select_btn = "6"
input_start_btn = "7"
input_l_btn = "4"
input_r_btn = "5"
input_l2_axis = "+2"
input_r2_axis = "+5"
input_l3_btn = "9"
input_r3_btn = "10"
input_l_y_plus_axis = "+1"
input_l_y_minus_axis = "-1"
input_l_x_plus_axis = "+0"
input_l_x_minus_axis = "-0"
input_r_y_plus_axis = "+4"
input_r_y_minus_axis = "-4"
input_r_x_plus_axis = "+3"
input_r_x_minus_axis = "-3"
input_menu_toggle_btn = "8"
```

The udev profile binds Guide to menu toggle. **[VERIFY]** the virtual pad's
actual evdev/SDL name on current SteamOS. VID/PID matching makes it matter
less, except for `input_remap_sort_by_controller_enable` directory names.

## Bind value syntax (`retroarch.cfg`, autoconfig)

Values are **device indices for the active joypad driver**, written by
`save_keybind_joykey` / `save_keybind_hat` / `save_keybind_axis`:

| Kind | Key suffix | Value |
|------|-----------|-------|
| Button | `_btn` | `"<n>"`, e.g. `"4"` |
| Hat | `_btn` | `"h<hat><dir>"`, e.g. `"h0up"` |
| Axis | `_axis` | `"+<n>"` / `"-<n>"` |
| Unbound | `_btn` / `_axis` | `"nul"` |
| Keyboard | none | key name, e.g. `"f2"` |

So the same physical button is `"4"` under `sdl2` and `"6"` under `udev` for
Select on the Steam virtual pad. Hotkey writes must know the driver.

## Core descriptors

`data/adapters/retroarch/cores/<id>.json`. Example:

```jsonc
{
  "core": "Snes9x",                       // library_name = remap dir name
  "core_files": ["snes9x_libretro.so"],
  "systems": ["snes"],
  "sources": ["https://github.com/libretro/snes9x/blob/<commit>/libretro/libretro.cpp#L1081"],
  "targets": {
    "snes.standard.b": "B", "snes.standard.a": "A",
    "snes.standard.y": "Y", "snes.standard.x": "X",
    "snes.standard.l": "L", "snes.standard.r": "R",
    "snes.standard.start": "START", "snes.standard.select": "SELECT",
    "snes.standard.up": "UP", "snes.standard.down": "DOWN",
    "snes.standard.left": "LEFT", "snes.standard.right": "RIGHT"
  }
}
```

RetroPad ids (`RETRO_DEVICE_ID_JOYPAD_*`, `libretro.h`, confirmed): B=0, Y=1,
SELECT=2, START=3, UP=4, DOWN=5, LEFT=6, RIGHT=7, A=8, X=9, L=10, R=11, L2=12,
R2=13, L3=14, R3=15.

Canonical physical → RetroPad (positional, via either Steam virtual pad
profile): `face_south→B, face_east→A, face_west→Y, face_north→X, l1→L, r1→R,
l2→L2, r2→R2, l3→L3, r3→R3, select→SELECT, start→START, dpad_*→UP/DOWN/LEFT/RIGHT`.
`guide`, `misc1`, paddles, touchpad and gyro have no RetroPad id, so they can
never be a remap source.

**Composition:** for binding `snes.standard.a ← face_south`, target RetroPad
= `A` (from the core descriptor), source RetroPad = `B` (from the physical →
RetroPad table). We write `input_player1_btn_b = "8"`. Because remaps are not
swaps, the adapter must also write the displaced source: for the full SNES
Nintendo-confirm swap, `input_player1_btn_a = "0"`. Any source left driving a
target that another source now claims must be set to `-1` or to its new
target.

### Core highlights

Full tables are in the descriptors. These are the ones that matter most:

| Core (`library_name`) | Mapping highlights |
|-----------------------|--------------------|
| Genesis Plus GX, PicoDrive | Genesis A=`Y`, B=`B`, C=`A`, X=`L`, Y=`X`, Z=`R`, Mode=`SELECT`, Start=`START`. SMS button 1=`B`, 2=`A`. GPGX pad type via `input_libretro_device_pN` (3B=257, 6B=513, MS 2B=769, 1 = auto). PicoDrive pad type via core option `picodrive_input1` (`3 button pad` default / `6 button pad`) |
| Mupen64Plus-Next | A=`B`, B=`Y`, Z=`L2`, L=`L`, R=`R`, Start. **C buttons = right stick** (digital, threshold 0x4000). Holding `R2` turns `A/Y/B/X` into C-right/left/down/up (options `mupen64plus-{r,l,d,u}-cbutton`, default C1..C4 = A, Y, B, X). `mupen64plus-alt-map=True`: C = `X`(up) `A`(down) `L`(left) `R`(right), L=`SELECT`, R=`R2`. Pak: core option `mupen64plus-pak1` (default `memory`) |
| ParaLLEl N64 | Same default table and descriptors as Mupen64Plus-Next; option `parallel-n64-alt-map`. Holding `SELECT` toggles built-in per-game layouts (Killer Instinct Gold, ClayFighter, ISS, Ridge Racer…). The R2 chord's C-button ids are never assigned in source (all read RetroPad B) **[VERIFY]** on device |
| Beetle Saturn | A=`B`, B=`A`, C=`R`, X=`Y`, Y=`X`, Z=`L`, L=`L2`, R=`R2`. 3D Pad = device 261 (`SELECT` = mode switch) |
| Beetle PSX HW, SwanStation | Cross=`B`, Circle=`A`, Square=`Y`, Triangle=`X`, L1/R1=`L`/`R`, L2/R2=`L2`/`R2`. Digital = device 1; DualShock = 517 (Beetle) / 261 (SwanStation) |
| FBNeo | Generated per game: fire 1..9 = `B A Y X R L R2 L2 R3` (classic, default device 5). 3P+3K games: LP/MP/HP = `Y X L`, LK/MK/HK = `B A R`. Neo Geo A–D = `B A Y X`. Coin = `SELECT` |
| Flycast | DC A=`B`, B=`A`, X=`Y`, Y=`X`, triggers `L2`/`R2` (analog). NAOMI/AW buttons 1–8 = `B A Y X R L R2 L2`, coin = `SELECT` |
| dolphin-emu | **Label-based, not positional:** GC A=`A`, B=`B`, X=`X`, Y=`Y`, Z=`R`, L/R=`L2`/`R2`. Wii devices via `input_libretro_device_pN` (Wiimote 1, sideways 513, +Nunchuk 769, +Classic 1025, +Classic Pro 1281) |

## Managed keys

- In the core-level `.rmp`: `input_playerN_btn_*`, `input_playerN_stk_*`,
  `input_playerN_analog_dpad_mode`, `input_libretro_device_pN`,
  `input_remap_port_pN`, for the users we resolve. We leave the `input_turbo_*`
  keys RetroArch writes untouched.
- In `retroarch.cfg`: hotkeys, by exact name: `input_<base>_btn`
  and `input_<base>_axis` for `enable_hotkey` and each base in
  [hotkeys.json](../../data/adapters/retroarch/hotkeys.json) `targets`
  (`menu_toggle`, `exit_emulator`, `save_state`, `load_state`,
  `state_slot_increase`, `state_slot_decrease`, `toggle_fast_forward`,
  `hold_fast_forward`, `rewind`, `screenshot`, `pause_toggle`,
  `toggle_fullscreen`). Nothing is written there unless a rule sets a hotkey.
  The keyboard (`input_<base>`) and mouse (`input_<base>_mbtn`) binds are not
  managed. Meta binds have no user number (`input_config_get_prefix`: prefix
  `input`), so they are rendered from player 1's resolution.
- In `retroarch.cfg`, also `input_playerN_joypad_index` for the players
  `apply` assigns (see "Which pad is which player"). Nothing else there.
- We never touch autoconfig files EmuDeck ships. We may *add* a generated
  autoconfig for native-mode devices with no profile.

## Which pad is which player (implemented)

`input_playerN_joypad_index` is the 0-based joypad port user N reads (default
N−1, `config_set_defaults`; two users on one port is allowed). With
`input_joypad_driver = "sdl2"` (EmuDeck's setting), port i is SDL device index i:
`sdl2_joypad_init` opens SDL indices 0..n−1 into ports 0..n−1, and a hot-plugged
pad takes the index SDL gives it.

On the owner's Deck (Flatpak 1.22.2, Game Mode, docs/13 S1) RetroArch numbered
users by **js node**: after a reorder put the DualSense in Steam slot 0, user 1
was the Deck's virtual pad (`pad 1`, js0), and the pads kept their
`Microsoft X-Box 360 pad <N>` names. That's node order, so the adapter declares
`sdl_order = "nodes"` (`retropad.json` `joypad_ports`). It was observed despite
SDL3 underneath: the Flatpak (runtime `org.kde.Platform` 6.11) loads the runtime's
`libSDL2-2.0.so.0.3200.68`, which is sdl2-compat over `libSDL3` 3.2.30. SDL3 sorts
Steam virtual pads by slot and renames them, and the Flatpak has `host`
filesystem access and can read `virtualgamepadinfo.txt`. So why SDL3's slot sort didn't apply is unknown **[VERIFY]** (maybe `SteamVirtualGamepadInfo` isn't in the Flatpak's environment, or the sdl2-compat path differs). A fresh session
with the virtual pads in slot order (2026-10-22, docked) gave the right player 1
under either order, so it doesn't settle this.

`apply` without `--player` takes the players in Steam's order (player K = K-th
live slot), finds each one's virtual pad, ranks it among the joysticks SDL sees
(physical pads behind Steam are hidden from SDL), and writes
`input_playerK_joypad_index = "<rank>"` for every assigned player, so the ports
stay a permutation. `tests/golden/retroarch/game-mode-reorder.diff` is the
S1 case: player 1 → port 1 (the DualSense), player 2 → port 0 (the Deck), with
the DualSense's remap on player 1.

`apply` warns when these ports won't hold: `input_joypad_driver` isn't `sdl2`;
`input_assign_ports_on_button_press` is on; a player has a reserved device
(`input_playerN_device_reservation_type` ≠ 0, applied on every connect); or a
core, folder or game override in `config/<core>/*.cfg` sets a joypad index
(overrides save it when it differs, `config_save_overrides`, and win over
`retroarch.cfg`). EmuDeck sets `config_save_on_exit = "false"`, so RetroArch
doesn't write the ports back at quit.

## Per-game

Write the **core-level** `.rmp` at each launch (global-swap). If a game-level or
directory-level `.rmp` exists that we didn't create, RetroArch loads it **instead
of** ours (first match wins, no layering). Report it as a per-game override in
the trace and offer import.

Native per-game is possible: we could write the game-level file ourselves
for game-scope rules. Because it fully replaces the core file, it must contain
the complete merged result, not just the game-specific keys.

## Game id

`path_basename_nocompression(RARCH_PATH_BASENAME)`: the content file name with
its **last** extension removed (`runloop_path_set_basename`), e.g.
`Super Metroid (USA).sfc` → `Super Metroid (USA)`.

- Archive opened directly (`game.zip` from the CLI): `game`.
- Path into an archive (`game.zip#folder/rom.sfc`, as playlists store it):
  the **member's** basename, `rom`. The exception is cores that take archives
  themselves (`block_extract`, e.g. dolphin-emu), which use the archive name
  (`runloop_path_set_basename_to_archive`, master).
- The content-dir id is the name of the immediate parent directory
  (`fill_pathname_parent_dir_name`).

## Hotkeys

Keys and value syntax: see "Bind value syntax" above. The full list of bases is
`input_config_bind_map` in `configuration.c` (meta binds L388–466, copied into
`hotkeys.json` `meta_bases`). EmuDeck's combos are in
[data/defaults/README.md](../../data/defaults/README.md#hotkey-scheme), read
from its shipped `retroarch.cfg`.

**One enable button for all.** While `input_enable_hotkey` is bound, every
other hotkey needs it held (`input_hotkey_blocked`, `input_keys_pressed` in
`input/input_driver.c`). A RetroArch hotkey is therefore always
*enable + action*, and the enable input is shared by every hotkey, including
the ones map-helper doesn't manage (EmuDeck's Select+X FPS, Select+Y next disc,
Select+L3 reset, Select+D-Up run-ahead). EmuDeck's enable is Select
(`input_enable_hotkey_btn = "4"`).

**Rendering** (`RetroArchAdapter._render_hotkeys`), only when player 1's
resolution has `hotkey.*` bindings that rules set:

1. Read `input_joypad_driver` from `retroarch.cfg`. Indices are driver-specific,
   and only `sdl2` has a table. Anything else (`udev`, `sdl3`, unset) writes no
   hotkeys and warns; wrong indices would bind the wrong buttons.
2. Each rule must be a two-input chord. The enable input is the one most
   chords share (ties go to the live one); chord order doesn't matter, so
   `start+select` and `select+start` are the same. A chord that doesn't
   include it, a single input, a 3-input chord, or an input with no `sdl2`
   index is skipped with a warning. `{"input": "none"}` unbinds the hotkey.
3. Each bound base gets both keys: the one that applies (`_btn` for buttons,
   `_axis` for triggers and stick directions) and `"nul"` in the other, so an
   old bind on the other kind doesn't keep firing.
4. A hotkey we don't render that is still bound to an input we just used
   (action or enable) would fire with it. Managed ones are set to `"nul"`
   with a warning (EmuDeck's Select+R2 fast-forward toggle when a rule puts
   `hotkey.fast_forward_hold` on R2). Unmanaged ones are only warned about.
5. Moving the enable button warns, since every RetroArch hotkey moves with it.

`input_menu_toggle_gamepad_combo = "2"` (L3+R3) and
`input_quit_gamepad_combo = "4"` (Start+Select) in EmuDeck's config are
separate combo settings, not binds (`enum input_combo_type`,
`input/input_defines.h` L221–235; the quit combo is checked in
`input_driver.c` L2221 regardless of the exit hotkey). map-helper leaves both
unmanaged. When a rule moves or unbinds `hotkey.exit` and the live quit combo
isn't `0` (none), the render warns that the combo (Start+Select under EmuDeck)
still quits. A rule that keeps exit on Select+Start gets no warning.

### SDL2 indices

With `sdl2`, a pad that SDL knows as a game controller (the Steam virtual
pad is in SDL's mapping database) is opened with `SDL_GameControllerOpen`, and
`sdl2_pad_get_button` / `sdl2_pad_get_axis` pass the bind index straight to
`SDL_GameControllerGetButton` / `SDL_GameControllerGetAxis`
(`input/drivers_joypad/sdl2_joypad.c`). So the numbers are SDL's enums:

| Canonical | `_btn` | | Canonical | `_axis` |
|-----------|--------|-|-----------|---------|
| `face_south` | 0 | | `ls_right` / `ls_left` | `+0` / `-0` |
| `face_east` | 1 | | `ls_down` / `ls_up` | `+1` / `-1` |
| `face_west` | 2 | | `rs_right` / `rs_left` | `+2` / `-2` |
| `face_north` | 3 | | `rs_down` / `rs_up` | `+3` / `-3` |
| `select` | 4 | | `l2` | `+4` |
| `guide` | 5 **[VERIFY]** | | `r2` | `+5` |
| `start` | 6 | | | |
| `l3` / `r3` | 7 / 8 | | | |
| `l1` / `r1` | 9 / 10 | | | |
| `dpad_up/down/left/right` | 11–14 | | | |

These match every value in EmuDeck's `retroarch.cfg` and the sdl2 Steam
Virtual Gamepad autoconfig. SDL's `MISC1`, `PADDLE1`–`4` and `TOUCHPAD`
(15–20) are left out: the Steam virtual pad is an Xbox 360 pad without them.
**[VERIFY]** on a Deck: that RetroArch opens the Steam virtual pad through the
GameController API (otherwise raw joystick indices apply), and whether Guide
reaches RetroArch at all (Steam keeps it).

`hotkey.fast_forward` is `toggle_fast_forward`, which EmuDeck binds to
Select+R2 (the canonical fast-forward is always the toggle);
`hotkey.fast_forward_hold` is `hold_fast_forward`.

## Known pitfalls

- **`remap_save_on_exit` is on by default.** RetroArch rewrites the loaded
  `.rmp` at content close, normalised and with any Quick Menu edits. Drift
  detection must compare parsed key/values, not bytes. Edits made in RetroArch
  land in our managed file and are lost at the next launch unless imported.
  The writer and restore still treat the save as ours (load precedence above);
  `doctor` warns.
- **`config_save_on_exit` is on by default.** `retroarch.cfg` is rewritten at
  quit. Never use `--appendconfig` for hotkeys; its values leak into the main
  config.
- Remap dir name is `library_name`, which differs between builds of one core
  (`Beetle PSX` vs `Beetle PSX HW`, FBNeo subset builds, SwanStation debug
  builds) and has changed across core versions. Read it from the installed
  core's `.info` file or from RetroArch's log (`[Remap] ... found at`) rather
  than hard-coding it **[VERIFY]** `.info` `corename` equals `library_name`
  for each core.
- Device type ids (`input_libretro_device_pN`) are per core. Some cores pick the
  pad type with core options instead (PicoDrive pad, N64 paks), which live in
  `retroarch-core-options.cfg` / per-game `.opt` files, not in remaps.
- `input_playerN` is the RetroArch user, not the core port. With
  `input_assign_ports_on_button_press` on (master), port assignment is dynamic
  and `input_remap_port_pN` is not saved for those users.
- Analog-to-digital (`analog_dpad_mode` ≠ 0) zeroes the core's analog reads.
  N64/PSX analog games break if we leave it on.
- `input_remap_binds_enable = false` disables remaps globally. Check it at apply
  time.
- Bind values in `retroarch.cfg` are driver-specific (`sdl2` vs `udev` indices
  differ). The hotkey writer reads `input_joypad_driver` and writes nothing for
  a driver it has no table for.
- `config_save_on_exit` is false under EmuDeck, so hotkey edits made in
  RetroArch's menu only stick if the user saves the config. Ours are rewritten
  at each launch either way.

## `doctor` checks

`map-helper doctor` reads the RetroArch config root (default the Flatpak's) and
reports what stops our core-level `.rmp` from taking effect. It never writes.
Paths in its output are relative to the config root. EmuDeck's
`input_remapping_directory` names the Flatpak root explicitly
(`~/.var/app/org.libretro.RetroArch/config/retroarch/config/remaps`), so
`doctor` reads that prefix as the root it was given.

| Finding | Severity | Why |
|---------|----------|-----|
| `auto_remaps_enable = false` | error | `config_load_remap` never runs, so no `.rmp` loads |
| `input_remap_binds_enable = false` | error | remaps are loaded but not applied |
| `input_remap_sort_by_controller_enable = true` | error | remaps are looked up under `<core>/<device name>/`, never our core-level file |
| `input_autodetect_enable = false` | error | `input_config_get_autoconfig_dir` returns NULL, so no profile loads; pads get only `retroarch.cfg` binds, which EmuDeck leaves `nul` |
| non-`nul` `input_playerN_<button>_btn`/`_axis` in `retroarch.cfg` | warning | a user bind beats the profile's (`auto_binds` is used only for `NO_BTN`/`AXIS_NONE`), so the RetroPad source a press produces isn't the Steam Virtual Gamepad profile's, which our remaps assume |
| any of the above in an override (`config/<core>/*.cfg`) | same | overrides load over `retroarch.cfg` when `auto_overrides_enable` is on (EmuDeck: on). The captured overrides are content-dir ones named after EmuDeck's ROM folders (`config/Beetle Cygne/wonderswan.cfg`) |
| another `.rmp` in `<remap dir>/<core>/` | warning | a game or content-dir remap wins over ours when it matches (load precedence above) |
| `<core>.rmp` next to EmuDeck's `<core>.rmp.disabled` | warning | EmuDeck's layout switch to ABXY moves `.rmp.disabled` over ours; switching back renames ours to `.rmp.disabled` |
| `<core>.rmp` alone for one of EmuDeck's 10 toggled cores | warning | the switch to BAYX renames it to `.rmp.disabled` (with `controllerLayout=abxy` it's likely EmuDeck's own file) |
| cores with only `.rmp.disabled` | info | EmuDeck's ABXY remaps are parked (normal under `baxy`) |
| `remap_save_on_exit` not `false`, and map-helper's manifest lists a `.rmp` | warning | RetroArch saves its remaps over ours when a game closes; mh-run rewrites them at the next launch, so Quick Menu remap edits don't last |

"AutoMap" is EmuDeck's, and it doesn't touch RetroArch (only Dolphin, Cemu
and the Switch emulators, [07](../07-launch-integration.md)). RetroArch's own
counterpart is autoconfig, covered by the two `retroarch-autoconfig` rows.
`doctor` checks EmuDeck AutoMap for Dolphin separately.

Sources: `input/input_driver.c` @ `eb7335f`: `input_config_get_autoconfig_dir`
(L14337), bind fallback to `auto_binds` (L1671–1677, L2805–2810),
`input_key_pressed` (L9640); `tasks/task_autodetect.c` reads
`input_autodetect_enable` on connect (L1823–1824); `config.def.h`
`DEFAULT_INPUT_AUTODETECT_ENABLE true` (L1946). EmuDeck
`functions/EmuScripts/emuDeckRetroArch.sh` @ `dddb302`:
`RetroArch_setABXYstyle` (L363–374), `RetroArch_setBAYXstyle` (L376–386);
`functions/helperFunctions.sh` `controllerLayout_ABXY`/`_BAYX` (L1307–1329).

## Sources

RetroArch, master `eb7335f939c39be703662c2a0e07c106f99b64ac` (version 1.22.2), cross-checked at tag `v1.22.2`:

- `configuration.c`: `config_load_remap` (L8107–8227), `input_remapping_load_file` (L10313), `input_remapping_save_file` (L10496–10699: new file L10528, identity left out and unmapped as `-1` L10589–10600 and L10628–10639, device line L10657, turbo L10676–10682; same at `v1.22.2`), `input_config_bind_map` (L347), `save_keybind_joykey`/`save_keybind_hat`/`save_keybind_axis` (L8259–8355), `input_config_get_prefix` (L8418), `config_save_file` (L9095), `JOYPAD_DEFAULT_DRIVER` (L736–790), setting keys (L1947, L2114, L2120, L2250, L2263, L2265). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/configuration.c>
- `input/input_driver.c`: remap application in `input_driver_poll` (L15916–16060), original-bit suppression in `input_state_device` (L4435–4475) and `input_state_internal` (L5153–5170), `input_remapping_update_port_map` (L16849), `input_remapping_deinit` (L16905–16919, saves only when passed `remap_save_on_exit`), `input_remapping_defaults_into`, `input_key_pressed` (L9640). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/input/input_driver.c>
- `input/input_defines.h`: `RARCH_FIRST_CUSTOM_BIND` = 16, `RARCH_UNMAPPED` = 1024, analog bind enum, `analog_dpad_mode` enum (L31–103, L209–218). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/input/input_defines.h>
- `libretro-common/include/libretro.h`: `RETRO_DEVICE_ID_JOYPAD_*` (L309–371), `RETRO_DEVICE_SUBCLASS` (L138). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/libretro-common/include/libretro.h>
- `config.def.h`: `DEFAULT_CONFIG_SAVE_ON_EXIT` (L730), `DEFAULT_REMAP_SAVE_ON_EXIT` (L736), `DEFAULT_AUTO_REMAPS_ENABLE` (L1094). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/config.def.h>
- `runloop.c`: `runloop_event_deinit_core` remap save (L5666–5679), `runloop_event_init_core` remap load (L6684–6718), `runloop_path_set_basename` (L11135), `runloop_path_set_basename_to_archive` (L6497). `retroarch.c`: `retroarch_main_quit_finish` (L10528–10585, remap save L10550), `--appendconfig` help (L7802–7813). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/runloop.c>
- `input/drivers_joypad/sdl2_joypad.c`: `sdl2_pad_get_button` (L59–65), `sdl2_pad_get_axis` (L81–97), `SDL_IsGameController` / `SDL_GameControllerOpen` in `sdl2_pad_connect` (L121–125), button/axis counts for game controllers (L181–194), ident `"sdl2"` (L669). <https://github.com/libretro/RetroArch/blob/eb7335f939c39be703662c2a0e07c106f99b64ac/input/drivers_joypad/sdl2_joypad.c>
- `input/input_driver.c`: hotkey gating by the enable bind, `input_hotkey_blocked` (L12083) and `input_keys_pressed` (L13561).
- SDL 2.30.0 (`release-2.30.0`, `859844e`) `include/SDL_gamecontroller.h`: `SDL_GameControllerAxis` (L620–630), `SDL_GameControllerButton` (L731–755). <https://github.com/libsdl-org/SDL/blob/859844eae358447be8d66e6da59b6fb3df0ed778/include/SDL_gamecontroller.h>
- `tasks/task_autodetect.c`: `input_autoconfigure_tuple_affinity` (L205), `input_autoconfigure_get_config_file_affinity` (L261), directory scan (L929–1120, L1895–1920). v1.22.2 scan order: <https://github.com/libretro/RetroArch/blob/v1.22.2/tasks/task_autodetect.c>
- `frontend/drivers/platform_unix.c`: base path `$XDG_CONFIG_HOME/retroarch` (L3149–3170), remap and autoconfig defaults (L3203–3215, L3315–3319), `unix_find_packaged_dir` (L2617). `menu/cbs/menu_cbs_ok.c`: `generic_action_ok_remap_file_operation` (L4104). `settings/settings_def_input_haptics.h`: `input_remap_binds_enable`, `input_remap_sort_by_controller_enable` (L77–86).
- libretro docs, overrides and remaps: <https://github.com/libretro/docs/blob/a7043e4a8b984c3a0a1dc5d04b8fd0a0bc66b50f/docs/guides/overrides.md> (<https://docs.libretro.com/guides/overrides/>)
- retroarch-joypad-autoconfig master `7f94f847057c0829d4e18df27e50930728507f83`: `sdl2/Steam Virtual Gamepad.cfg`, `udev/Steam Input x-box.cfg`. <https://github.com/libretro/retroarch-joypad-autoconfig/tree/7f94f847057c0829d4e18df27e50930728507f83>
- Joypad ports: `input/drivers_joypad/sdl2_joypad.c` `sdl2_pad_connect` (L112–131), `sdl2_joypad_init` (L334–339), hot-plug (L486–497); `configuration.c` default (L6078), load and sanitize (L7102–7114), overrides (L10124–10133); `input/input_driver.c` `input_config_sanitize_joypad_indices` (L10350–10390). SDL2 order: `src/joystick/linux/SDL_sysjoystick.c` `sort_entries` (L854–885), `LINUX_ScanSteamVirtualGamepads` (L900–962) at <https://github.com/libsdl-org/SDL/blob/0aef2c3612294b8ed4fb9626b8426f4c9c835c6d/src/joystick/linux/SDL_sysjoystick.c> (release-2.30.x); `SDL_ShouldIgnoreJoystick` (`src/joystick/SDL_joystick.c` L2989–3011).
- Core sources: see `sources` in each `data/adapters/retroarch/cores/*.json` (pinned commits).

## EmuDeck specifics (from fixtures)

Cross-checked against EmuDeck's shipped `retroarch.cfg`
(`tests/fixtures/retroarch/emudeck-default/`, `dragoonDorise/EmuDeck@dddb302`) and
[data/defaults/README.md](../../data/defaults/README.md). This resolves several unknowns above:

- `input_joypad_driver = "sdl2"`, so hotkey indices use SDL GameController order (see [SDL2 indices](#sdl2-indices)) and autoconfig resolves under `autoconfig/sdl2/`.
- `config_save_on_exit = "false"`: `retroarch.cfg` is **not** rewritten at quit under EmuDeck.
- `remap_save_on_exit = "true"`: whichever `.rmp` was loaded **is** rewritten when content closes, so drift detection must compare parsed values.
- EmuDeck ships core-level remaps as `<core>.rmp.disabled` for 10 cores. Its `abxy` layout setting renames them to `.rmp` (A↔B / X↔Y swaps). Our core-level `.rmp` would replace those, so the pristine snapshot and uninstall must restore the `.rmp` / `.rmp.disabled` state exactly.
- Hotkeys: Select (`input_enable_hotkey_btn = "4"`) + button, as listed in the defaults README.
