# Adapter: xemu

Facts below were read from xemu at tag `v0.8.136` (`fc24584ce8`), the version
on the owner's Deck, and from SDL `release-3.4.14`, the SDL the Flatpak runs,
unless another version is given. Links are in [Sources](#sources). Items marked
**confirmed on a Deck** were checked read-only over ssh on 2026-10-31 (xemu
Flatpak 0.8.136, runtime `org.freedesktop.Platform` 26.08, Game Mode, one pad
connected).

## Summary

| Field | Value |
|-------|-------|
| Adapter id | `xemu` |
| Systems | `xbox` (layout [`data/layouts/xbox.json`](../../data/layouts/xbox.json)) |
| EmuDeck install type | Flatpak `app.xemu.xemu`, `--user` (EmuDeck `emuDeckXemu.sh` L4–L6) |
| Versions covered | 0.8.136 (SDL3 input, `gamepad_mappings` remaps). Older SDL2 builds are out of scope |
| Priority | P2 |
| Strategy | global-swap of `[input.bindings] port1..port4` (player order), plus per-slot `[input] gamepad_mappings` entries for remaps |
| Per-game input | none in xemu |

The short version: xemu keys everything on the **SDL joystick GUID**. For a
Steam virtual pad that GUID contains a CRC of the evdev name
`Microsoft X-Box 360 pad <N>`, so **each Steam slot has its own GUID**. map-helper
can work out every slot's GUID from `/proc/bus/input/devices` and write
`portK` = the GUID of player K's slot. A remap for that player goes in the
`gamepad_mappings` entry with the same GUID.

## Paths

| What | Flatpak (EmuDeck) | Native / AppImage |
|------|-------------------|-------------------|
| Config root | `~/.var/app/app.xemu.xemu/data/xemu/xemu/` | `${XDG_DATA_HOME:-~/.local/share}/xemu/xemu/` |
| Config file | `xemu.toml` (input, display, system, everything) | same |
| Portable mode | `xemu.toml` next to the binary wins (`SDL_GetBasePath()`) | same |
| Profiles | none | |
| Per-game | none | |

The root is `SDL_GetPrefPath("xemu", "xemu")` unless portable mode is on
(`ui/xemu-settings.cc` L51–L105). Inside the Flatpak `XDG_DATA_HOME` is
`~/.var/app/app.xemu.xemu/data`, which gives EmuDeck's `Xemu_configFile`
(`emuDeckXemu.sh` L6). **Confirmed on a Deck**: the file is there.

The same file can hold `[general] user_token` (xemu's compatibility-report
token, `config_spec.yml` L14). Read only the `[input]` tables, and never print
the file whole.

## Format

TOML, parsed with toml++ and generated from a schema (`config_spec.yml`).
Load: `config_tree.update_from_table(toml::parse(buf))`, then
`store_to_struct(&g_config)` (`ui/xemu-settings.cc` L158–L207). A key that is
missing gets the schema default. A parse error stops xemu with a dialog
("Failed to load xemu config file", `ui/xemu.c` L1325–L1333), so **a bad write
means xemu won't start**. The writer must check its output with `tomllib`
before replacing the file.

**Save on exit, whole file.** `atexit(xemu_settings_save)` (`ui/xemu.c` L1334)
rewrites the file from memory as a **delta against the defaults**
(`generate_delta_toml()`, `ui/xemu-settings.cc` L209–L238). Comments and key
order are lost and keys equal to their default are dropped. There is no other
call to `xemu_settings_save`, so settings changed in the UI reach the file only
when xemu exits. Drift detection must compare parsed values with defaults
filled in, not bytes.

Real file on the owner's Deck after xemu ran (GUIDs masked, paths kept):

```toml
[general]
show_welcome = false
skip_boot_anim = true

[input]
gamepad_mappings = [
    { gamepad_id = '0300…(32 hex)'},
    { gamepad_id = '0300…(32 hex)'},
    ...7 entries in all...
    ]

[input.bindings]
port1_driver = 'usb-xbox-gamepad'
port1 = '0300…(32 hex)'
port2_driver = 'usb-xbox-gamepad'
port2 = '0300…(32 hex)'
port3_driver = 'usb-xbox-gamepad'
port3 = '0300…(32 hex)'
port4_driver = 'usb-xbox-gamepad'
port4 = '0300…(32 hex)'
```

`gamepad_mappings` is written as an **inline array of inline tables** spread
over several lines. A line-preserving editor can't patch a field inside it, so
map-helper should rewrite the whole `gamepad_mappings = [ ... ]` value (one
managed key whose value spans lines) and keep every entry it doesn't own as it
is.

## Input schema (`config_spec.yml` L23–L225)

### `[input.bindings]`

| Key | Type | Meaning |
|-----|------|---------|
| `port1` … `port4` | string | What is plugged into Xbox port K: the `SDL_GUIDToString()` of an SDL joystick GUID (32 lowercase hex), the literal `keyboard`, or empty / missing (nothing remembered). |
| `port1_driver` … `port4_driver` | string | Emulated pad: `usb-xbox-gamepad` (Duke, "Xbox Controller") or `usb-xbox-gamepad-s` ("Xbox Controller S"). Missing, empty or anything else means Duke (`get_bound_driver`, `ui/xemu-input.c` L242–L259; names in `ui/xemu-input.h` L35–L39). |

GUID strings come from `SDL_GUIDToString(SDL_GetJoystickGUID(joystick))`
(`ui/xemu-input.c` L370, L378, L692). xemu writes `portK` and `portK_driver`
only when it binds with `save = 1` (`xemu_input_bind`, L687–L700).

### `[input.peripherals.portK]`

`peripheral_type_0/1` (0 none, 1 XMU memory unit) and `peripheral_param_0/1`
(the XMU image path) (`ui/xemu-input.h` L76; `ui/xemu-input.c` L883–L928).
map-helper never touches these.

### `[input]` options

| Key | Default | Meaning |
|-----|---------|---------|
| `auto_bind` | `true` | A pad that matches no port goes to the first free port, and that binding is **saved** (`ui/xemu-input.c` L415–L424). UI: Settings → Input → "Auto-bind controllers". |
| `allow_vibration` | `true` | Deprecated. `false` is copied into each mapping's `enable_rumble` (`ui/xemu-settings.cc` L279–L305). |
| `background_input_capture` | `false` | SDL background joystick events. |
| `gamecontrollerdb_path` | empty | extra SDL mapping DB |
| `keyboard_controller_scancode_map.*` | see spec | SDL scancodes for the keyboard "pad" |

### `[input] gamepad_mappings` (array of tables)

One entry per SDL GUID xemu has ever seen. Entries are found by an exact
`strcmp` on `gamepad_id`, first match (`xemu_settings_load_gamepad_mapping`,
`ui/xemu-settings.cc` L268–L308). When a pad with a new GUID connects, xemu
appends `{ gamepad_id = '<guid>' }` with every other field at its default.

| Key | Type / default | Meaning |
|-----|----------------|---------|
| `gamepad_id` | string | The same 32-hex GUID string as `portK`. **Confirmed on a Deck**: all 7 entries are 32 characters long, not 36. |
| `enable_rumble` | bool, `true` | rumble for this pad |
| `controller_mapping.<xbox input>` | int | for each Xbox button or axis, the **SDL3 `SDL_GamepadButton` / `SDL_GamepadAxis` index it reads** (tables below). `-1` means unbound. Out of range resets to `-1` with a warning (`ui/xemu-input.c` L159–L208). |
| `controller_mapping.invert_axis_left_x/left_y/right_x/right_y` | bool, `false` | flip that stick axis |

How the remap is applied (`xemu_input_update_sdl_controller_state`,
`ui/xemu-input.c` L561–L627): each Xbox button reads
`SDL_GetGamepadButton(pad, controller_mapping.<button>)`, and each Xbox axis
reads `SDL_GetGamepadAxis(pad, controller_mapping.<axis>)`. So:

- A mapping goes **from Xbox input to pad input**. Several Xbox inputs may read
  the same pad button. One Xbox input **can't** read two pad buttons, so
  map-helper's "several pad buttons for one console input" can't be expressed:
  write the first one and report the rest in the trace.
- Buttons only read buttons and axes only read axes. A trigger can't be driven
  by a button, and the Xbox face buttons (analog on real hardware) are full on
  or off.
- Y axes: xemu flips SDL's Y (down is positive) to the Xbox's up-is-positive
  **unless** `invert_axis_*_y` is true (L612–L622). `invert_axis_left_y = true`
  therefore gives an inverted stick. X axes flip only when their invert key is true.

`controller_mapping` keys and defaults (`config_spec.yml` L149–L225), with the
bit each one feeds in xemu's Xbox pad state (`ui/xemu-input.h` L41–L57,
`ui/xemu-input.c` L572–L600):

| Key | Default | SDL3 default input | Xbox input fed |
|-----|---------|--------------------|----------------|
| `a` | 0 | `SDL_GAMEPAD_BUTTON_SOUTH` | A |
| `b` | 1 | `EAST` | B |
| `x` | 2 | `WEST` | X |
| `y` | 3 | `NORTH` | Y |
| `back` | 4 | `BACK` | Back |
| `guide` | 5 | `GUIDE` | Guide (xemu extension, opens xemu's menu; not an Xbox input) |
| `start` | 6 | `START` | Start |
| `lstick_btn` | 7 | `LEFT_STICK` | left thumb click |
| `rstick_btn` | 8 | `RIGHT_STICK` | right thumb click |
| `lshoulder` | 9 | `LEFT_SHOULDER` | **White** (bit `CONTROLLER_BUTTON_WHITE`, L582) |
| `rshoulder` | 10 | `RIGHT_SHOULDER` | **Black** (bit `CONTROLLER_BUTTON_BLACK`, L583) |
| `dpad_up` / `dpad_down` / `dpad_left` / `dpad_right` | 11 / 12 / 13 / 14 | `DPAD_UP` / `DOWN` / `LEFT` / `RIGHT` | D-pad |
| `axis_left_x` / `axis_left_y` | 0 / 1 | `SDL_GAMEPAD_AXIS_LEFTX` / `LEFTY` | left stick |
| `axis_right_x` / `axis_right_y` | 2 / 3 | `RIGHTX` / `RIGHTY` | right stick |
| `axis_trigger_left` / `axis_trigger_right` | 4 / 5 | `LEFT_TRIGGER` / `RIGHT_TRIGGER` | L / R trigger |

The UI labels the `lshoulder` and `rshoulder` rows "White" and "Black"
(`ui/xui/main-menu.cc` L588–L604, L676–L692).

## Device references and player order

### How xemu binds a pad to a port (`ui/xemu-input.c` L349–L431)

On `SDL_EVENT_GAMEPAD_ADDED` (startup and hotplug alike):

1. Open the pad, read its GUID, append it to `available_controllers`, and load
   or create its `gamepad_mappings` entry.
2. **Match by GUID only.** Scan `port1..port4` from the first, looking for a
   port whose string equals the GUID **and that nothing is bound to yet**. Bind
   there **without saving** (`xemu_input_get_controller_default_bind_port`,
   L313–L329, loop L397–L413).
3. Otherwise, if `auto_bind` is on, bind to the **first free port and save** the
   GUID and driver into that port (L415–L424).
4. Otherwise the pad stays unbound.

Several pads with one GUID: each takes the next unbound port that names that
GUID, in arrival order (the comment at L384–L394 is about wireless 360
receivers). On removal the port is unbound **without saving**, so it's kept
for a reconnect (L432–L455). The keyboard is bound at init, before any pad, if
some port is `keyboard` (L300–L308).

Arrival order at startup is SDL's enumeration order. Inside a Flatpak SDL3
turns udev off ("Container detected", `SDL_sysjoystick.c` L1031–L1045) and
scans `/dev/input` itself, **Steam virtual pads first, sorted by slot**
(`LINUX_ScanSteamVirtualGamepads`, L867–L948, called first from
`LINUX_FallbackJoystickDetect` L950–L970), then everything else. After that it
watches `/dev/input` with inotify, so hotplug works in-game.

What this means for map-helper:

- `portK` is the only thing that decides which pad is player K, and it's keyed
  on the **slot's** GUID, not the physical pad's. Write `portK` = GUID of the
  Steam slot that map-helper's player policy puts at player K
  (`devices.player_order`, docs/04 §5.2). xemu then binds by match, saves
  nothing, and leaves our values in place at exit.
- Clear the stale ports. If there are fewer than 4 players, a stale port that
  names a live slot's GUID still binds that pad when no earlier port takes it.
  Set every remaining port that holds a Steam-virtual-pad GUID (tail
  `de280000ff110000…`, below) to `''`. Leave `keyboard` and foreign GUIDs alone.
- A slot that no port names (one that connects mid-game) auto-binds to the
  first free port and xemu **saves** it. The next launch's apply overwrites
  that, so the drift check must not offer it as a user edit.
- **Confirmed on a Deck**: today `port1..port4` hold the GUIDs of slots 0, 1, 2,
  3 in that order, and the 7 `gamepad_mappings` are slots 0–6. That is the
  auto-bind result, so xemu currently follows raw Steam slot order and leaves a
  hole when a slot is missing. For example, with slots 0 and 2 live, slot 2
  sits on port 3 and player 2 has no pad. Writing the ports fixes both.

### The GUID of a Steam virtual pad

xemu calls `SDL_GetJoystickGUID`, which returns the GUID the Linux backend made
at detection (`SDL_joystick.c` L1393, L3554–L3569; `item->guid`,
`SDL_sysjoystick.c` L514, L1151–L1154). Nothing in between overwrites it:
Steam's `SteamVirtualGamepadInfo` changes the name, VID and PID SDL reports
(`SDL_GetJoystickVendorForID` L3493–L3510), **not** the GUID.

`IsJoystick` (`SDL_sysjoystick.c` L292–L363):

1. `product_string`: `JSIOCGNAME` fails on an evdev node, so SDL reads
   `EVIOCGID` (bus, vendor, product, version) and `EVIOCGNAME` (L316–L330). These
   are the `I: Bus= Vendor= Product= Version=` and `N: Name=` lines of
   `/proc/bus/input/devices`.
2. `FixupDeviceInfoForMapping` (L198–L218) changes the version only for an
   Elite 2 and Atari VCS pads, not `28de:11ff`.
3. `SDL_CreateJoystickGUID(bus, vendor, product, version, NULL, product_string, 0, 0)` (L355).

`SDL_CreateJoystickGUID` (`SDL_joystick.c` L2931–L2973), with no vendor name:

```
crc     = SDL_crc16(0, product_string, strlen(product_string))   # the raw evdev name
guid16  = [bus, crc, vendor, 0, product, 0, version]               # each u16 little-endian
guid[14] = driver_signature = 0, guid[15] = driver_data = 0
```

`SDL_crc16` is CRC-16/ARC: reflected polynomial `0xA001`, initial value 0, no
final XOR (`src/stdlib/SDL_crc16.c` L33–L52). `SDL_GUIDToString` writes the 16
bytes as 32 lowercase hex digits in byte order (`src/SDL_guid.c` L24–L42).

In Python (stdlib only):

```python
import struct

def crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        r, c = (crc ^ byte) & 0xFF, 0
        for _ in range(8):
            c = (0xA001 if (c ^ r) & 1 else 0) ^ (c >> 1)
            r >>= 1
        crc = c ^ (crc >> 8)
    return crc

def sdl_linux_guid(bus: int, vendor: int, product: int, version: int, name: str) -> str:
    return struct.pack("<7H", bus, crc16(name.encode("utf-8")), vendor, 0, product, 0, version).hex() + "0000"
```

Use the node's own `Bus`, `Version` and `Name` from `/proc/bus/input/devices`
instead of hard-coded values. On the Deck they are `Bus=0003`, `Version=0001`
(**confirmed**). Worked example, computed from the algorithm above (the name is
the same on every Deck, so this isn't data from the owner's machine):
`Microsoft X-Box 360 pad 0` → CRC `0xf679` →
`030079f6de280000ff11000001000000`. Slot 1 → `0300b836de28…`, slot 2 → `0300f837de28…`.
The name ends in the slot number, so **every slot has a different GUID**.

**Confirmed on a Deck** (2026-10-31): the predicted GUIDs of slots 0–3 equal
`port1`..`port4` exactly, slots 0–6 equal the 7 `gamepad_id`s, and the live
slot-0 node's computed GUID matches `port1`. No port or mapping has a zero CRC.

EmuDeck's template sets `port1 = '03000000de280000ff11000001000000'`
(`configs/app.xemu.xemu/.../xemu.toml` L7–L8). That is the CRC-zeroed form
SDL's mapping DB uses. It can never equal an SDL3 GUID (whose CRC isn't zero),
so on a fresh install the first pad lands on port 1 through `auto_bind`, and
xemu then saves the real GUID.

Not covered: pads Steam doesn't virtualise (Steam Input off for the shortcut,
or xemu started outside Steam). SDL may then open them through HIDAPI, whose
GUIDs use a different bus/signature. The adapter should leave the ports
untouched and report "no Steam slots" in the trace. **[VERIFY]** None of the 7
GUIDs xemu has saved on the owner's Deck is a physical pad's, which suggests
Steam's `SDL_GAMECONTROLLER_IGNORE_DEVICES` reaches the Flatpak and SDL drops
the physical pads, as docs/04 §5.2 assumes.

### Which SDL

The Flathub manifest builds xemu with autotools/meson and doesn't bundle SDL
(`app.xemu.xemu.yml` @ `b88359d0e4`, modules L25–L136). xemu's meson first tries
the system `sdl3` (`allow_fallback: false`) and builds its `subprojects/sdl3.wrap`
(SDL 3.4.10, static) only when that fails (`meson.build` L1676–L1702). The
runtime has SDL3, so the system one wins. **Confirmed on a Deck**: `/app/bin/xemu`
has `DT_NEEDED libSDL3.so.0`, and runtime 26.08 ships `libSDL3.so.0.4.14`
(version string `SDL-3.4.14`). The GUID code above is the same in 3.4.10 and
3.4.14 (`git diff release-3.4.10 release-3.4.14` touches only VID/PID tables in
`SDL_joystick.c`). Flathub moved xemu 0.8.136 from runtime 25.08 to 26.08 on
2026-10-05 (`d474492cdd` → `b88359d0e4`). The 25.08 runtime's SDL3 is not
checked, but the algorithm has been the same since SDL 2.26 **[VERIFY]** if
a Deck is still on the old build.

## Input naming table

The canonical pad input → SDL3 index to write in `controller_mapping`
(`include/SDL3/SDL_gamepad.h` L154–L182, L224–L231). Through Steam Input the
virtual pad is an Xbox 360 layout, so only the first 15 buttons and 6 axes
ever have data.

| Canonical | SDL3 index | Canonical | SDL3 index |
|-----------|-----------|-----------|-----------|
| `face_south` | 0 | `dpad_up` | 11 |
| `face_east` | 1 | `dpad_down` | 12 |
| `face_west` | 2 | `dpad_left` | 13 |
| `face_north` | 3 | `dpad_right` | 14 |
| `select` | 4 | `misc1` | 15 |
| `guide` | 5 | `paddle1` (right upper) / `paddle2` (left upper) | 16 / 17 |
| `start` | 6 | `paddle3` (right lower) / `paddle4` (left lower) | 18 / 19 |
| `l3` / `r3` | 7 / 8 | `touchpad_click` | 20 |
| `l1` / `r1` | 9 / 10 | `misc2`..`misc6` | 21..25 |
| `ls_x` / `ls_y` (axes) | 0 / 1 | `rs_x` / `rs_y` (axes) | 2 / 3 |
| `l2` / `r2` (axes) | 4 / 5 | unbound | -1 |

SDL3's face buttons are positional, so `face_south` is the bottom button on
every pad. Through Steam Input the face buttons follow Steam's virtual Xbox
layout, which is positional unless the user turned on Steam's Nintendo-layout
option **[VERIFY]** for the Switch Pro and 8BitDo.

## Console target table

From the targets in [`data/layouts/xbox.json`](../../data/layouts/xbox.json) to
xemu keys. `positional_default` there is exactly xemu's default mapping above,
so with no rules the adapter writes nothing into `controller_mapping`.

| Canonical target | `controller_mapping` key | Default canonical source |
|------------------|--------------------------|--------------------------|
| `xbox.standard.a` / `b` / `x` / `y` | `a` / `b` / `x` / `y` | `face_south` / `face_east` / `face_west` / `face_north` |
| `xbox.standard.white` | `lshoulder` | `l1` |
| `xbox.standard.black` | `rshoulder` | `r1` |
| `xbox.standard.start` / `back` | `start` / `back` | `start` / `select` |
| `xbox.standard.l3` / `r3` | `lstick_btn` / `rstick_btn` | `l3` / `r3` |
| `xbox.standard.up` / `down` / `left` / `right` | `dpad_up` / `dpad_down` / `dpad_left` / `dpad_right` | `dpad_*` |
| `xbox.standard.lstick_x` / `lstick_y` | `axis_left_x` / `axis_left_y` (+ `invert_axis_left_x/y`) | `ls_x` / `ls_y` |
| `xbox.standard.rstick_x` / `rstick_y` | `axis_right_x` / `axis_right_y` (+ `invert_axis_right_x/y`) | `rs_x` / `rs_y` |
| `xbox.standard.l_trigger` / `r_trigger` | `axis_trigger_left` / `axis_trigger_right` | `l2` / `r2` |
| (not in the layout) | `guide` | `guide`. Leave it: it only opens xemu's menu |

Rules that can't be rendered (report each one in the trace): a button source on
an axis or trigger target, an axis source on a button target, two sources for
one target, and a source the virtual pad doesn't have (paddles, touchpad,
misc). A half-axis source (`ls_up`) on a button target is impossible too.

## Controller type keys

| What | Key | Values |
|------|-----|--------|
| Duke vs Controller S | `[input.bindings] portK_driver` | `usb-xbox-gamepad` (default), `usb-xbox-gamepad-s` |

Write only with an `options.controller_type` rule. `xbox.json`'s `standard`
covers both, because they have the same inputs.

## Managed keys

- `[input.bindings] port1`..`port4`: player K's slot GUID for K ≤ min(players, 4).
  The remaining ports are set to `''` only when they hold a Steam-virtual-pad GUID.
- `[input.bindings] portK_driver`: only with an `options.controller_type` rule.
- `[input] gamepad_mappings`: the whole value is rewritten, but within it only the
  entries whose `gamepad_id` is the GUID of a player's slot, and only their
  `controller_mapping.*` (and `enable_rumble` with an options rule). Every other
  entry and field is kept as it was. Write only non-default fields, as xemu does,
  so xemu's exit save doesn't show up as drift.
- Never: `[input.peripherals.*]` (XMUs), `keyboard_controller_scancode_map`,
  `auto_bind`, anything outside `[input]`.

A remap belongs to a **slot**, not to a physical pad. That's fine because we
rewrite at every launch from the current slot → pad mapping. But if the pad in
a slot changes mid-session (hotplug reorder), the new pad inherits the old
pad's remap until the next launch.

## Game id

xemu has no per-game config, so the game id is needed only to *resolve*
game-scoped rules. The Xbox title ID sits in the XBE certificate of
`default.xbe` on the disc (xemu reads it from guest memory at the XBE base `0x10000`, `xemu-xbe.c` L84). Reading
it from an XISO means walking the XDVDFS directory. **[VERIFY]** Use filename
heuristics until then; game rules are P3 for this adapter.

## Hotkeys

None are configurable. Fixed bindings (`ui/xui/main.cc` L272–L307,
`ui/xui/menubar.cc` L44–L80):

| Input | Action |
|-------|--------|
| **Guide** on any pad | open the popup menu (Pause/Resume, Screenshot, Save Snapshot, Games, Eject/Load Disc, Settings, Restart, Exit: `ui/xui/popup-menu.cc` L424–L466) |
| **Back + Start** together on any pad | same popup menu ("controllers without a guide button") |
| F1 / F2 | main menu / popup menu |
| F5–F8, Shift+F5–F8 | load / save the snapshot bound to that key (`general.snapshots.shortcuts.f5..f8`, `ui/xui/actions.cc` L94–L116) |
| Ctrl+E / O / P / R / Q | eject disc / load disc / pause / reset / shut down |
| F11, F12, `` ` `` | fullscreen, screenshot, monitor |

The pad buttons are the **mapped** Xbox bits from every pad together
(`InputManager::Update`, `ui/xui/input-manager.cc` L14–L36), so a remap of
Back or Start also moves the Back + Start chord. While the menu has focus,
pad input doesn't reach the game (`xemu_input_set_test_mode`, L57–L59). In
Game Mode Steam normally takes the Guide/Steam button for itself, so on a Deck
Back + Start is the practical way into the menu **[VERIFY]**. The only shipped
canonical hotkey that maps is `hotkey.menu` (fixed). `save_state`,
`load_state` and `exit` have no pad binding in xemu.

## Options support

| Option | Key |
|--------|-----|
| Rumble on/off | `gamepad_mappings[].enable_rumble` (per slot) |
| Stick inversion | `controller_mapping.invert_axis_*` |
| Controller type | `portK_driver` |
| Dead zones, sensitivity, gyro | none |

## EmuDeck interaction

- **Install and init** (`emuDeckXemu.sh` L27–L44): `Xemu_init` calls
  `configEmuFP … "true"`, which rsyncs EmuDeck's `configs/app.xemu.xemu` over
  `~/.var/app/` with `--backup --suffix=.bak` (`configEmuFP.sh` L8–L15). That
  **replaces the whole `xemu.toml`** with the template (`port1` = the
  CRC-zeroed GUID, no `gamepad_mappings`). This happens on install and on
  "Reset configuration" (`Xemu_resetConfig`, L183–L185). `Xemu_update` uses
  `--ignore-existing` (L47–L54). The other functions edit only `sys.files.*`
  paths, `display.ui.fit` and `display.quality.surface_scale` (L57–L74,
  L150–L162, L195–L222). **Confirmed on a Deck**: `xemu.toml.bak` is there.
- **No AutoMap for xemu.** `emulatorInit` turns on AutoMap only for ryujinx,
  dolphin and cemu (`helperFunctions.sh` L1163–L1175), and there is no
  `Xemu_launch_fixes` (`emulatorLaunchFixes`, L1266–L1277). So nothing in EmuDeck
  rewrites xemu input at launch.
- **EmuDeck's launcher** `tools/launchers/xemu-emu.sh` (L1–L9): `launcherInit`,
  `emulatorInit "xemu"`, `flatpak run app.xemu.xemu "$@"`, then cloud sync. It is
  what EmuDeck's "xemu" Steam shortcut runs (`Xemu_addToSteam`, L231–L234).
  EmuDeck ships **no Steam ROM Manager parser for xbox**, so xbox games come
  from ES-DE.
- After an EmuDeck reset, re-snapshot "pristine" (docs/06 §3). Our next launch
  writes the ports again.

## ES-DE recognition

ES-DE's bundled Linux `es_systems.xml` (`a529a9d`, L2506–L2514):

```xml
<name>xbox</name>
<command label="xemu (Standalone)">%INJECT%=%BASENAME%.esprefix %EMULATOR_XEMU% -dvd_path %ROM%</command>
```

EmuDeck's custom `es_systems.xml` doesn't define `xbox`, and its custom
`es_find_rules.xml` has no `XEMU` entry (`dddb302`). So ES-DE resolves
`%EMULATOR_XEMU%` with its own rule (`es_find_rules.xml` L1585–L1600):
`xemu` / `app.xemu.xemu` on PATH, then static paths including
`~/.local/share/flatpak/exports/bin/app.xemu.xemu`. **ES-DE runs the Flatpak
export directly, not EmuDeck's `xemu-emu.sh`.** **Confirmed on a Deck**: no
`XEMU` rule and no custom `xbox` system in `~/ES-DE/custom_systems/`, no
`alternativeEmulator` for xbox, and the export
`~/.local/share/flatpak/exports/bin/app.xemu.xemu` exists. For comparison,
ES-DE's log shows RetroArch launched the same way
(`/home/deck/.local/share/flatpak/exports/bin/org.libretro.RetroArch -L …`).
There is no xbox launch in the current log, so **[VERIFY]** the expanded xemu
command line on the next xbox launch.

xemu reads `-dvd_path <path>` from argv itself (`system/vl.c` L3076–L3095).

For map-helper:

- `data/frontends/es-de.json` `systems` gets
  `"xbox": [["xemu (Standalone)", "%INJECT%=%BASENAME%.esprefix %EMULATOR_XEMU% -dvd_path %ROM%"]]`
  (its absence is why the hook says "es-de system 'xbox': no command map-helper
  knows"). The system name is the map-helper id (no alias).
- `esde.classify`: `"%EMULATOR_XEMU%" in command or "xemu-emu.sh" in command or
  "app.xemu.xemu" in command` → `("xemu", None)`.
- The ROM is `%ROM%`, and the system folder is `roms/xbox/`.

## Known pitfalls

- A TOML syntax error stops xemu from starting. Validate before the atomic
  replace, and fail open (leave the file alone).
- xemu rewrites the whole file at exit. Our formatting is lost, and only our
  values survive.
- `lshoulder`/`rshoulder` are White/Black, not "LB/RB" on the Xbox side.
- The ports name slots. If Steam's slot numbering changes between our apply
  and xemu's start (a pad connecting in between), the wrong pad can land on a
  port. The race is the same as for Dolphin.
- Physical pads outside Steam Input aren't handled (see above).
- `gamepad_mappings` grows by one entry per GUID ever seen. Don't prune
  entries we don't own.

## Fixtures

To capture (none yet): `tests/fixtures/xemu/0.8.136/xemu.toml` as EmuDeck
ships it, and one after a run with 2+ pads (GUIDs redacted to computed slot
GUIDs, `user_token` removed), plus a `/proc/bus/input/devices` with several
virtual pads for the GUID test. Use the worked example above as test data.

## Open questions

- **[VERIFY]** The expanded ES-DE command for xbox (export path vs `flatpak run`).
- **[VERIFY]** Steam's `SDL_GAMECONTROLLER_IGNORE_DEVICES` reaches the Flatpak,
  so physical pads never show up as extra GUIDs (strong evidence, not tested
  with 2+ pads).
- **[VERIFY]** With 2+ pads, writing `port1` = slot 1 and `port2` = slot 0 really
  swaps players (the code says yes).
- **[VERIFY]** Whether a remap written to `gamepad_mappings` is picked up at start
  (the code says yes: lookup on add, `ui/xemu-input.c` L382, L210–L240).
- **[VERIFY]** Whether Steam passes the Guide button through to xemu in Game Mode.
- **[VERIFY]** SDL3 on the 25.08 runtime build gives the same GUIDs.
- Xbox game id from XISO (P3).

## Sources

xemu, tag `v0.8.136` = `fc24584ce88f0915ad7f04775bb7712c2e3f49ee`
(`https://github.com/xemu-project/xemu/blob/fc24584ce88f0915ad7f04775bb7712c2e3f49ee/<path>`):

- Schema: `config_spec.yml` L1–L225 (`general` L1–L21, `input` L23–L225: bindings L24–L32, peripherals L33–L54, auto_bind L55–L58, allow_vibration L59–L62, keyboard map L63–L139, gamepad_mappings L140–L225)
- Input: `ui/xemu-input.h` L35–L57, L76; `ui/xemu-input.c` L95–L107 (port keys), L159–L208 (range check), L210–L240 (map reload), L242–L259 (drivers), L263–L329 (init, keyboard, default port), L349–L480 (add/remove/bind policy), L561–L627 (mapping applied), L654–L755 (bind, save)
- Settings: `ui/xemu-settings.cc` L42–L105 (paths), L158–L238 (load, save delta), L268–L337 (mapping lookup, reset); `ui/xemu.c` L1325–L1334 (load error, atexit save), L1364 (input init)
- UI: `ui/xui/main-menu.cc` L547–L573, L588–L692; `ui/xui/main.cc` L272–L307; `ui/xui/input-manager.cc` L14–L93; `ui/xui/menubar.cc` L44–L80; `ui/xui/popup-menu.cc` L316–L466; `ui/xui/actions.cc` L94–L116
- CLI: `system/vl.c` L3076–L3095
- SDL selection: `meson.build` L1676–L1702; `subprojects/sdl3.wrap`

SDL `release-3.4.14` = `147a8ee32dbf9ac02f3794964490687b6bbda1bc`
(`https://github.com/libsdl-org/SDL/blob/147a8ee32dbf9ac02f3794964490687b6bbda1bc/<path>`):

- `src/joystick/linux/SDL_sysjoystick.c` L198–L218 (fixups), L237–L252 (slot from name), L292–L363 (`IsJoystick`, GUID), L498–L520 (item), L867–L970 (virtual pads first, by slot), L1031–L1045 (no udev in a container), L1151–L1154
- `src/joystick/SDL_joystick.c` L1393, L2931–L2973 (`SDL_CreateJoystickGUID`), L3464 (`SDL_ShouldIgnoreJoystick`), L3476–L3510, L3554–L3569
- `src/stdlib/SDL_crc16.c` L33–L52; `src/SDL_guid.c` L24–L42
- `include/SDL3/SDL_gamepad.h` L154–L182 (buttons), L224–L231 (axes)
- Compared with `release-3.4.10` (`8e37db5e797b6167f3a00d697d816a684bd259c7`, xemu's wrap): no GUID change.

Flathub `app.xemu.xemu`:
`https://github.com/flathub/app.xemu.xemu/blob/b88359d0e41b146eb3e3a3047c619769b9e38dfe/app.xemu.xemu.yml`
(runtime 26.08, xemu 0.8.136 source L122–L136); previous build
`d474492cdd36557454cc08e32f1adc96720b8a27` (runtime 25.08).

EmuDeck `dragoonDorise/EmuDeck@dddb30229adbbd54d5ff7283cfd70e11c4322c26`
(`https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/<path>`):

- `functions/EmuScripts/emuDeckXemu.sh` L1–L234
- `configs/app.xemu.xemu/data/xemu/xemu/xemu.toml` L1–L23
- `tools/launchers/xemu-emu.sh` L1–L9
- `functions/configEmuFP.sh` L2–L18
- `functions/helperFunctions.sh` L1153–L1182 (`emulatorInit`), L1245–L1277 (launch fixes)
- `configs/emulationstation/custom_systems/es_systems.xml`, `es_find_rules.xml` (no xbox / XEMU)

ES-DE `a529a9d38c0af09b6fd7e38d10c8076cb0a21050`
(`https://gitlab.com/es-de/emulationstation-de/-/blob/a529a9d38c0af09b6fd7e38d10c8076cb0a21050/<path>`):
`resources/systems/linux/es_systems.xml` L2506–L2514; `resources/systems/linux/es_find_rules.xml` L1585–L1600.

Deck checks (read-only, 2026-10-31): `flatpak info --user app.xemu.xemu`; ELF `DT_NEEDED` of `/app/bin/xemu`;
runtime `files/lib/x86_64-linux-gnu/libSDL3.so.0*`; predicted slot GUIDs vs `xemu.toml` compared on the
Deck with only match results printed; `~/ES-DE/custom_systems/`, `gamelists/xbox/gamelist.xml`, `logs/es_log.txt`.
