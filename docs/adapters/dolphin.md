# Adapter: Dolphin

> Facts below were read from Dolphin source at master `2c805fee8f`
> (2026-10-22, after release 2609a) unless a version is given. Links are in
> [Sources](#sources). Machine-readable tables: [`data/adapters/dolphin.json`](../../data/adapters/dolphin.json).

## Summary

| Field | Value |
|-------|-------|
| Adapter id | `dolphin` (Primehack reuses it with a different path set) |
| Systems | `gc`, `wii` |
| EmuDeck install type | Flatpak `org.DolphinEmu.dolphin-emu` (EmuDeck `emuDeckDolphin.sh`); Flathub tracks Dolphin's **beta** channel |
| Versions covered | 2407 to 2609a and master (SDL Gamepad input names); older names still accepted |
| Priority | **P0** |
| Strategy | global-swap (`GCPadNew.ini`, `WiimoteNew.ini`), plus profile-select enhancement (`Profiles/GCPad/map-helper-*.ini`) |

## Paths

Dolphin splits its user directory across **three XDG roots** on Linux
(`UICommon::SetUserDirectory`). Inside the Flatpak this split is always used.
Natively it is used unless `~/.dolphin-emu/` already exists.

| What | Flatpak (EmuDeck) | Native XDG | Root |
|------|-------------------|------------|------|
| Config root | `~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/` | `${XDG_CONFIG_HOME:-~/.config}/dolphin-emu/` | config |
| Data root | `~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/` | `${XDG_DATA_HOME:-~/.local/share}/dolphin-emu/` | data |
| Cache root | `~/.var/app/org.DolphinEmu.dolphin-emu/cache/dolphin-emu/` | `${XDG_CACHE_HOME:-~/.cache}/dolphin-emu/` | cache |
| GC pads | `GCPadNew.ini` (`[GCPad1]`..`[GCPad4]`) | same | config |
| Wiimotes | `WiimoteNew.ini` (`[Wiimote1]`..`[Wiimote4]`, `[BalanceBoard]`) | same | config |
| Hotkeys | `Hotkeys.ini` (`[Hotkeys]`) | same | config |
| Port types | `Dolphin.ini` `[Core] SIDevice0..3` | same | config |
| Profiles | `Profiles/GCPad/<name>.ini`, `Profiles/Wiimote/<name>.ini`, `Profiles/Hotkeys/<name>.ini` | same | **config** |
| Per-game | `GameSettings/<GAMEID>.ini` | same | **data** |
| Game list cache | `gamelist.cache` | same | cache |

Other layouts: `~/.dolphin-emu/` (one dir; config in `Config/`, cache in
`Cache/`) when it exists outside Flatpak; `<exe dir>/User/` when
`portable.txt` sits next to the binary; `$DOLPHIN_EMU_USERPATH` overrides
everything except portable.

## Format

INI, one section per emulated controller. Keys are `<group>/<control>`, values
are control **expressions**. Keys are case-insensitive. Dolphin deletes keys
whose value equals the default (empty for bindings) when it saves.

Real excerpt, EmuDeck's shipped `GCPadNew.ini` (Steam Input passthrough):

```ini
[GCPad1]
Device = SDL/0/Steam Deck Controller
Buttons/A = `Button E`
Buttons/B = `Button S`
Buttons/X = `Button N`
Buttons/Y = `Button W`
Buttons/Z = `Shoulder R`
Buttons/Start = Start
Main Stick/Up = `Axis 1-`
Main Stick/Down = `Axis 1+`
Main Stick/Modifier = `Thumb L`
Main Stick/Modifier/Range = 50.
Main Stick/Calibration = 100.00 141.42 100.00 141.42 100.00 141.42 100.00 141.42
C-Stick/Up = `Axis 4-`
Triggers/L = `Trigger L`
Triggers/L-Analog = `Trigger L`
D-Pad/Up = `Pad N`
Rumble/Motor = Strong
```

Real excerpt, Dolphin's own shipped profile `Data/Sys/Profiles/GCPad/SDL Gamepad.ini`:

```ini
[Profile]
Buttons/A = `Button A`
Main Stick/Up = `Left Y+`
Main Stick/Down = `Left Y-`
C-Stick/Left = `Right X-`
Triggers/L = `Trigger L`
Triggers/L-Analog = `Trigger L`
D-Pad/Up = `Pad N`
Rumble/Motor = `Motor L` | `Motor R`
```

Expression syntax (`ExpressionParser.cpp`, `MappingCommon.cpp`):

| Need | Syntax |
|------|--------|
| One input | `` `Button S` `` (backticks are required when the name has any non-letter; Dolphin's UI quotes whenever that is true) |
| Either of two (multiple bindings) | `` `Button S` | `Button E` `` |
| Both together | `` `Back` & `Start` `` |
| Ordered hotkey chord | `` @(`Back`+`Start`) `` |
| Other device for one input | `` `SDL/1/PS4 Controller:Button S` `` |
| Unbound | empty value |
| Range scaling | separate key `<group>/<control>/Range = <percent>` |

Sticks have no full-axis token. Every direction is its own key bound to a
half-axis input.

## Device references

`Device = <source>/<id>/<name>` (`DeviceQualifier::ToString`).

- `source`: `SDL`, `evdev`, `SteamDeck` (built-in Deck controls, see below), `DSUClient`, `Bluetooth` (real Wiimote), keyboard/mouse `XInput2`.
- `id`: the first free index among devices with the **same source and name**,
  in the order they were added (`ControllerInterface::AddDevice`). Two identical
  pads are `SDL/0/<name>` and `SDL/1/<name>`.
- `name`: `SDL_GetGamepadName()`. When Steam launched the process and set
  `SteamVirtualGamepadInfo`, SDL names each Steam virtual pad after the physical
  controller Steam reports (SDL `SDL_UpdateJoystickNameForID`). EmuDeck ships
  `SDL/0/Steam Deck Controller` and `SDL/1/Steam Deck Controller`. Without
  that info, SDL's gamepad DB names the virtual pad `Steam Virtual Gamepad`
  (GUID `03000000de280000ff11000001000000`).
- Native, no Steam: the Deck's own pad through SDL HIDAPI is `Steam Deck`; a
  DualShock 4 is SDL's name for it (e.g. `PS4 Controller`) **[VERIFY]** names on
  device for each controller in spike S8.

## Input naming table (SDL backend)

| Canonical | Dolphin token (2407+) | Legacy token (still accepted) | Notes |
|-----------|-----------------------|-------------------------------|-------|
| `face_south` | `Button S` | `Button A`, `Button 0` | positional |
| `face_east` | `Button E` | `Button B`, `Button 1` | |
| `face_west` | `Button W` | `Button X`, `Button 2` | |
| `face_north` | `Button N` | `Button Y`, `Button 3` | |
| `dpad_up/down/left/right` | `Pad N` / `Pad S` / `Pad W` / `Pad E` | `Hat 0 N` … | |
| `l1` / `r1` | `Shoulder L` / `Shoulder R` | | |
| `l2` / `r2` | `Trigger L` / `Trigger R` | | analog 0..1 |
| `ls_up` / `ls_down` | `Left Y+` / `Left Y-` | `Axis 1-` / `Axis 1+` | **Dolphin flips Y**: `+` is up |
| `ls_left` / `ls_right` | `Left X-` / `Left X+` | `Axis 0-` / `Axis 0+` | |
| `rs_up` / `rs_down` | `Right Y+` / `Right Y-` | depends on the device mapping | |
| `rs_left` / `rs_right` | `Right X-` / `Right X+` | | |
| `l3` / `r3` | `Thumb L` / `Thumb R` | | |
| `start` / `select` / `guide` | `Start` / `Back` / `Guide` | | |
| `misc1` | `Misc 1` | | `Misc 2`..`Misc 6` exist from 2609 |
| `paddle1`..`paddle4` | `Paddle 1`..`Paddle 4` | | SDL order: 1 = right upper (Deck R4), 2 = left upper (L4), 3 = right lower (R5), 4 = left lower (L5) |
| `touchpad_click` | `Touchpad` | | |
| `touchpad` | `Touchpad X-/X+`, `Touchpad Y-/Y+` | | extra pads: `Touchpad 1 X-` … |
| `gyro` | `Gyro Pitch Up/Down`, `Gyro Roll Left/Right`, `Gyro Yaw Left/Right` | | also `Gyro L …`, `Gyro R …` (Joy-Con) |
| `accel` | `Accel Up/Down/Left/Right/Forward/Backward` | | |
| `trackpad_*`, `qam` | none | | Steam owns them |

Rumble outputs: `Motor` (both motors), `Motor L` (low frequency), `Motor R`
(high frequency) from 2503, `Trigger L`/`Trigger R` trigger rumble from 2503,
and SDL haptic effects `Constant`, `Ramp`, `Sine`, `Triangle`, `Sawtooth Up`,
`Sawtooth Down`, `Strong`, `Weak`.

### Version history of SDL names

| Range | Names |
|-------|-------|
| Before commit `51e05f468a` (2023-08-03, "SDL: Add GameController API") | Raw joystick: `Button <n>`, `Axis <n>+/-`, `Hat <n> N/E/S/W`, `Motor` |
| `51e05f468a` to now (first git-tagged release 2407; Dolphin did not tag releases in git before 2407) | Gamepad names in the table above |
| 2509 | SDL3 (`6da3f5f26a`). Names unchanged. |
| 2609 | `Misc 2`..`Misc 6` added |

Current Dolphin still accepts the legacy names. It adds raw joystick axes as
hidden inputs, and `Button::IsMatchingName` matches `Button <n>` and the
XInput-style `Button A/B/X/Y` positionally. So one naming table works for every
version we care about. Write the current names, and read both.

### Dolphin's own Steam Deck backend

Dolphin also reads the Deck's built-in controls directly through hidraw
(`ControllerInterface/SteamDeck`, since commit `c5d2ad99d2`, 2023-04). Built
when hidapi is available, which Dolphin bundles in `Externals/`. Device
`SteamDeck/0/Steam Deck`. This is the only backend in these three emulators that
exposes the trackpads, L4/L5/R4/R5 and the Deck gyro while Steam Input is on
**[VERIFY]** it enumerates inside the Flatpak.

| Canonical | Token | Canonical | Token |
|-----------|-------|-----------|-------|
| `face_south/east/west/north` | `A` `B` `X` `Y` | `dpad_*` | `D-Pad Up/Down/Left/Right` |
| `l1` `r1` | `L1` `R1` | `l2` `r2` (analog) | `L2` `R2` (`L2 Full Pull` digital) |
| `ls_up/down/left/right` | `Left Stick Y+` / `Y-` / `X-` / `X+` | `rs_*` | `Right Stick …` |
| `l3` `r3` | `L3` `R3` | `start` `select` `guide` `qam` | `Menu` `View` `Steam` `Quick Access` |
| `paddle1..4` | `R4` `L4` `R5` `L5` | `trackpad_l/r_click` | `Left/Right Trackpad Click` |
| `trackpad_l/r` | `Left Trackpad X-/X+/Y-/Y+` … | `gyro` / `accel` | same names as SDL (`Gyro Pitch Up` …) |

Also `Left/Right Trackpad Touch`, `… Pressure`, `Left/Right Stick Touch`, `… Capacitance`.

## Console target table

### GameCube (`GCPadNew.ini`, `[GCPad<n>]`)

| Canonical target | Key |
|------------------|-----|
| `gc.standard.a` `b` `x` `y` `z` `start` | `Buttons/A` `Buttons/B` `Buttons/X` `Buttons/Y` `Buttons/Z` `Buttons/Start` |
| `gc.standard.up` `down` `left` `right` | `D-Pad/Up` `D-Pad/Down` `D-Pad/Left` `D-Pad/Right` |
| `gc.standard.main_x` | `Main Stick/Left` (neg), `Main Stick/Right` (pos) |
| `gc.standard.main_y` | `Main Stick/Up` (neg), `Main Stick/Down` (pos) |
| `gc.standard.c_x` / `c_y` | `C-Stick/Left`/`Right`, `C-Stick/Up`/`Down` |
| `gc.standard.l_digital` / `r_digital` | `Triggers/L` / `Triggers/R` |
| `gc.standard.l_analog` / `r_analog` | `Triggers/L-Analog` / `Triggers/R-Analog` |
| (rumble option) | `Rumble/Motor` |

Other keys in the section: `Main Stick/Modifier`, `C-Stick/Modifier`,
`Triforce/Test|Service|Coin`, `Microphone/Button`, `Options/Always Connected`.

### Wii (`WiimoteNew.ini`, `[Wiimote<n>]`)

| Canonical target | Key |
|------------------|-----|
| `wii.wiimote.a` `b` `one` `two` `minus` `plus` `home` | `Buttons/A` `Buttons/B` `Buttons/1` `Buttons/2` `Buttons/-` `Buttons/+` `Buttons/Home` |
| `wii.wiimote.up` … `right` | `D-Pad/Up` … `D-Pad/Right` |
| `wii.wiimote.shake` | `Shake/X`, `Shake/Y`, `Shake/Z` (same source on all three) |
| `wii.wiimote.ir_x` / `ir_y` | `IR/Left`/`IR/Right`, `IR/Up`/`IR/Down` (also `IR/Hide`, `IR/Recenter`) |
| `wii.wiimote.tilt` | stick source: `Tilt/Forward` `Backward` `Left` `Right`; accel source: `IMUAccelerometer/Up` … `Backward` = `` `Accel Up` `` … |
| `wii.wiimote_nunchuk.*` | all Wiimote keys above, plus: |
| `wii.wiimote_nunchuk.c` / `z` | `Nunchuk/Buttons/C` / `Nunchuk/Buttons/Z` |
| `wii.wiimote_nunchuk.nunchuk_x` / `nunchuk_y` | `Nunchuk/Stick/Left`/`Right`, `Nunchuk/Stick/Up`/`Down` |
| `wii.wiimote_nunchuk.nunchuk_shake` | `Nunchuk/Shake/X`, `/Y`, `/Z` |
| `wii.classic.a` `b` `x` `y` `zl` `zr` `minus` `plus` `home` | `Classic/Buttons/A` … `Classic/Buttons/ZL` `ZR` `-` `+` `Home` |
| `wii.classic.up` … `right` | `Classic/D-Pad/Up` … |
| `wii.classic.l_digital` / `r_digital` | `Classic/Triggers/L` / `Classic/Triggers/R` |
| `wii.classic.l_analog` / `r_analog` | `Classic/Triggers/L-Analog` / `Classic/Triggers/R-Analog` |
| `wii.classic.lstick_*` / `rstick_*` | `Classic/Left Stick/Up|Down|Left|Right`, `Classic/Right Stick/…` |
| gyro (option) | `IMUGyroscope/Pitch Up` … `Yaw Right` = `` `Gyro Pitch Up` `` … |

Extension keys are `<Extension name>/<group>/<control>` (`Attachments::SaveConfig`).
Every extension's keys are saved at once, whichever one is selected.

## Controller type keys

| What | File / key | Values |
|------|-----------|--------|
| GC port device | `Dolphin.ini` `[Core] SIDevice0`..`SIDevice3` | `0` none, `1` N64 mic, `2` N64 keyboard, `3` N64 mouse, `4` N64 controller, `5` GBA (link), `6` **standard controller**, `7` keyboard, `8` steering wheel, `9` dance mat, `10` Taru Konga, `11` AM baseboard, `12` **GC adapter for Wii U**, `13` GBA (emulated). Defaults: `SIDevice0 = 6`, others `0`. |
| Wiimote source | `WiimoteNew.ini` `[Wiimote<n>] Source` | `0` none, `1` emulated, `2` real. Defaults: Wiimote1 `1`, others `0`. `[BalanceBoard] Source` likewise. |
| Wii extension | `WiimoteNew.ini` `[Wiimote<n>] Extension` | `None` (wii.wiimote), `Nunchuk` (wii.wiimote_nunchuk), `Classic` (wii.classic); also `Guitar`, `Drums`, `Turntable`, `uDraw`, `Drawsome`, `TaTaCon`, `Shinkansen`. Default `None`. |
| MotionPlus | `Extension/Attach MotionPlus` | `True` (default) / `False` |

## Managed keys

- `GCPadNew.ini` `[GCPad<n>]`: `Device`, `Buttons/*`, `D-Pad/*`, `Main Stick/Up|Down|Left|Right|Modifier`, `C-Stick/Up|Down|Left|Right|Modifier`, `Triggers/L|R|L-Analog|R-Analog`, `Rumble/Motor`. Option keys only when an options rule sets them: `Main Stick/Dead Zone`, `C-Stick/Dead Zone`, `Triggers/Dead Zone`, `Triggers/Threshold`.
- `WiimoteNew.ini` `[Wiimote<n>]`: `Device`, `Source`, `Extension`, `Buttons/*`, `D-Pad/*`, `IR/*`, `Shake/*`, `Tilt/*`, `IMUAccelerometer/*`, `IMUGyroscope/*`, `Nunchuk/Buttons/*`, `Nunchuk/Stick/*`, `Nunchuk/Shake/*`, `Classic/*`, `Rumble/Motor`.
- `Dolphin.ini` `[Core] SIDevice0..3` only with `options.controller_type`.
- `Hotkeys.ini` `[Hotkeys]` `Device` and hotkey keys, only with hotkey rules.
- Never: `Calibration`, `Center`, `Range` keys (user calibration), unless an options rule sets them.

## Hotkeys

`Hotkeys.ini`, section `[Hotkeys]`, `Device = …` plus `<group>/<label>` keys
(`HotkeyManager.cpp` `s_groups_info` and `s_hotkey_labels`).

| Canonical | Key |
|-----------|-----|
| `hotkey.save_state` | `Save State/Save to Selected Slot` |
| `hotkey.load_state` | `Load State/Load from Selected Slot` |
| `hotkey.next_slot` / `prev_slot` | `Other State Hotkeys/Increase Selected State Slot` / `Decrease Selected State Slot` |
| `hotkey.pause` | `General/Toggle Pause` |
| `hotkey.exit` | `General/Exit` (`General/Stop` stops emulation only) |
| `hotkey.toggle_fullscreen` | `General/Toggle Fullscreen` |
| `hotkey.screenshot` | `General/Take Screenshot` |
| `hotkey.fast_forward` | `Emulation Speed/Disable Emulation Speed Limit` |
| `hotkey.menu`, `hotkey.rewind` | none in Dolphin |

EmuDeck's hotkey combos: spike S7.

## Options support

| Option | Key | Notes |
|--------|-----|-------|
| Rumble on/off | `Rumble/Motor` = `` `Motor` `` or empty | per `[GCPad<n>]`/`[Wiimote<n>]` |
| Stick dead zone | `Main Stick/Dead Zone`, `C-Stick/Dead Zone`, `Nunchuk/Stick/Dead Zone`, `Classic/Left Stick/Dead Zone` | percent, 0..50, default 0 |
| Trigger dead zone / threshold | `Triggers/Dead Zone` (0..25), `Triggers/Threshold` (1..100, default 90) | |
| Gyro | `IMUGyroscope/*`, `IMUGyroscope/Dead Zone` | Wii only |
| Controller type | see above | |
| SDL hints | `Dolphin.ini` `[SDL_Hints]` | applied at startup (2603+) |

## Game id

6-character game ID (`GALE01`). Per-game INIs use it as the file name.

1. **`dolphin-tool header -j -i <file>`** prints JSON with `game_id`,
   `internal_name`, `revision`, `title_id`, `region`, `country`, and for
   GCZ/WIA/RVZ `block_size`, `compression_method`, `compression_level`. It reads
   every format Dolphin reads. It is built by default (`ENABLE_CLI_TOOL=ON`),
   and the Flathub manifest does not turn it off, so the Flatpak should have
   `/app/bin/dolphin-tool`: `flatpak run --command=dolphin-tool org.DolphinEmu.dolphin-emu header -j -i <file>`
   **[VERIFY]** on device.
2. **Header bytes**, no tool needed:
   - ISO/GCM: bytes `0x00`–`0x05`.
   - WIA/RVZ: magic `WIA\x01` / `RVZ\x01` at 0; the disc header copy starts at
     `0x58` (`WIAHeader1` is 0x48 bytes, then four u32 fields in `WIAHeader2`), so
     the ID is bytes `0x58`–`0x5D`.
   - GCZ (magic `0xB10BC001`, little endian): blocks are deflate-compressed; use the tool.
3. **Game list cache** `<cache root>/gamelist.cache`: a `PointerWrap` dump
   (revision 27) of `std::map`s and structs. It is not a stable format, so don't parse it.

Revision matters too: Dolphin also loads `<ID>r<revision>.ini` (see below).

## Per-game override detection

For the running game Dolphin merges, from both `Sys/GameSettings/` and the user
`GameSettings/` dir, `<ID[0]>.ini`, `<ID[0:3]>.ini`, `<ID>.ini` and
`<ID>r<rev>.ini` (`GetGameIniFilenames`). If `[Controls]` has
`PadProfile1`..`PadProfile4` (GC) or `WiimoteProfile1`..`WiimoteProfile4`
(Wii), Dolphin loads `Profiles/GCPad/<value>.ini` or `Profiles/Wiimote/<value>.ini`
(section `[Profile]`) **instead of** that slot's global section
(`InputConfig::LoadConfig`). The value can be a comma-separated list or a
directory; the first match wins. Our global write is then ignored for that slot.
`read()` must check all four user files, report the override, and offer to
import the profile as a game rule or remove the pointer.

## Save behaviour

- On startup, `MainWindow::InitControllers` loads and immediately re-saves
  `WiimoteNew.ini`, `GCPadNew.ini`, `GBA.ini`, `GCKeyNew.ini` and FreeLook input.
  Key order and float formatting change, and default-valued keys are deleted.
  Drift detection must compare parsed values, not bytes.
- The mapping windows save on change.
- `Config::Save()` on exit writes `Dolphin.ini` and the other Config-system
  files, including `[Wiimote<n>] Source`. We write before launch, so this only
  matters for drift detection.

## Known pitfalls

- `Left Y+` means stick **up** (Dolphin flips SDL's Y axis to match XInput).
  PCSX2/DuckStation use `-LeftY` for up.
- EmuDeck uses legacy `Axis n±` tokens for sticks and maps GC A to `Button E`
  (east). This doesn't match `data/layouts/gc.json`'s draft `a = face_south`. Spike S7.
- `id` in `SDL/<id>/<name>` counts only same-named devices. With Steam Input
  every virtual pad can carry a different physical name, so `SDL/0/…` is often
  correct for every player. The device name must be resolved at launch.
- Expressions can be arbitrarily complex. `read()` parses single-input and
  `|`-joined expressions and keeps anything else opaque ("custom expression, preserved").
- Real Wiimote passthrough (`Source = 2`) and the GC adapter (`SIDevice = 12`)
  bypass our bindings. Report them, don't fight them.

## Sources

Dolphin, master `2c805fee8f232d090c454381bb1b8422242345e1`
(`https://github.com/dolphin-emu/dolphin/blob/2c805fee8f232d090c454381bb1b8422242345e1/<path>`):

- SDL names: `Source/Core/InputCommon/ControllerInterface/SDL/SDLGamepad.h` L388–439 (`s_sdl_button_names`, `s_sdl_axis_names`, motion axes); `SDLGamepad.cpp` L22–143 (inputs, rumble, touchpad, sensors), L281–337 (`Axis::GetName` Y flip, `Button::IsMatchingName` legacy matching)
- Device string: `Source/Core/InputCommon/ControllerInterface/CoreDevice.cpp` L190–218; id assignment `ControllerInterface.cpp` L249–270
- Expressions: `Source/Core/InputCommon/ControllerInterface/MappingCommon.cpp` L34–142; `Source/Core/InputCommon/ControlReference/ExpressionParser.cpp` L193–255, L865–877
- Key layout: `Source/Core/InputCommon/ControllerEmu/ControlGroup/ControlGroup.cpp` L22–105; `ControllerEmu.cpp` L113–137; `ControlGroup/Attachments.cpp` L53–95; `ControlGroup/MixedTriggers.cpp` L18–30; `StickGate.cpp` L21–26, L132
- GC pad: `Source/Core/Core/HW/GCPadEmu.h` L57–86; `GCPadEmu.cpp` L39–98; `GCPad.cpp` L14 (`GCPadNew`, profile dir `GCPad`, key `Pad`)
- Wii: `Source/Core/Core/HW/Wiimote.cpp` L100; `Wiimote.h` L45–52; `WiimoteEmu/WiimoteEmu.cpp` L213–310; `WiimoteEmu/Extension/Nunchuk.cpp` L32–57; `Extension/Classic.h` L221–244; `Config/WiimoteSettings.cpp` L10–19
- Port devices: `Source/Core/Core/Config/MainSettings.cpp` L168–181; `Source/Core/Core/HW/SI/SI_Device.h` L88–106
- Hotkeys: `Source/Core/Core/HotkeyManager.cpp` L22–211, L295–328
- Profiles and per-game: `Source/Core/InputCommon/InputConfig.cpp` L31–153; `InputProfile.cpp` L30–54; `Source/Core/Core/ConfigLoaders/GameConfigLoader.cpp` L33–58; `Source/Core/Core/ConfigManager.cpp` L561–580
- Paths: `Source/Core/UICommon/UICommon.cpp` L401–482; `Source/Core/Common/FileUtil.cpp` L843–850, L924–936; `Source/Core/Common/CommonPaths.h` L15–105
- Saving: `Source/Core/DolphinQt/MainWindow.cpp` L369, L377–403; `Source/Core/Common/IniFile.h` L25–45, L64
- Game id: `Source/Core/DolphinTool/HeaderCommand.cpp` L22–170; `Source/Core/DiscIO/WIABlob.h` L40–119; `Source/Core/DiscIO/VolumeDisc.cpp` L19–58; `Source/Core/UICommon/GameFileCache.cpp` L26–39; `Source/Core/UICommon/GameFile.cpp` L291–331; `CMakeLists.txt` L97
- Steam Deck backend: `Source/Core/InputCommon/ControllerInterface/SteamDeck/SteamDeck.cpp` L15, L141–273; build condition `Source/Core/InputCommon/CMakeLists.txt` L190–198; `CMakeLists.txt` L724
- Shipped profile: `Data/Sys/Profiles/GCPad/SDL Gamepad.ini`
- History: commits `51e05f468a` (GameController names), `6da3f5f26a` (SDL3), `fb512adc5f` (Motor L/R), `b572e4ca5a` (Misc 2–6), via `gh api repos/dolphin-emu/dolphin/compare/<sha>...<tag>`

Other:

- Flathub manifest: https://github.com/flathub/org.DolphinEmu.dolphin-emu/blob/e4c2d7d2ebeff8dc4d79b614c1dced3011b47126/org.DolphinEmu.dolphin-emu.yml
- SDL Steam virtual pad naming: https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/src/joystick/SDL_joystick.c#L1019-L1040, `src/joystick/SDL_gamepad.c` L3883–3900, `src/joystick/SDL_gamepad_db.h` L741, `src/joystick/hidapi/SDL_hidapi_steamdeck.c` L348, `include/SDL3/SDL_gamepad.h` L171–175 (paddle order)
- EmuDeck: https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/EmuScripts/emuDeckDolphin.sh#L4-L6 and `configs/org.DolphinEmu.dolphin-emu/config/dolphin-emu/GCPadNew.ini`
