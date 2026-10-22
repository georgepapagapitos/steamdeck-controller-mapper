# 04 — Controller Identification

To pick the right rules, we need to know, for every connected controller:

```
device id (stable)  →  model  →  family  →  brand  →  style  (+ capabilities)
```

and which **player slot** each one gets.

## 1. Where identity comes from

### 1.1 Always probe the *physical* device

With Steam Input on, emulators see **Steam virtual gamepads**: `uinput`
devices with VID `28de`, PID `11ff`, bus USB, named
`Microsoft X-Box 360 pad <N>` and created under `/devices/virtual/input/`
(SDL `usb_ids.h`, SDL and Proton's winebus both parse the `pad <N>` name;
dmesg in steam-for-linux #13029/#13665, see [Sources](#sources)). By default
every controller looks like an Xbox 360 pad to them. SDL 2.30+ and SDL3 can
undo part of that (§5.2). map-helper probes **under** Steam:

- `/sys/class/input/*/device/` and `/proc/bus/input/devices` give name, bus, vendor, product, version, `uniq` and `phys`. What `uniq` holds per driver is in §1.3.
- `/sys/class/hidraw/*` with `HID_ID`, `HID_NAME`, `HID_UNIQ` from the uevent.
- On BlueZ, `bluetoothctl info` or `/var/lib/bluetooth/...` for the paired MAC (fallback only).
- We filter out Steam's virtual devices (`28de:11ff`, or anything under `/devices/virtual/input/`), other `uinput` devices, and keyboards and mice. The DualShock 4 / DualSense also create sibling evdev nodes named `<name> Motion Sensors` and `<name> Touchpad`, and Joy-Cons / Switch Pro create `<name> (IMU)`. These carry the same `uniq` and must be grouped with the gamepad node, not treated as extra controllers.

**Can we still read the physical evdev nodes while Steam runs?** Probably yes,
with one exception. **[VERIFY]** (S3) on device with `evtest` /
`EVIOCGRAB` probing:

- Steam reads Sony, Nintendo and Valve pads through **hidraw**, not evdev. Valve's `steam-devices` udev rules grant `uaccess` on hidraw for DS4 (`05c4`, `09cc`, the `0ba0` adapter), DualSense (`0ce6`), DualSense Edge (`0df2`), Switch Pro (`2009`) and Joy-Cons (`2006/2007`), plus `uinput` for creating the virtual pads. hid-playstation's own comments mention "hidraw applications such as Steam" issuing feature reports.
- Steam hides the physical pads from games by **filtering**, not by grabbing them. It puts their VID/PIDs in `SDL_GAMECONTROLLER_IGNORE_DEVICES` in the game's environment (environment dump in Proton #4707; Proton #150), and Proton's winebus honours the same list. If Steam grabbed the evdev nodes, it wouldn't need that list. This is an inference, not a confirmed fact.
- **Exception: Steam Deck built-in controls and Steam Controllers.** `hid-steam` *removes* its own evdev gamepad (`Steam Deck` / `Steam Controller`) while the Steam client holds the hidraw node open ("this input device will be removed, to avoid double input"). In Game Mode the Deck's controls only exist as a Steam virtual pad plus the raw hidraw `28de:1205`.
- Xbox pads (xpad, or hid-microsoft over Bluetooth) have no hidraw rule in `steam-devices`, so Steam must read them through evdev. Whether it grabs them is the key S3 question.

### 1.2 Stable device id

In order of preference:

1. `uniq`, if non-empty, not all zeros and not the placeholder `XXXXXXXXXX` → `mac:<aa:bb:cc:dd:ee:ff>` (lower-cased) when it parses as a MAC, else `serial:<uniq>`
2. USB serial from sysfs `serial` → `usb-serial:<serial>`
3. Fallback: `path:<vid>:<pid>:<usb port path>`. This only stays stable if the
   pad is plugged into the same port, and the UI marks it as "port-bound".

**Sony and Nintendo pads already have one identity across USB and Bluetooth.**
The kernel sets `uniq` to the controller's Bluetooth MAC on both transports:

- `hid-playstation` reads the MAC over USB with feature report **`0x12`** (DS4, 16 bytes, MAC at `buf[1..6]` little-endian) or **`0x09`** (DualSense / Edge, 20 bytes, same layout), then writes it into `hdev->uniq` as `%pMR`. Over Bluetooth the DS4 takes it from HIDP's `uniq`. The DualSense reads `0x09` on both transports.
- `hid-nintendo` reads the MAC with the device-info subcommand and sets `uniq` to `%pMU` (upper case) on both the gamepad and the `(IMU)` node. **Normalise to lower case.**

So a DS4 does **not** need manual USB↔BT linking, as long as the kernel driver
is bound (it is on SteamOS). The registry still keeps the "link identities"
feature for pads whose USB `uniq` is empty: Xbox over xpad, 8BitDo, and generic
pads.

### 1.3 What `uniq` / `phys` hold, per path

| Path | `uniq` | `phys` | Source |
|------|--------|--------|--------|
| Classic Bluetooth (HIDP) | controller BT MAC | host adapter BT MAC | `net/bluetooth/hidp/core.c` |
| Bluetooth LE (BlueZ HOGP via uhid) | controller BT MAC | host adapter BT MAC | BlueZ `src/shared/uhid.c` |
| DS4 / DualSense / Edge, USB or BT (hid-playstation) | controller BT MAC, from feature report 0x12 / 0x09 | USB path / adapter MAC | `hid-playstation.c` |
| Sony USB wireless adapter `054c:0ba0` | whatever report 0x12 returns through the dongle (dongle's or pad's MAC?) **[VERIFY]** | USB path | `hid-playstation.c` |
| Switch Pro / Joy-Cons (hid-nintendo), USB or BT | controller MAC, upper case | from hdev | `hid-nintendo.c` |
| Xbox 360 / One / Series over USB (xpad) | empty (xpad doesn't set it) | `usb-<bus>-<port>/input0` | `xpad.c` (only `name`/`phys` set) |
| Steam Deck / Steam Controller (hid-steam) | unit serial number (`XXXXXXXXXX` if unreadable) | from hdev | `hid-steam.c`; node absent while Steam runs |
| Steam virtual pad (uinput) | **[VERIFY]** (expected empty) | **[VERIFY]** (expected empty) | S1 |

For xpad pads, the USB `serial` attribute (sysfs, parent USB device) is the
only per-unit id. Whether Xbox One/Series pads and 8BitDo dongles report one
is **[VERIFY]** (S8).

## 2. Controller DB (`data/controllers.json`)

Shipped data, community-extendable. Excerpt:

```jsonc
{
  "brands": {
    "sony":     { "name": "Sony" },
    "microsoft":{ "name": "Microsoft" },
    "nintendo": { "name": "Nintendo" },
    "8bitdo":   { "name": "8BitDo" },
    "valve":    { "name": "Valve" }
  },
  "families": {
    "sony.dualshock4": { "brand": "sony", "style": "playstation", "name": "DualShock 4" },
    "sony.dualsense":  { "brand": "sony", "style": "playstation", "name": "DualSense" },
    "ms.xbox-one":     { "brand": "microsoft", "style": "xbox", "name": "Xbox One / Series" },
    "nintendo.switch-pro": { "brand": "nintendo", "style": "nintendo", "name": "Switch Pro" },
    "8bitdo.pro2":     { "brand": "8bitdo", "style": "nintendo", "name": "8BitDo Pro 2" },
    "8bitdo.sn30pro":  { "brand": "8bitdo", "style": "nintendo", "name": "8BitDo SN30 Pro" },
    "8bitdo.m30":      { "brand": "8bitdo", "style": "sega6",    "name": "8BitDo M30" },
    "valve.steamdeck": { "brand": "valve", "style": "steamdeck", "name": "Steam Deck (built-in)" }
  },
  "models": {
    "sony.ds4.v1":   { "family": "sony.dualshock4", "ids": ["054c:05c4"] },
    "sony.ds4.v2":   { "family": "sony.dualshock4", "ids": ["054c:09cc"] },
    "sony.ds4.adapter": { "family": "sony.dualshock4", "ids": ["054c:0ba0"],
                       "notes": "Sony USB wireless adapter (CUH-ZWA1)" },
    "sony.dualsense":{ "family": "sony.dualsense",  "ids": ["054c:0ce6"] },
    "sony.dualsense-edge": { "family": "sony.dualsense", "ids": ["054c:0df2"],
                       "caps": ["paddle1", "paddle2"] },
    "nintendo.switch-pro": { "family": "nintendo.switch-pro", "ids": ["057e:2009"] },
    "valve.steamdeck": { "family": "valve.steamdeck", "ids": ["28de:1205"] }
  },
  "capabilities_by_family": {
    "sony.dualshock4": ["gyro", "accel", "touchpad", "touchpad_click", "rumble", "lightbar"],
    "sony.dualsense":  ["gyro", "accel", "touchpad", "touchpad_click", "rumble", "adaptive_triggers", "misc1"],
    "valve.steamdeck": ["gyro", "accel", "trackpad_l", "trackpad_r", "paddle1", "paddle2", "paddle3", "paddle4", "rumble"]
  },
  "glyph_sets": {
    "playstation": { "face_south": "✕", "face_east": "○", "face_west": "□", "face_north": "△", "l1": "L1", "select": "Share", "start": "Options" },
    "xbox":        { "face_south": "A", "face_east": "B", "face_west": "X", "face_north": "Y", "l1": "LB", "select": "View", "start": "Menu" },
    "nintendo":    { "face_south": "B", "face_east": "A", "face_west": "Y", "face_north": "X", "l1": "L", "select": "−", "start": "+" }
  }
}
```

All VID:PIDs in the shipped file are cross-checked against SDL
`controller_list.h` / `usb_ids.h`, the kernel's `hid-ids.h` / `xpad.c`, and
SDL_GameControllerDB, with the sources recorded in the file's `sources` array.

**Seeding the DB.** SDL's `SDL_GameControllerDB` (community
`gamecontrollerdb.txt`) and SDL's own `controller_type` tables cover hundreds
of VID:PIDs. We can generate a first draft from them and then curate families
and brands by hand. Both are under the **zlib** licence: SDL itself, and the
community DB's `LICENSE` file, which is the SDL zlib text. The zlib licence
only asks that we don't misrepresent the origin and keep the notice in
modified sources, so credit both in `data/README`.

## 3. The hard cases: pads that lie about who they are

| Case | What the OS sees | Consequence | Handling |
|------|------------------|-------------|----------|
| **8BitDo in X-input mode** (X) | Many models show up as Microsoft Xbox 360 `045e:028e` (widely reported, not in any upstream table; which models do is **[VERIFY]** per model/firmware). Some newer models keep their own VID in XInput (`2dc8:3106` Ultimate 2.4G / Pro 2 wired, `2dc8:310a` Ultimate 2C, `2dc8:310b` Ultimate 2, `2dc8:2000/201e` Pro 2 Wired for Xbox; xpad table) | `045e:028e` pads can't be matched to "all 8BitDo" automatically | **User claim**: on first sight of an unknown/ambiguous device, the UI asks "What controller is this?" and stores `device id → model` in the registry. The evdev **name won't say 8BitDo**: xpad names the device from its own VID:PID table (`045e:028e` → `Microsoft X-Box 360 pad`), not from the USB product string. The USB `product` string in sysfs might. **[VERIFY]** (S8) |
| **8BitDo SN30 Pro+ over Bluetooth in X mode** | Xbox One S BT `045e:02e0` (the kernel lists it as `USB_DEVICE_ID_8BITDO_SN30_PRO_PLUS` under the Microsoft vendor) | Looks like a real Xbox One S | User claim; BT MAC OUI hint |
| **8BitDo in Switch mode** (S) | Nintendo Switch Pro `057e:2009`; hid-nintendo binds and sets `uniq` to the MAC the pad reports | Looks like a real Switch Pro | Same user claim. The `uniq` MAC OUI can hint at the vendor **[VERIFY]** (S8): does an 8BitDo report a non-Nintendo OUI? |
| **8BitDo in D-input mode** | Its own `2dc8:xxxx` (e.g. Pro 2 `6003` USB / `6006` BT, SN30 Pro `6001` / `6101`, SN30 Pro+ `6002` / `6102`, M30 `5006` USB / `0651` BT) | Good, identifiable | DB lookup |
| **8BitDo in macOS / Apple mode** (A, Start+A on older pads) | Reportedly an Xbox Wireless (BT) or DS4 identity, depending on the model **[VERIFY]** (S8) | Like X mode | User claim |
| **8BitDo / other wireless dongles** | The dongle's VID:PID (`2dc8:3100` Adapter, `3101`–`3104` Receiver, `3106` Adapter 2 / Ultimate 2.4G), or the identity it impersonates (`045e:028e` X mode, `057e:2009` Switch mode **[VERIFY]**), not the pad's | All pads on one dongle look the same | Model = the dongle, plus a user claim per slot |
| **Sony wireless adapter** | `054c:0ba0`, even with no pad paired; hid-playstation tracks connect/disconnect from the input report | One identity for whichever DS4 is paired | Model `sony.ds4.adapter`; `uniq` semantics **[VERIFY]** |
| **Third-party "Xbox compatible" pads** (PowerA, PDP, GameSir) | Often their own VID, sometimes `045e` | Mostly identifiable | DB + name heuristics |
| **Generic clones** | Fake Sony/Microsoft IDs | Might be wrongly matched as genuine | Acceptable; the user can override the claim |
| **Handheld built-ins** (GPD etc.) | Also `045e:028e` (SDL_GameControllerDB lists GPD Win Max 2, Be1, MSI GC20 under this ID) | Same ambiguity as 8BitDo X mode | DB + DMI hints later |
| **Steam Deck built-in** | `28de:1205` (hid-steam; evdev node only when Steam isn't running) | Fine | Special style `steamdeck` |
| **Steam Controller** (2015) | `28de:1102` wired, `28de:1142` wireless dongle (hid-ids). SDL also lists BT `1105`/`1106` | Fine | Family `valve.steamcontroller` |
| **Steam Controller** (2026, "Triton"/"Ibex") | `28de:1302` (`1303` BLE, `1304`/`1305` dongles) per SDL and hid-ids | Fine | Same family, new model |

**User claims beat DB detection.** The registry entry
`{device_id, claimed_model, label, color}` is stored in `$DATA/devices.json`.
The UI shows a friendly name ("Blue DS4", "8BitDo Pro 2 (X-mode)").

**Mode-agnostic families.** One physical 8BitDo Pro 2 can show up as three
different identities depending on its mode switch. The 8BitDo product page
names the four positions Switch, Android, D-input and X-input. The registry can
link all of them to one device, so family/brand rules follow the physical pad
whatever mode it's in.

## 4. Style inference

When no family is known, infer the style:

1. DB family → style
2. Name heuristics: `"Xbox"|"X-Box"|"XInput"` → `xbox`; `"Wireless Controller"` + Sony VID → `playstation`; `"Pro Controller"` → `nintendo`
3. Default → `xbox` (it matches what SDL reports)

Style affects **glyphs** in the UI and **label-match** presets. It never
affects positional bindings.

## 5. Player slots

Getting player order right matters a lot for couch play and for the docked Deck.

### 5.1 Policies (user-selectable; can be set per system)

| Policy | Behaviour |
|--------|-----------|
| `steam-order` (default) | Match whatever order Steam assigns its virtual gamepads. Steam's slot number is in each virtual pad's evdev name (`Microsoft X-Box 360 pad <N>`), and `virtualgamepadinfo.txt` says which physical model is in each slot (§5.2). Whether `<N>` is exactly Steam's player number, and whether "Reorder controllers" renumbers it, is **[VERIFY]** (S1). |
| `external-first` | External controllers become P1..Pn in connection order. Deck built-in controls go last, or are disabled for emulation. This is the "docked" experience. |
| `pinned` | The user pins devices to slots: "Blue DS4 is always P1, 8BitDo P2". Unpinned devices fill the gaps. |
| `deck-only` | Only the built-in controls (handheld). |

Docked detection can switch the policy automatically:
`handheld → deck-only`, `docked → external-first`. Signals, in order of
reliability:

1. **External display**: any `/sys/class/drm/card*-*/status` other than the internal panel (`card*-eDP-*`) reading `connected`. The kernel's `status` attribute is always one of `connected` / `disconnected` / `unknown` (`drm_sysfs.c` `status_show` → `drm_get_connector_status_name`). Don't hard-code `card0` vs `card1`, since the index differs between SteamOS releases and models. Glob, and skip `eDP`. On the Deck an external screen arrives as a `DP-*` connector through USB-C DP alt-mode (dock or adapter) **[VERIFY]** (S9): the connector name on LCD vs OLED.
2. **External power**: `/sys/class/power_supply/*` with `type` = `Mains` or `USB` and `online` = `1` (kernel ABI `sysfs-class-power`). The Deck's supply name (`ACAD`?) is **[VERIFY]** (S9), so glob by `type` rather than name. Power alone isn't "docked" (charging in handheld), so only use it as a tiebreaker.
3. **External controller count > 0** is the strongest *intent* signal and is already known from the probe.

Rule: `docked = external_display_connected || (external_power && external_pads > 0)`.
Re-evaluate at launch only. No daemon is needed.

### 5.2 Mapping slots to what the emulator sees

Emulators bind to **their** device index (SDL index, `SDL-0`, Dolphin's
`SDL/0/<name>`, a GUID...). With Steam Input on, those are Steam virtual pads.
The adapter has to write **P1's bindings on the device the emulator will see as
P1**, so we need two links: physical controller → Steam slot, and Steam
slot → emulator index.

#### What Steam gives a launched game (confirmed from source)

When Steam launches anything (Steam game or non-Steam shortcut), the
process environment carries:

| Variable | Content | Who reads it |
|----------|---------|--------------|
| `SteamVirtualGamepadInfo` | Path to an INI-like file, e.g. `~/.local/share/Steam/config/virtualgamepadinfo.txt` (seen in SDL #14410 for a non-Steam shortcut). Proton launches get `SteamVirtualGamepadInfo_Proton` instead. | SDL ≥ 2.30 / SDL3 |
| `SDL_GAMECONTROLLER_IGNORE_DEVICES` | Comma-separated `0xVVVV/0xPPPP` list of the **physical** pads Steam is virtualising | SDL, Proton winebus |
| `SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD=1` | Tells SDL not to drop `28de:11ff`. Without it SDL ignores Steam virtual pads as game controllers. | SDL |
| `SDL_JOYSTICK_HIDAPI_STEAMXBOX=0`, `SDL_GAMECONTROLLERCONFIG=...Steam Virtual Gamepad...` | Mapping for the virtual pad | SDL |

The info file has one section per Steam slot (parser in SDL
`SDL_steam_virtual_gamepad.c`):

```ini
[slot 0]
name=PS4 Controller        ; Steam's display name for the physical pad
VID=0x054c                 ; physical VID
PID=0x09cc                 ; physical PID
type=ps4                   ; SDL gamepad type string (xbox360, xboxone, ps4, ps5, switchpro, ...)
handle=<uint64>            ; Steam Input API InputHandle_t
```

SDL then links each virtual pad to a slot. On Linux it parses the digits after
`pad ` in the evdev name `Microsoft X-Box 360 pad <N>` (`GetSteamVirtualGamepadSlot`,
only for `28de:11ff`). The HIDAPI path parses `GamePad-<N>` (1-based). For that
joystick, SDL then reports the **physical** pad's name, VID, PID and gamepad
type (`SDL_GetJoystickVendor/Product`, `SDL_GetRealGamepadType`), and the Steam
handle (`SDL_GetGamepadSteamHandle`). The **GUID is unchanged**: it is still the
`28de:11ff` virtual-pad GUID. SDL re-reads the file when its mtime changes
(polled every 3 s) and sends `SDL_CONTROLLERSTEAMHANDLEUPDATED` /
`SDL_EVENT_GAMEPAD_STEAM_HANDLE_UPDATED`. It also swaps A/B for Switch-type
slots, because Steam's "Use Nintendo button layout" sends button 0 for the
east button. SDL's Linux evdev backend returns player index −1, so the
emulator gets no player index from Steam on Linux.

**Consequences for the design:**

1. **map-helper can do the same thing SDL does, outside the emulator.** Our launch wrapper is the command Steam runs, so it inherits `SteamVirtualGamepadInfo`. It reads the file, lists `28de:11ff` evdev nodes, and parses `<N>` from each name. That gives us **slot N → physical VID:PID + type** without any on-device guesswork. This answers most of S1.
2. **`SDL_GAMECONTROLLER_IGNORE_DEVICES` answers "is this pad behind Steam Input?"** (spike S2). A physical pad whose `0xVVVV/0xPPPP` is in the list is virtualised. Pads not in the list are native. See [05](05-steam-input-strategy.md).
3. **Identical pads are still ambiguous.** Two DS4 v2s give two slots with the same VID/PID/type, and nothing in the file links a slot to a MAC. `handle` is an opaque Steam API handle. **Disambiguation by input correlation:** if S3 confirms we can read physical evdev nodes while Steam runs, the wizard asks "press a button on the controller you want as P1". The same press shows up on exactly one `Microsoft X-Box 360 pad <N>` node, which links MAC → slot exactly. Without that, fall back to user claims per slot.
4. **Emulators on SDL ≥ 2.30 / SDL3 see real names.** Under Steam, an SDL 2.30+ emulator reports the virtual pad as e.g. `PS4 Controller` with VID `054c`, not "Xbox 360 Controller". Name-keyed device strings (Dolphin `SDL/0/<name>`, RetroArch autoconfig by name/VID/PID) therefore follow the **physical** model. GUID-keyed configs (yuzu-family, Ryujinx) still see the virtual GUID. Each adapter must record which one its emulator uses and which SDL version its Flatpak/AppImage bundles. **[VERIFY]** per emulator (S6).
5. **The emulator's SDL index order is not guaranteed to equal slot order.** SDL numbers joysticks in discovery order, and the slot is only metadata. Adapters that bind by index (`SDL-N`) must compute the index by enumerating the same way SDL does (evdev nodes in order). Adapters that can bind by name should prefer the slot-aware name. **[VERIFY]** (S1): does SDL index order match `<N>` order with 3+ pads and after hot-plug?
6. **Virtual pads are recreated at every launch.** Steam tears down and recreates `Microsoft X-Box 360 pad 0` each time a game or shortcut starts (steam-for-linux #13665). The wrapper must probe *after* Steam has created the pads for this launch. Poll for the `28de:11ff` nodes and an updated `virtualgamepadinfo.txt` mtime for up to ~2 s **[VERIFY]** (timing). It must not cache an earlier launch's view.
7. **Flatpak emulators**: the environment variable crosses into `flatpak run`, but the file must be readable in the sandbox, and SDL's 3 s polling still applies. **[VERIFY]** for each Flatpak (S1/S6).
8. **Proton/Wine-hosted Windows emulators** ignore the info file (Proton's winebus clears the hint and maps slots from the evdev name itself). Same slot logic, different consumer.

#### Policies on top of that

- `steam-order` with Steam Input on: P1 = slot 0. We know the model in each slot from the info file, so per-model rules resolve without a user claim.
- `external-first` / `pinned`: we can't reorder Steam's slots (no stable API; Steam's "Reorder controllers" UI only). We **rewrite each emulator's player config** so that player K points at the device for the slot holding the wanted controller (by index or name, per adapter). Point 3 covers identical models.
- Native mode (Steam Input off for that pad): emulators see the real pad. Prefer **GUID or name matching** where the emulator supports it (yuzu-family, Ryujinx, Citra-family, Dolphin by name, RetroArch by name + VID/PID). Use the index only where an emulator can do nothing else (PCSX2/DuckStation `SDL-N`, **[VERIFY]**).

This is still the riskiest technical area. Spike S1 in
[13](13-research-spikes.md) now has to *confirm* the mechanism above on device
and settle points 3, 5, 6 and 7. It no longer has to discover the mechanism.

## 6. Capabilities

Rules can need capabilities: `gyro`, `touchpad`, `paddles`, `analog_triggers`,
`rumble`. When a rule's capability is missing on the resolved controller, the
binding is skipped with a warning in the trace. Example: "Gyro aim skipped: 8BitDo
SN30 Pro has no gyro."

## Sources

Checked 2026-10-22. Upstream sources were read only (shallow clones), never built.

- **SDL3** `libsdl-org/SDL` `main` @ `8adc0f98837db84fd24f17c339e59dcf36a17156`:
  - [`src/joystick/SDL_steam_virtual_gamepad.c`](https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/SDL_steam_virtual_gamepad.c): env var `SteamVirtualGamepadInfo` (L136), Wine exclusion (L138–146), `[slot N]` / `name` / `VID` / `PID` / `type` / `handle` parser (L159–243), 3 s mtime poll (L161–185)
  - [`src/joystick/linux/SDL_sysjoystick.c`](https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/linux/SDL_sysjoystick.c): `GetSteamVirtualGamepadSlot` parses `"pad "` + digits from `EVIOCGNAME` (L237–252), only for Valve `11ff` (L516–520); player index −1 (L1142–1145)
  - [`src/joystick/hidapi/SDL_hidapi_xbox360.c`](https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/hidapi/SDL_hidapi_xbox360.c): `GamePad-%d` slot (L289–294)
  - [`src/joystick/SDL_joystick.c`](https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/SDL_joystick.c): name override (L1007–1035), Nintendo face swap (L1327–1346), steam handle (L1479–1483), handle-update events (L2922–2975), `SDL_IsJoystickSteamVirtualGamepad` (L3507–3514), VID/PID override vs unchanged GUID (L3756–3810)
  - [`src/joystick/usb_ids.h`](https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/usb_ids.h) (Sony L175–181, Nintendo L122–137, Microsoft L191–210, `STEAM_VIRTUAL_GAMEPAD 0x11ff` L211, 8BitDo L73–82) and [`controller_list.h`](https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/controller_list.h) (Sony L107–110, L177, L643; Xbox L199, L206, L363–373, L645–648; 8BitDo L487–489, L650–657; Nintendo L585–599; Valve L661–673)
- **SDL2** `SDL2` branch @ `8acf7cfc0f88717e5c036f60f0314bfcafe39189`: same `SDL_steam_virtual_gamepad.c`; [`WhatsNew.txt`](https://github.com/libsdl-org/SDL/blob/8acf7cfc0f88717e5c036f60f0314bfcafe39189/WhatsNew.txt) L5–11 (2.30.0 added `SDL_GameControllerGetSteamHandle`, "could also change the name, VID, and PID"); [`src/joystick/SDL_gamecontroller.c`](https://github.com/libsdl-org/SDL/blob/8acf7cfc0f88717e5c036f60f0314bfcafe39189/src/joystick/SDL_gamecontroller.c) L2153–2166 (`SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD`); [`include/SDL_hints.h`](https://github.com/libsdl-org/SDL/blob/8acf7cfc0f88717e5c036f60f0314bfcafe39189/include/SDL_hints.h) L529–555 (`IGNORE_DEVICES` format)
- **Linux** `torvalds/linux` @ `2a08195e4db5aba84600db6518089a1dbe2d04c7`:
  - [`drivers/hid/hid-ids.h`](https://github.com/torvalds/linux/blob/2a08195e4db5aba84600db6518089a1dbe2d04c7/drivers/hid/hid-ids.h): 8BitDo L25–26, Microsoft Xbox BT L1065–1071 (incl. `USB_DEVICE_ID_8BITDO_SN30_PRO_PLUS 0x02e0`), Nintendo L1120–1133, Sony L1360–1369, Valve L1410–1417
  - [`drivers/hid/hid-playstation.c`](https://github.com/torvalds/linux/blob/2a08195e4db5aba84600db6518089a1dbe2d04c7/drivers/hid/hid-playstation.c): `DS_FEATURE_REPORT_PAIRING_INFO 0x09` (L92–93), `DS4_FEATURE_REPORT_PAIRING_INFO 0x12` (L352–353), `uniq` copied to input devs (L652), `dualsense_get_mac_address` (L1183–1204), `hdev->uniq = %pMR` (L1788, L2789), `dualshock4_get_mac_address` USB vs BT (L2148–2186), "hidraw applications such as Steam" (L1963–1966), `Motion Sensors` / `Touchpad` (L916, L953), device table (L2939–2957)
  - [`drivers/hid/hid-nintendo.c`](https://github.com/torvalds/linux/blob/2a08195e4db5aba84600db6518089a1dbe2d04c7/drivers/hid/hid-nintendo.c): IMU node `uniq` / name `(IMU)` (L2140–2147), gamepad `uniq`/name/phys (L2204–2206), MAC from device-info subcommand, `%pMU` (L2493–2509), device table (L4442–4479)
  - [`drivers/hid/hid-steam.c`](https://github.com/torvalds/linux/blob/2a08195e4db5aba84600db6518089a1dbe2d04c7/drivers/hid/hid-steam.c): input device removed while client has hidraw open (L22–28, L1465–1482), name/`uniq` = serial (L1122–1126), `XXXXXXXXXX` fallback (L1392–1394)
  - [`drivers/hid/hid-microsoft.c`](https://github.com/torvalds/linux/blob/2a08195e4db5aba84600db6518089a1dbe2d04c7/drivers/hid/hid-microsoft.c) L427–438 (Xbox BT + 8BitDo SN30 Pro+ BT)
  - [`drivers/input/joystick/xpad.c`](https://github.com/torvalds/linux/blob/2a08195e4db5aba84600db6518089a1dbe2d04c7/drivers/input/joystick/xpad.c): Microsoft L123–134, 8BitDo L382–389, vendor matches L516–517 / L565–566, name/phys only (L1955–1956, L2076, L2096)
  - [`net/bluetooth/hidp/core.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/net/bluetooth/hidp/core.c) L800–807 (`phys` = src adapter, `uniq` = dst device)
  - [`drivers/gpu/drm/drm_sysfs.c`](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/gpu/drm/drm_sysfs.c) L229–240 and `drm_connector.c` `drm_get_connector_status_name` (connected/disconnected/unknown)
  - [`Documentation/ABI/testing/sysfs-class-power`](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-class-power) (`online`, `type`)
- **BlueZ** [`src/shared/uhid.c`](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/src/shared/uhid.c) L417–426 (`UHID_CREATE2` phys = src, uniq = dst)
- **Proton Wine** `ValveSoftware/wine` `proton_10.0` @ `b8fdff8e1f855b5276ec4ddca0f31b2792554322`: [`dlls/winebus.sys/bus_udev.c`](https://github.com/ValveSoftware/wine/blob/b8fdff8e1f855b5276ec4ddca0f31b2792554322/dlls/winebus.sys/bus_udev.c) L1593–1598 (`"Microsoft X-Box 360 pad %u"`, `28de:11ff`); [`bus_sdl.c`](https://github.com/ValveSoftware/wine/blob/b8fdff8e1f855b5276ec4ddca0f31b2792554322/dlls/winebus.sys/bus_sdl.c) L922–935 (`SDL_GAMECONTROLLER_IGNORE_DEVICES[_EXCEPT]`), L1170–1172 (clears `SteamVirtualGamepadInfo`)
- **steam-devices** `ValveSoftware/steam-devices` @ `22ec85e5ff5ea2e15c56d71a41bcbef46356cd60`: [`60-steam-input.rules`](https://github.com/ValveSoftware/steam-devices/blob/22ec85e5ff5ea2e15c56d71a41bcbef46356cd60/60-steam-input.rules) L5 (uinput), L19–59 (Sony/Nintendo hidraw)
- **SDL_GameControllerDB** `mdqinc/SDL_GameControllerDB` @ `ff333823a85ae896e73f4c53670932cf0f728adb`: `gamecontrollerdb.txt` Linux section (8BitDo GUIDs decoded to VID:PID; `045e:028e` shared by GPD/MSI/Be1; `28de:11ff` "Steam Virtual Gamepad"), [`LICENSE`](https://github.com/mdqinc/SDL_GameControllerDB/blob/ff333823a85ae896e73f4c53670932cf0f728adb/LICENSE) (zlib)
- **Issue trackers**: [libsdl-org/SDL#14410](https://github.com/libsdl-org/SDL/issues/14410) (`SteamVirtualGamepadInfo=/home/deck/.local/share/Steam/config/virtualgamepadinfo.txt` for non-Steam shortcuts; `_Proton` variant); [ValveSoftware/Proton#4707](https://github.com/ValveSoftware/Proton/issues/4707) (game environment dump with `SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD=1`, `SDL_GAMECONTROLLER_IGNORE_DEVICES`, `SDL_JOYSTICK_HIDAPI_STEAMXBOX=0`); [Proton#150](https://github.com/ValveSoftware/Proton/issues/150) (`IGNORE_DEVICES` set by the Steam client); [steam-for-linux#13029](https://github.com/ValveSoftware/steam-for-linux/issues/13029) and [#13665](https://github.com/ValveSoftware/steam-for-linux/issues/13665) (dmesg `Microsoft X-Box 360 pad 0 as /devices/virtual/input/...`, recreated per launch)
- **8BitDo**: [Pro 2 product page](https://www.8bitdo.com/pro2/) (mode switch: Switch, Android, D-input, X-input)
