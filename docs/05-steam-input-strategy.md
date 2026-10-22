# 05 — Steam Input Strategy

Steam Input is always there in Game Mode. We have to decide on purpose how we
coexist with it.

## The two modes

### Mode P: Passthrough (default)

```
DS4 ──▶ Steam Input ("Gamepad" template, no remaps) ──▶ Steam Virtual Gamepad (Xbox-like) ──▶ Emulator
```

- What the emulator sees: a `uinput` pad `28de:11ff` named `Microsoft X-Box 360 pad <N>`, positional Xbox-style, the same for every controller. Under SDL ≥ 2.30 / SDL3, *with* Steam's `SteamVirtualGamepadInfo` file, SDL reports the physical pad's name, VID/PID and type for that virtual pad. The GUID stays the virtual one ([04 §5.2](04-controller-identification.md#52-mapping-slots-to-what-the-emulator-sees)).
- **map-helper still knows the physical controller** from its probe and from Steam's `virtualgamepadinfo.txt`, so DS4 and 8BitDo rules can still differ. We write different emulator bindings per launch depending on who's plugged in.
- **Nintendo-layout caveat.** With Steam's "Use Nintendo Button Layout" (the default for Switch-type pads), Steam sends virtual button 0 for the **east** (A) button. SDL 2.30+ swaps it back to positional when the slot's type is `switchpro`/Joy-Con (SDL `ShouldSwapFaceButtons`). Older SDL, and non-SDL readers, see A/B (and X/Y) swapped. So "`face_south` is virtual `A`" only holds for non-Nintendo slots, or for SDL ≥ 2.30 emulators. Adapters for emulators on older SDL must apply the swap for Switch-type slots. **[VERIFY]** per emulator (S6).
- Steam features keep working: the guide button/QAM, per-game Steam layouts, gyro-to-mouse via Steam, and back paddles (Deck L4/R4 etc.) via Steam.
- Lost: native gyro/touchpad data reaching the emulator, unless the emulator reads motion some other way. **DSU/cemuhook** motion servers fill this gap:
  - **SteamDeckGyroDSU** (`kmicki/SteamDeckGyroDSU`) serves the **Deck's built-in** IMU over DSU on UDP `26760` (port configurable with `SDGYRO_SERVER_PORT`). It sends motion only, no buttons, and runs as a user service. Last release v2.1.1 (2024-01-23), last push 2024-03. Issues are still being filed through 2026, and in 2026-01 it merged Legion Go S support. Treat it as *low-activity but used*. Whether it works on the current SteamOS stable is **[VERIFY]** (S10). EmuDeck can install it **[VERIFY]**.
  - **evdevhook2** (`v1993/evdevhook2`, successor of the archived `evdevhook`) is a DSU server for pads with **kernel motion drivers**: DS4, DualSense, Switch Pro and Joy-Cons (DS3 untested). It reads the `Motion Sensors` / `(IMU)` evdev nodes that hid-playstation and hid-nintendo create, so it needs no hidraw and can coexist with Steam owning hidraw **[VERIFY]** (S3/S10). It ships an AppImage. Last release v1.0.2 (2024-04). Up to 4 pads per server; run more instances on other ports for more.
  - **joycond-cemuhook** (`joaorb64/joycond-cemuhook`) covers Joy-Cons / Switch Pro via joycond. Last push 2024-12. Superseded by evdevhook2 for our purposes.
  - **Handheld Daemon** (`hhd-dev/hhd`) and **InputPlumber** are actively maintained (2026 releases), but they are full input stacks for other handhelds. Out of scope as dependencies.
  - **Consumers (DSU clients):** Cemu (`src/input/api/DSU`), Dolphin ("DSU Client", `InputCommon/ControllerInterface/DualShockUDPClient`), Azahar/Citra-family (`src/input_common/udp`), yuzu-family (`input_common/drivers/udp_client`) and Ryujinx-family (CemuHook motion) **[VERIFY]** for the current forks (Eden, Citron, Ryubing). RetroArch, PCSX2, DuckStation and RPCS3 don't take DSU motion **[VERIFY]**.
  - So a v2 "motion in passthrough" component is mostly *configuration*: launch evdevhook2 (external pads) and/or SteamDeckGyroDSU (Deck), then point each DSU-capable emulator's motion source at `127.0.0.1:26760` and the right pad slot. We don't need to write a DSU server.
- Back paddles: Steam virtual pads may not expose paddles to the emulator, so
  in passthrough paddles are mapped *in Steam* to other buttons. map-helper
  can **advise** (show a hint) but doesn't write Steam layouts in v1.

### Mode N: Native

```
DualSense ──(Steam Input disabled for this controller type or game)──▶ Emulator via SDL/evdev/hidraw
```

- The emulator sees the real controller, with its gyro, touchpad, paddles, GUID and name.
- Needed for: best gyro in Cemu/Switch emulators/Citra, RPCS3 DualSense handler features, adaptive triggers.
- Costs: Steam guide button chords may stop working in-game, along with Steam overlay navigation using that pad, and Steam-level remaps.
- Not available for the **Deck's built-in controls** in Game Mode: hid-steam removes its evdev gamepad while Steam holds the hidraw node open, so the built-ins only exist as a Steam virtual pad.

How a user turns Steam Input off, and where Steam stores it:

- **Globally per controller type**: Steam Settings → Controller → "PlayStation / Xbox / Switch / Generic controller support". These are **per-user** settings in `~/.local/share/Steam/userdata/<accountid>/config/localconfig.vdf` (the `UserLocalConfigStore`). Steam's client-settings protobuf maps them to that store:

  | Setting | Key | Type / default |
  |---------|-----|----------------|
  | PlayStation | `SteamController_PSSupport` | int, default `1` |
  | Xbox | `SteamController_XBoxSupport` | bool (default off; SDL#14410 notes Xbox pads aren't put behind Steam Input by default) |
  | Xbox extended driver | `SteamController_XBoxDriver` | bool |
  | Switch | `SteamController_SwitchSupport` | bool |
  | Generic | `SteamController_GenericGamepadSupport` | bool |

  `SteamController_PSSupport` is three-valued. `1` = "Enabled in games without support" is the default and is documented by third parties. Our assumption is `0` = disabled and `2` = enabled everywhere **[VERIFY]** (S2). How "games without support" is decided for a **non-Steam shortcut** is also **[VERIFY]** (S2). Our guess is that it's treated as "without support", i.e. Steam Input on.

- **Per game**: game properties → Controller → override. Stored in the same `localconfig.vdf` under `UserLocalConfigStore` → `apps` → `<appid>` → `UseSteamControllerConfig`: `"0"` = disabled, `"1"` = use default settings (SRM deletes the key for this), `"2"` = enabled (SRM `controller-manager.ts`). **It applies to non-Steam shortcuts.** The key is the shortcut's **unsigned 32-bit app id** (SRM switched from the signed id after a 2026 Steam update stopped honouring it; SRM #891).

Writing these files while Steam runs gets overwritten. map-helper only
**reads** them (see below) and never writes them in v1
([ADR-004](adr/004-steam-input-stance.md)).

### The per-game override in `doctor`

A non-Steam shortcut set to "Disable Steam Input" breaks every emulator it
launches: the environment is byte-identical either way, so SDL still ignores
the physical pads while Steam stops feeding the virtual one, and EmuDeck's
configs bind the virtual pad (spike S2, `game-steam-input-on/off`).
`map-helper doctor` reports it as an **error** for any shortcut whose name,
`Exe`, `StartDir` or `LaunchOptions` points at a frontend or emulator (ES-DE,
EmuDeck launchers, RetroArch, Dolphin...). It reads:

- `userdata/<account>/config/shortcuts.vdf` (binary KeyValues: `shortcuts` →
  `<n>` → `appid` int32, `AppName`, `Exe`, `StartDir`, `LaunchOptions`; format
  as `steam-shortcut-editor`, SRM's library, parses it) to name each shortcut
  and get its id. The id is stored signed; Steam keys `localconfig.vdf` by the
  same 32 bits read unsigned.
- `userdata/<account>/config/localconfig.vdf` →
  `UserLocalConfigStore/apps/<unsigned id>/UseSteamControllerConfig` = `"0"`.
  An entry only under the old **signed** id is reported as info: current
  Steam ignores it (SRM#891).

**[VERIFY]** that Steam itself stores the Game Mode override there. On the
owner's Deck it wasn't in `localconfig.vdf` 14 minutes after setting it. The
SRM code and community fixes all use this key, and the community fixes say to
close Steam before editing the file because Steam rewrites it from memory, so
the likely explanation is that Steam saves it late (at exit or restart). The
capture that settles it: set "Disable Steam Input" on a test shortcut in Game
Mode, then **fully exit Steam** (switch to Desktop Mode, or reboot), and
`grep -n UseSteamControllerConfig` plus the shortcut's unsigned id in
`~/.local/share/Steam/userdata/*/config/localconfig.vdf`; then set it back to
Default, exit Steam again and check the entry is gone or `"1"`. If it isn't
there either time, look for the id under
`steamapps/common/Steam Controller Configs/<account>/config/` and
`userdata/<account>/241100/remote/`. Print only yes/no and key names, not the
account id.

## What map-helper does

1. **Detect the mode at launch, per physical pad.** Our launch wrapper is the process Steam starts, so it inherits Steam's launch environment. Signals, strongest first:
   1. `SDL_GAMECONTROLLER_IGNORE_DEVICES` in our own environment lists the `0xVVVV/0xPPPP` of every physical pad Steam is virtualising for this launch. A physical pad whose VID/PID is listed is in **P**. A pad that isn't listed is **N**.
   2. The file named by `SteamVirtualGamepadInfo` (`[slot N]` with the physical `VID`/`PID`/`type`) together with the `28de:11ff` `Microsoft X-Box 360 pad <N>` evdev nodes. Each slot is a pad in P, and the slot number is its Steam order.
   3. Fallback when neither variable is set (launched outside Steam, e.g. ES-DE in Desktop Mode without a Steam shortcut): no virtual pads for this process → every pad is N.
   4. Advisory cross-check: `localconfig.vdf` `UseSteamControllerConfig` for this shortcut's app id and the `SteamController_*Support` keys. This is for the UI ("Steam Input is off for PlayStation pads") and for planning before launch. It is not the runtime truth.

   A mix is normal: Deck controls via Steam (always) plus a DualSense in native mode when PlayStation support is off. Identical pads (two DS4s) can't be told apart from the file alone. See [04 §5.2](04-controller-identification.md#52-mapping-slots-to-what-the-emulator-sees) point 3. Remaining on-device checks are in spike S2: timing of pad creation vs our probe, and whether the variables survive `flatpak run`.
2. **Render accordingly.** Adapters get `steam_input_mode` per player plus, in P, the slot number and the physical type. They choose a device reference (virtual pad index or slot-aware name vs native GUID/name) and input names. In P, `face_south` is the virtual pad's `A`, whatever the physical controller is, with the Nintendo-layout caveat above.
3. **Respect the Steam layout assumption.** In P we assume the Steam layout
   for that shortcut is a **1:1 gamepad passthrough**. If the user has remapped
   in Steam *and* in map-helper, the two stack and get confusing. Mitigations:
   - Docs and UI copy: "Leave your Steam layout as the default gamepad template; map buttons here."
   - **[VERIFY]**/stretch: read the active Steam layout for the shortcut and warn if it isn't a passthrough. SRM reads per-app template choices from `steamapps/common/Steam Controller Configs/<accountid>/config/configset_controller_<type>.vdf` → `controller_config` → `<shortcut title>` (one file per controller type, e.g. `ps4`, `neptune`), and the templates themselves from `steamapps/workshop/content/241100/` (user/workshop) and `controller_base/templates/` (Valve). Telling "passthrough" from "remapped" from those entries is **[VERIFY]**.
4. **Offer a per-system "use native mode" toggle** with clear trade-offs. In v1 we only *advise* and link to the Steam setting. Writing Steam configs is risky and out of scope ([ADR-004](adr/004-steam-input-stance.md)).

## Why not manage Steam Input layouts too?

- SRM and Steam already do it. Steam's config formats are undocumented and change.
- Writing Steam's config while Steam is running can get overwritten or corrupt state.
- The value we add is the emulator layer, which nobody owns.

Revisit after v1: an *optional* integration that sets SRM controller templates
per parser could be a cheap win.

## Sources

Checked 2026-10-22.

- Steam virtual pad environment, info file format and SDL behaviour: see [04 Sources](04-controller-identification.md#sources) (SDL `SDL_steam_virtual_gamepad.c`, `SDL_joystick.c` `ShouldSwapFaceButtons` L1327–1346, SDL2 `SDL_gamecontroller.c` L2153–2166, Proton `bus_sdl.c`/`bus_udev.c`, SDL#14410, Proton#4707, Proton#150, steam-for-linux#13665).
- Steam settings keys and stores: `SteamTracking/Protobufs` @ `5c2b73b24be75d4e0f85889cea48bd669916767f`, [`steam/steammessages_clientsettings.proto`](https://github.com/SteamTracking/Protobufs/blob/5c2b73b24be75d4e0f85889cea48bd669916767f/steam/steammessages_clientsettings.proto) L23–29 (`EClientSettingStore`: Install / UserRoaming / UserLocal) and L204–208 (`SteamController_PSSupport` int default 1, `_XBoxSupport`, `_XBoxDriver`, `_SwitchSupport`, `_GenericGamepadSupport`, all `ConfigStore_UserLocal`).
- `localconfig.vdf` location of the `SteamController_*` keys: EmuDeck-WE [`functions/helperFunctions.ps1`](https://github.com/EmuDeck/emudeck-we/blob/037460efc88c1ab70256ab0833f8f10e7f2904b2/functions/helperFunctions.ps1) L1302–1324 (`steamEnableXboxInput` edits `userdata/*/config/localconfig.vdf`).
- Per-game override: SRM `SteamGridDB/steam-rom-manager` @ `f68289a770ff8537ac8235618b3399844580359b`, [`src/lib/controller-manager.ts`](https://github.com/SteamGridDB/steam-rom-manager/blob/f68289a770ff8537ac8235618b3399844580359b/src/lib/controller-manager.ts) L72–76 (0 Disabled / 1 default / 2 Enabled), L79–83 (`controller_config`, `UserLocalConfigStore`), L105–116 (template dirs), L219–227 and L348–360 (`configset_controller_<type>.vdf` → `controller_config`), L431–432 (`userdata/<id>/config/localconfig.vdf`), L476–509 (`apps/<shortId>/UseSteamControllerConfig`, set at L503); [SRM#891](https://github.com/SteamGridDB/steam-rom-manager/issues/891) (unsigned app id); `src/models/parser.model.ts` L168 (`steamInputEnabled` 0/1/2).
- Hand edits need Steam closed, or Steam overwrites them: [Steam Deck bug report thread](https://steamcommunity.com/app/1675200/discussions/1/3877095200009314997/); per-shortcut script writing `apps/<short id>/UseSteamControllerConfig` = `"0"`: <https://pastebin.com/RSNgjRd3>. Both community sources, not Valve's.
- shortcuts.vdf binary layout: [`tirish/steam-shortcut-editor` `lib/parser.js`](https://github.com/tirish/steam-shortcut-editor/blob/d755f03e28280e64c96e4a6039739fcb41e28f0e/lib/parser.js) @ `d755f03` (SRM's dependency); shortcut id = `crc32(exe + name) | 0x80000000` in SRM [`src/lib/helpers/steam/generate-app-id.ts`](https://github.com/SteamGridDB/steam-rom-manager/blob/f68289a770ff8537ac8235618b3399844580359b/src/lib/helpers/steam/generate-app-id.ts).
- Deck built-ins absent from evdev while Steam runs: `hid-steam.c` L22–28 (see 04 Sources).
- DSU servers: [kmicki/SteamDeckGyroDSU](https://github.com/kmicki/SteamDeckGyroDSU) README (port 26760, `SDGYRO_SERVER_PORT`, motion only), releases (v2.1.1, 2024-01-23), [issues](https://github.com/kmicki/SteamDeckGyroDSU/issues) (#79–#86, 2025-12 to 2026-08); [v1993/evdevhook2](https://github.com/v1993/evdevhook2) README (supported devices, v1.0.2 2024-04-06); [v1993/evdevhook](https://github.com/v1993/evdevhook) (archived); [joaorb64/joycond-cemuhook](https://github.com/joaorb64/joycond-cemuhook); [hhd-dev/hhd](https://github.com/hhd-dev/hhd), [ShadowBlip/InputPlumber](https://github.com/ShadowBlip/InputPlumber) (activity only).
- DSU clients in source: [Cemu `src/input/api/DSU`](https://github.com/cemu-project/Cemu/tree/main/src/input/api/DSU), [Dolphin `DualShockUDPClient`](https://github.com/dolphin-emu/dolphin/tree/master/Source/Core/InputCommon/ControllerInterface/DualShockUDPClient), [Azahar `src/input_common/udp`](https://github.com/azahar-emu/azahar/tree/master/src/input_common/udp).
