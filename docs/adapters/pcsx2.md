# Adapter: PCSX2 (Qt)

> Facts below were read from PCSX2 source at master `7fe1e5525a`
> (2026-10-22, after v2.9.138) unless a version is given. Links are in
> [Sources](#sources). Machine-readable tables: [`data/adapters/pcsx2.json`](../../data/adapters/pcsx2.json).

## Summary

| Field | Value |
|-------|-------|
| Adapter id | `pcsx2` |
| Systems | `ps2` |
| EmuDeck install type | AppImage `$emusFolder/pcsx2-Qt.AppImage` (downloaded from GitHub releases; stable vs nightly **[VERIFY]**), config `~/.config/PCSX2/inis/PCSX2.ini` (EmuDeck `emuDeckPCSX2QT.sh`) |
| Versions covered | v2.3.199 (SDL3; first stable v2.4.0) to v2.9.138 and master. Older SDL2 names in a legacy table. |
| Priority | **P0** |
| Strategy | global-swap of `[PadN]` sections in `PCSX2.ini`, plus profile-select enhancement (`inputprofiles/map-helper-*.ini`) |

PCSX2 (Qt) and DuckStation share their input-system design, so they should
share a base adapter class (`ini_sdl_family`). The SDL face-button tokens differ,
though (see the [DuckStation adapter](duckstation.md)).

## Paths

`EmuFolders::SetDataDirectory`: the data root is `$XDG_CONFIG_HOME/PCSX2` if
`XDG_CONFIG_HOME` is absolute, else `~/.config/PCSX2`.

| What | AppImage / native (EmuDeck) | Flatpak `net.pcsx2.PCSX2` |
|------|-----------------------------|---------------------------|
| Data root | `~/.config/PCSX2/` | `~/.var/app/net.pcsx2.PCSX2/config/PCSX2/` |
| Main | `inis/PCSX2.ini` | same relative |
| Input profiles | `inputprofiles/<name>.ini` | same relative |
| Per-game | `gamesettings/<SERIAL>_<CRC>.ini` (fallback `<CRC>.ini`) | same relative |
| Game list cache | `cache/gamelist.cache` | same relative |

- `inis/` is always under the data root. `inputprofiles`, `gamesettings` and
  `cache` can be moved by `[Folders] InputProfiles|GameSettings|Cache` in
  `PCSX2.ini` (relative to the data root unless absolute). Read them first.
- Portable: `portable.txt`/`portable.ini` next to the binary (its content is a
  sub-path), or `-portable`. For an AppImage in portable mode the data root is
  `<AppImage dir>/PCSX2/`.

## Format

INI (SimpleIni). A key can repeat: each line is one more binding for that
control (`INISettingsInterface::GetStringList`). ` & ` inside one value is a
chord: all must be held (`InputManager::SplitChord`).

Real excerpt, EmuDeck's shipped `PCSX2.ini` (Steam Input passthrough):

```ini
[UI]
SettingsVersion = 1

[InputSources]
Keyboard = true
Mouse = true
SDL = true
SDLControllerEnhancedMode = false

[Hotkeys]
ToggleFullscreen = SDL-0/Start & SDL-0/LeftStick
LoadStateFromSlot = SDL-0/Back & SDL-0/LeftShoulder
SaveStateToSlot = SDL-0/Back & SDL-0/RightShoulder
OpenPauseMenu = SDL-0/Back & SDL-0/RightStick
ShutdownVM = SDL-0/Back & SDL-0/Start

[Pad1]
Type = DualShock2
Deadzone = 0.000000
AxisScale = 1.330000
LargeMotorScale = 1.000000
SmallMotorScale = 1.000000
Up = SDL-0/DPadUp
Triangle = SDL-0/Y
Circle = SDL-0/B
Cross = SDL-0/A
Square = SDL-0/X
Select = SDL-0/Back
Start = SDL-0/Start
```

EmuDeck still ships **SDL2-era** names (`SDL-0/A`). Current PCSX2 parses
them, converts them to positional SDL3 names, and **writes the converted value
back** to the file it came from (`InputManager::AddBindings`). After one launch
the file reads `Cross = SDL-0/FaceSouth`.

Binding value syntax (`SDLInputSource::ParseKeyString` / `ConvertKeyToString`):

| Need | Syntax |
|------|--------|
| Button | `SDL-0/FaceSouth` |
| Half-axis | `SDL-0/+LeftTrigger`, `SDL-0/-LeftY` |
| Full axis | `SDL-0/FullLeftX` |
| Raw joystick | `SDL-0/JoyButton12`, `SDL-0/+JoyAxis6`, `SDL-0/-JoyAxis2~` (`~` = inverted), `SDL-0/Hat0North` |
| Motors | `SDL-0/LargeMotor`, `SDL-0/SmallMotor`, `SDL-0/Haptic` |
| Chord | `SDL-0/Back & SDL-0/Start` |
| Several bindings | repeat the key |
| Per-binding scale/deadzone | `<Key>Scale`, `<Key>Deadzone` in the same `[PadN]` |
| Unbound | delete the key |

## Device references

- `SDL-<n>`, where `n` is the **SDL player index** (`SDL_GetGamepadPlayerIndex`).
  If that is negative or already taken, PCSX2 uses the first free index
  (`SDLInputSource::OpenDevice`). Steam virtual pads report their Steam slot as
  the player index **[VERIFY]** on device (spike S1).
- No name or GUID in the binding, so slot ordering matters a lot (see [04 §5.2](../04-controller-identification.md)).
- Other sources: `Keyboard/<key>`, `Pointer-<n>/…`, `XInput-<n>`, `DInput-<n>` (Windows).
- `[InputSources] SDLControllerEnhancedMode` (default `true` for new configs,
  EmuDeck sets `false`) turns on DS4/DualSense HIDAPI extras (lightbar, rumble
  over BT). `SDLPS5PlayerLED`, `SDLRawInput` are the other SDL keys.

## Input naming table (SDL backend)

| Canonical | PCSX2 token (v2.3.199+) | Legacy token (SDL2, < v2.3.199) |
|-----------|-------------------------|---------------------------------|
| `face_south` / `face_east` / `face_west` / `face_north` | `FaceSouth` / `FaceEast` / `FaceWest` / `FaceNorth` | `A` / `B` / `X` / `Y` |
| `dpad_up/down/left/right` | `DPadUp` `DPadDown` `DPadLeft` `DPadRight` | same |
| `l1` / `r1` | `LeftShoulder` / `RightShoulder` | same |
| `l2` / `r2` | `+LeftTrigger` / `+RightTrigger` | same |
| `ls_up` / `ls_down` / `ls_left` / `ls_right` | `-LeftY` / `+LeftY` / `-LeftX` / `+LeftX` | same |
| `rs_*` | `-RightY` / `+RightY` / `-RightX` / `+RightX` | same |
| `l3` / `r3` | `LeftStick` / `RightStick` | same |
| `start` / `select` / `guide` | `Start` / `Back` / `Guide` | same |
| `misc1` | `Misc1` (`Misc2`..`Misc6` too) | `Misc1` |
| `paddle1`..`paddle4` | `Paddle1`..`Paddle4` (1 = right upper / R4, 2 = left upper / L4, 3 = R5, 4 = L5) | same |
| `touchpad_click` | `Touchpad` | same |
| `touchpad`, `gyro`, `accel` | none (PCSX2's SDL source has no sensor or touch-surface bindings) | |
| `trackpad_*`, `qam` | none | |

## Console target table (`[Pad<n>]`, `Type = DualShock2`)

| Canonical target | Key |
|------------------|-----|
| `ps2.dualshock2.cross` `circle` `square` `triangle` | `Cross` `Circle` `Square` `Triangle` |
| `ps2.dualshock2.l1` `r1` `l2` `r2` `l3` `r3` | `L1` `R1` `L2` `R2` `L3` `R3` (`L2`/`R2` are half-axis, pressure) |
| `ps2.dualshock2.select` `start` `analog` | `Select` `Start` `Analog` |
| `ps2.dualshock2.up` `down` `left` `right` | `Up` `Down` `Left` `Right` |
| `ps2.dualshock2.lstick_x` | `LLeft` (neg), `LRight` (pos) |
| `ps2.dualshock2.lstick_y` | `LUp` (neg), `LDown` (pos) |
| `ps2.dualshock2.rstick_x` / `rstick_y` | `RLeft`/`RRight`, `RUp`/`RDown` |
| (not in layout) | `Pressure` ("Apply Pressure" modifier) |
| options.rumble | `LargeMotor`, `SmallMotor` (bindings), `LargeMotorScale`, `SmallMotorScale` (0.0–2.0, default 1.0) |
| options.deadzone | `Deadzone` (stick, 0.0–1.0, default 0), `ButtonDeadzone` (0.0–1.0, default 0) |
| options sensitivity | `AxisScale` (0.01–2.0, default 1.33) |
| options invert | `InvertL`, `InvertR` (0 none, 1 X, 2 Y, 3 both) |

Other `Pad` keys: `PressureModifier` (default 0.5), `UseDiagonalScaleCorrection`,
`Macro1`..`Macro16` with `MacroNBinds`, `MacroNFrequency`, `MacroNPressure`,
`MacroNDeadzone`, `MacroNToggle`.

## Controller type and multitap

| What | Key | Values |
|------|-----|--------|
| Pad type | `[Pad<n>] Type` | `DualShock2`, `None`, `Guitar`, `Jogcon`, `NeGcon`, `Popn`. Defaults: Pad1 `DualShock2`, others `None`. |
| Multitap | `[Pad] MultitapPort1`, `[Pad] MultitapPort2` | `true`/`false`, default `false` |
| Pad numbering | `Pad1` = port 1 slot A, `Pad2` = port 2 slot A, `Pad3`–`Pad5` = 1B–1D, `Pad6`–`Pad8` = 2B–2D (`sioConvertPadToPortAndSlot`) | |

Pads 3–8 are ignored unless the matching multitap is on.

## Managed keys

- `[Pad<n>]` for resolved players: the binding keys in the target table, plus
  `Type` only with `options.controller_type`, and `Deadzone`, `ButtonDeadzone`,
  `AxisScale`, `LargeMotorScale`, `SmallMotorScale` only with options rules.
- `[Pad] MultitapPort1|2` only when a rule asks for more than 2 players.
- `[Hotkeys]` keys that have hotkey rules.
- `[InputSources] SDLControllerEnhancedMode` only in native mode with options that need it.
- Never touch `[UI] SettingsVersion` (if it is missing or not `1`, PCSX2 resets
  every setting to defaults: `VMManager::Internal::CheckSettingsVersion`) or `[Folders]`.

## Hotkeys

Section `[Hotkeys]`, same binding syntax.

| Canonical | Key |
|-----------|-----|
| `hotkey.save_state` / `load_state` | `SaveStateToSlot` / `LoadStateFromSlot` (also `SaveStateToSlot1`…, `LoadBackupStateFromSlot`) |
| `hotkey.next_slot` / `prev_slot` | `NextSaveStateSlot` / `PreviousSaveStateSlot` |
| `hotkey.menu` | `OpenPauseMenu` |
| `hotkey.exit` | `ShutdownVM` |
| `hotkey.pause` | `TogglePause` |
| `hotkey.fast_forward` | `ToggleTurbo` |
| `hotkey.fast_forward_hold` | `HoldTurbo` |
| `hotkey.toggle_fullscreen` | `ToggleFullscreen` |
| `hotkey.screenshot` | `Screenshot` |
| `hotkey.rewind` | none |

EmuDeck's combos are in the excerpt above (spike S7 for the full list).

## Game id

Per-game files are keyed on **serial + CRC** (`VMManager::GetGameSettingsPath`):
`gamesettings/<SanitizeFileName(serial)>_<CRC as %08X>.ini`, falling back to
`gamesettings/<CRC>.ini`. The CRC is that of the boot ELF, so it can't be read
cheaply from a CHD. Game-scoped rule *resolution* only needs the serial.

1. **Game list cache** `cache/gamelist.cache` (`GameList.cpp`). Little endian:
   - header: `u32 signature = 0x45434C47`, `u32 version = 34`
   - then entries until EOF: `str path`, `str serial`, `str title`,
     `str title_sort`, `str title_en`, `u8 type`, `u8 region`,
     `u64 total_size`, `u64 last_modified_time`, `u32 crc`, `u8 compatibility_rating`
   - `str` = `u32 length` + bytes, no terminator.
   - Append-only: a later entry for the same path wins. Check the version and
     fall back if it changes.
2. **SYSTEM.CNF** in an uncompressed ISO: `BOOT2 = cdrom0:\SLUS_203.12;1` →
   `SLUS-20312`. Serial only.
3. Filename heuristics (`(SLUS-20312)`).

## Per-game override detection

- `[EmuCore] InputProfileName = <name>` in the game INI loads
  `inputprofiles/<name>.ini`. While a profile is active, **all pad bindings come
  from the profile alone** (the global `[PadN]` is not consulted). Hotkeys still
  come from `PCSX2.ini` unless the profile sets `[Pad] UseProfileHotkeyBindings = true`
  (`VMManager.cpp` L680–700).
- Without a profile, settings are layered cmdline > game INI > input profile >
  base (`LayeredSettingsInterface`). A game INI holding its own `[PadN]` keys
  would shadow ours key by key.
- `read()` checks both and reports them (trace warning plus an offer to import).
- Profile files hold the same sections as `PCSX2.ini`: `[Pad]`, `[Pad1]`..`[Pad8]`,
  `[InputSources]`, `[Hotkeys]` (`Pad::CopyConfiguration`).

## Save behaviour

- Any settings change starts a single-shot timer, then the whole `PCSX2.ini` is
  rewritten from memory (`Host::CommitBaseSettingChanges` → `QtHost::SaveSettings`).
- On exit it saves again if dirty.
- The SDL2 → SDL3 binding migration rewrites keys in place on first load.
- So: write only while PCSX2 is not running. Edits made while it runs are lost
  at its next save. Drift detection compares parsed values.

## Known pitfalls

- Index-based `SDL-<n>` device refs (spike S1).
- EmuDeck's legacy `SDL-0/A` names get rewritten by PCSX2. Our `read()` must
  accept both, and our writer emits the new names for v2.3.199+.
- The SDL2 → SDL3 migration of `A/B/X/Y` reads each pad's button *labels*: on
  Nintendo-layout pads it may swap them and set `[UI] SDL2NintendoLayout = auto`.
  Writing positional names ourselves avoids this.
- `[UI] SettingsVersion` must stay `1`.

## Sources

PCSX2, master `7fe1e5525a2c219c119aa9586cee4ceae2f54ce1`
(`https://github.com/PCSX2/pcsx2/blob/7fe1e5525a2c219c119aa9586cee4ceae2f54ce1/<path>`):

- SDL tokens: `pcsx2/Input/SDLInputSource.cpp` L26–34 (`s_sdl_axis_setting_names`), L159–187 (`s_sdl_button_setting_names`), L538–545 (hats), L661–670 (`[InputSources]` keys), L797–1050 (`EnumerateDevices`, `ParseKeyString` incl. SDL2 migration), L1060–1175 (`ConvertKeyToString`), L1383–1415 (player index)
- Bindings: `pcsx2/Input/InputManager.cpp` L192–230 (`SplitChord`), L389–410, L606–660 (migration write-back), L860–1000 (`AddHotkeyBindings`, `AddPadBindings`, `<Key>Scale`/`<Key>Deadzone`, motors); `pcsx2/INISettingsInterface.cpp` L309–320
- DualShock 2: `pcsx2/SIO/Pad/PadDualshock2.cpp` L18–92
- Types and defaults: `pcsx2/SIO/Pad/Pad.cpp` L155–200, L272–279, L337–420 (`CopyConfiguration`), L503–506; `pcsx2/SIO/Pad/Pad{Guitar,Jogcon,Negcon,Popn,NotConnected}.cpp` (`ControllerInfo` names)
- Multitap: `pcsx2/Pcsx2Config.cpp` L1866–1868; `pcsx2/SIO/Sio.cpp` L36–44
- Paths: `pcsx2/Pcsx2Config.cpp` L2203–2345; `pcsx2-qt/QtHost.cpp` L1363
- Per-game and profiles: `pcsx2/VMManager.cpp` L680–700, L820–858, L982–1048; `pcsx2/LayeredSettingsInterface.h` L13–20; `pcsx2/LayeredSettingsInterface.cpp` L191–206
- Settings version: `pcsx2/VMManager.cpp` L153, L552–558
- Saving: `pcsx2-qt/QtHost.cpp` L1363–1400, L1452–1495, L2578–2581
- Hotkeys: `pcsx2/Hotkeys.cpp` L151–313; `pcsx2/GS/GS.cpp` L1224
- Game list cache: `pcsx2/GameList.cpp` L37–41, L460–560, L622–640
- SDL3 switch: commit `ac1a6d3348` ("Deps: Update to SDL3", 2025-03-02), first in tag v2.3.199; SDL2 names from its parent `pcsx2/Input/SDLInputSource.cpp`

Other:

- EmuDeck: https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/EmuScripts/emuDeckPCSX2QT.sh#L4-L6 and `configs/pcsx2qt/.config/PCSX2/inis/PCSX2.ini`
- SDL paddle order: https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/include/SDL3/SDL_gamepad.h#L171-L175
