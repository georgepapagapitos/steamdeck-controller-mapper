# Adapter: DuckStation

> Facts below were read from DuckStation source at master `b3d57a7f47`
> (2026-10-22; the rolling `latest` release is from 2026-10-13) unless a version
> is given. Links are in [Sources](#sources). Machine-readable tables:
> [`data/adapters/duckstation.json`](../../data/adapters/duckstation.json).

## Summary

| Field | Value |
|-------|-------|
| Adapter id | `duckstation` |
| Systems | `psx` |
| EmuDeck install type | AppImage `$emusFolder/DuckStation.AppImage`, config `~/.local/share/duckstation/settings.ini`. EmuDeck migrates old Flatpak `org.duckstation.DuckStation` installs to the AppImage (`emuDeckDuckStation.sh`). |
| Versions covered | SDL3 builds (commit `4e97420b3b`, 2025-01-24; every tag from v0.1-10339) to `latest`/master |
| Priority | **P0** |
| Strategy | global-swap of `[PadN]` in `settings.ini`, plus profile-select enhancement |
| Shares base with | PCSX2 (`ini_sdl_family`), with different face-button and paddle tokens |

## Paths

`Core::SetDataRoot`: portable first, then `$XDG_CONFIG_HOME/duckstation` if
`XDG_CONFIG_HOME` is set and absolute, else `~/.local/share/duckstation`.

| What | AppImage / native (EmuDeck) | Flatpak (old installs) |
|------|-----------------------------|------------------------|
| Data root | `~/.local/share/duckstation/` | `~/.var/app/org.duckstation.DuckStation/config/duckstation/` |
| Main | `settings.ini` | same relative |
| Input profiles | `inputprofiles/<name>.ini` | same relative |
| Per-game | `gamesettings/<SERIAL>.ini` | same relative |
| Game list cache | `cache/gamelist.cache` | same relative |

- If `XDG_CONFIG_HOME` is set when DuckStation starts, the AppImage uses
  `$XDG_CONFIG_HOME/duckstation/` instead. SteamOS Game Mode normally leaves it
  unset **[VERIFY]**. The path provider must mirror this rule.
- Portable: `portable.txt` **or** `settings.ini` in the AppImage's directory
  (DuckStation checks `$APPIMAGE`'s directory, not the mount) makes that
  directory the data root.
- `[Folders] GameSettings|InputProfiles|Cache` can relocate those directories.

## Format

INI. As in PCSX2, a repeated key adds another binding, and ` & ` joins a chord.

Real excerpt, EmuDeck's shipped `settings.ini`:

```ini
[ControllerPorts]
ControllerSettingsMigrated = true
MultitapMode = Disabled

[InputSources]
SDL = true
SDLControllerEnhancedMode = false

[Pad1]
Type = AnalogController
Up = SDL-0/DPadUp
Triangle = SDL-0/Y
Circle = SDL-0/B
Cross = SDL-0/A
Square = SDL-0/X
Select = SDL-0/Back
Start = SDL-0/Start
L1 = SDL-0/LeftShoulder
L2 = SDL-0/+LeftTrigger
Analog = Keyboard/F6
LLeft = SDL-0/-LeftX
LUp = SDL-0/-LeftY
SmallMotor = SDL-0/SmallMotor
LargeMotor = SDL-0/LargeMotor

[Hotkeys]
TogglePause = SDL-0/Back & SDL-0/A
LoadSelectedSaveState = Keyboard/F8
LoadSelectedSaveState = SDL-0/Back & SDL-0/LeftShoulder
```

Binding syntax (`SDLInputSource::ParseKeyString` / `ConvertKeyToString`):

| Need | Syntax |
|------|--------|
| Button | `SDL-0/A` |
| Half-axis | `SDL-0/+LeftTrigger`, `SDL-0/-LeftY`, `SDL-0/-LeftY~` (inverted) |
| Raw joystick | `SDL-0/Button12`, `SDL-0/+Axis6`, `SDL-0/FullAxis6`, `SDL-0/Hat0North` |
| Motion (accelerometer) | `SDL-0/+Turn`, `SDL-0/-Turn` (roll), `SDL-0/+Tilt`, `SDL-0/-Tilt` (pitch) |
| Motors / LEDs | `SDL-0/LargeMotor`, `SDL-0/SmallMotor`, `SDL-0/Haptic`, `SDL-0/RGBLED`, `SDL-0/MuteLED` |
| Chord | `SDL-0/Back & SDL-0/Start` |
| Several bindings | repeat the key |
| Per-binding scale/deadzone | `<Key>Scale`, `<Key>Deadzone` |

## Device references

- `SDL-<n>`: SDL player index, else the first free index (same as PCSX2).
- **Persistent identifiers** (commit `edd41dff15`, 2026-09-25; in the 2026-10-13
  `latest` release): with `[InputSources] SDLUsePersistentDeviceIdentifiers`
  (default `true`), DuckStation saves bindings as `SDL-<SDL GUID>-<serial>`
  when the pad reports a serial made of `[A-Za-z0-9-]`, or `SDL-SB-<GUID>-<hex serial>`
  otherwise. A numeric `SDL-<n>` is still accepted on load, so we can keep
  writing numbers. But `read()` must parse persistent ids. If the named pad is
  absent, those bindings do nothing. Steam virtual pads probably have no serial
  and stay numeric **[VERIFY]**.
- `[InputSources] SDLControllerEnhancedMode` defaults to `false` here
  (PCSX2: `true`).

## Input naming table (SDL backend)

DuckStation **does not** use PCSX2's `FaceSouth` names. Its config tokens are
positional but spelled `A/B/X/Y` (`s_button_info`; the PlayStation glyph names
like `Cross` are UI labels only).

| Canonical | DuckStation token | Legacy (SDL2 builds) |
|-----------|-------------------|----------------------|
| `face_south` / `face_east` / `face_west` / `face_north` | `A` / `B` / `X` / `Y` | same |
| `dpad_up/down/left/right` | `DPadUp` `DPadDown` `DPadLeft` `DPadRight` | same |
| `l1` / `r1` | `LeftShoulder` / `RightShoulder` | same |
| `l2` / `r2` | `+LeftTrigger` / `+RightTrigger` | same |
| `ls_up/down/left/right` | `-LeftY` / `+LeftY` / `-LeftX` / `+LeftX` | same |
| `rs_*` | `-RightY` / `+RightY` / `-RightX` / `+RightX` | same |
| `l3` / `r3` | `LeftStick` / `RightStick` | same |
| `start` / `select` / `guide` | `Start` / `Back` / `Guide` | same |
| `misc1` | `Misc1` (`Misc2`..`Misc6` too) | `Misc1` |
| `paddle1` / `paddle2` / `paddle3` / `paddle4` | `RightPaddle1` / `LeftPaddle1` / `RightPaddle2` / `LeftPaddle2` | `Paddle1`..`Paddle4` |
| `touchpad_click` | `Touchpad` | same |
| `accel` | `±Turn` (roll), `±Tilt` (pitch) **[VERIFY]** sign | |
| `touchpad`, `gyro`, `trackpad_*`, `qam` | none | |

## Console target table (`[Pad<n>]`)

| Canonical target | Key |
|------------------|-----|
| `psx.dualshock.cross` `circle` `square` `triangle` | `Cross` `Circle` `Square` `Triangle` |
| `psx.dualshock.l1` `r1` `l2` `r2` `l3` `r3` | `L1` `R1` `L2` `R2` `L3` `R3` |
| `psx.dualshock.select` `start` `analog` | `Select` `Start` `Analog` |
| `psx.dualshock.up` … `right` | `Up` `Down` `Left` `Right` |
| `psx.dualshock.lstick_x` / `lstick_y` | `LLeft`/`LRight`, `LUp`/`LDown` |
| `psx.dualshock.rstick_x` / `rstick_y` | `RLeft`/`RRight`, `RUp`/`RDown` |
| `psx.digital.*` | same keys minus `L3`, `R3`, `Analog` and the sticks (`Type = DigitalController`) |
| options.rumble | `LargeMotor`, `SmallMotor`; strength `LargeMotorVibrationBias`, `SmallMotorVibrationBias` (-255..255, default 8) |
| options.deadzone | `AnalogDeadzone` (0..1, default 0), `ButtonDeadzone` (0.01..1, default 0.25) |
| options sensitivity | `AnalogSensitivity` (0.01..2, default 1.33) |
| options invert | `InvertLeftStick`, `InvertRightStick` (0 none, 1 X, 2 Y, 3 both) |
| analog mode | `ForceAnalogOnReset` (default `true`), `AnalogDPadInDigitalMode` (default `true`) |

Other AnalogController keys: `DisableSOCD`, `AnalogShoulderButtons`, `AnalogTriggerButtons`.

## Controller types and multitap

| What | Key | Values |
|------|-----|--------|
| Pad type | `[Pad<n>] Type` | `AnalogController` (psx.dualshock), `DigitalController` (psx.digital), `None`; also `AnalogJoystick`, `GunCon`, `PlayStationMouse`, `NeGcon`, `NeGconRumble`, `Justifier`, `PopnController`, `DDGoController`, `JogCon`. Defaults: Pad1 `AnalogController`, Pad2 `None`. |
| Multitap | `[ControllerPorts] MultitapMode` | `Disabled` (default), `Port1Only`, `Port2Only`, `BothPorts` |
| Pad numbering | `Pad1` = 1A, `Pad2` = 2A, `Pad3`–`Pad5` = 1B–1D, `Pad6`–`Pad8` = 2B–2D (`Controller::ConvertPadToPortAndSlot`) | |

## Managed keys

- `[Pad<n>]` binding keys for resolved players; `Type` only with
  `options.controller_type`; `AnalogDeadzone`, `ButtonDeadzone`,
  `AnalogSensitivity`, `ForceAnalogOnReset`, the vibration bias keys only with options rules.
- `[ControllerPorts] MultitapMode` only when a rule asks for more than 2 players.
- `[Hotkeys]` keys with hotkey rules.
- Never touch `[Main] SettingsVersion` / `SetupWizardIncomplete` or `[Folders]`.

## Hotkeys

Section `[Hotkeys]`, same binding syntax (`core/hotkeys.cpp`).

| Canonical | Key |
|-----------|-----|
| `hotkey.save_state` / `load_state` | `SaveSelectedSaveState` / `LoadSelectedSaveState` |
| `hotkey.next_slot` / `prev_slot` | `SelectNextSaveStateSlot` / `SelectPreviousSaveStateSlot` |
| `hotkey.menu` | `OpenPauseMenu` (`TogglePauseMenu` too) |
| `hotkey.exit` | `PowerOff` |
| `hotkey.pause` | `TogglePause` |
| `hotkey.fast_forward` | `FastForward` (hold) / `ToggleFastForward` |
| `hotkey.rewind` | `Rewind` (needs `[Main] RewindEnable = true`) |
| `hotkey.toggle_fullscreen` | `ToggleFullscreen` |
| `hotkey.screenshot` | `Screenshot` |

## Game id

Serial (`SLUS-00594`). Per-game file: `gamesettings/<SanitizeFileName(serial)>.ini`.
For multi-disc sets in DuckStation's database, the serial of the **first disc**
is used (`System::GetGameSettingsPath`).

1. **Game list cache** `cache/gamelist.cache` (`GameList.cpp`). Little endian:
   - header: `u32 signature = 0x45434C48`, `u32 version = 41`
   - entries until EOF: `u8 type`, `u8 region`, `str path`, `str serial`,
     `str title`, `u64 hash`, `s64 file_size`, `u64 uncompressed_size`,
     `u64 last_modified_time`, `s8 disc_set_index`, `u8[16] achievements_hash`
   - `str` = `u32 length` + bytes.
   - Later entries for the same path win. DuckStation holds the file locked
     while it scans; read it before launch.
2. **SYSTEM.CNF** for BIN/CUE/ISO: `BOOT = cdrom:\SLUS_005.94;1` → `SLUS-00594`.
   For CHD, use the cache.
3. Filename heuristics are a weak last resort: Redump-style names don't include serials.

The cache doesn't hold the disc-set mapping. To find the first-disc serial for a
multi-disc game we would need DuckStation's game database **[VERIFY]**
(`GameDatabase::GetEntryForSerial`).

## Per-game override detection

Exactly one controller layer is used (`System::GetControllerSettingsLayer`):

1. **Input profile**: game INI `[ControllerPorts] InputProfileName = <name>` →
   `inputprofiles/<name>.ini`.
2. Otherwise the **game INI itself**, but only if it has
   `[ControllerPorts] UseGameSettingsForController = true`. Then its own
   `[PadN]`/`[ControllerPorts]` are used, and `InputProfileName` is ignored.
3. Otherwise base `settings.ini`.

Hotkeys come from the base file unless the chosen layer sets
`[ControllerPorts] UseProfileHotkeyBindings = true`. Input-source settings
likewise need `UseProfileInputSources = true`. Cases 1 and 2 shadow our
global-swap. `read()` reports them and offers import.

## Save behaviour

- Any settings change starts a 1-second single-shot timer
  (`SETTINGS_SAVE_DELAY = 1000`), then `QtHost::SaveSettings` rewrites `settings.ini`.
- A pending save is flushed at shutdown.
- So: write only while DuckStation is not running. Drift detection compares parsed values.

## Known pitfalls

- Index-based `SDL-<n>` refs, as in PCSX2. Persistent ids appear as soon as the
  user rebinds anything in a 2026-10+ build.
- Don't share the PCSX2 face-button table: DuckStation writes `A`, PCSX2 writes `FaceSouth`.
- Paddle names changed with SDL3 (`Paddle1` → `RightPaddle1`); current builds
  don't parse the old names.
- EmuDeck binds `Analog` to `Keyboard/F6`, not a pad button. Leave it unless a
  rule targets `psx.dualshock.analog`.
- Upstream licensing and distribution changes affect how EmuDeck installs it.
  The path provider must handle AppImage, old Flatpak and portable.

## Sources

DuckStation, master `b3d57a7f47a4b22a1f6ed3b22c6821ffe0a396d8`
(`https://github.com/stenzek/duckstation/blob/b3d57a7f47a4b22a1f6ed3b22c6821ffe0a396d8/<path>`):

- SDL tokens: `src/util/sdl_input_source.cpp` L56–63 (`s_axis_info`), L81–107 (`s_button_info`), L143–162 (hats, LEDs, sensors), L306–347 (persistent ids), L399–432 (`[InputSources]` keys), L700–860 (`ParseKeyString`), L862–932 (`ConvertKeyToString`), L1160–1250 (player index, GUID)
- Bindings: `src/util/input_manager.cpp` L250–270 (`SplitChord`), L895–930 (`GetStringList`, `<Key>Scale`/`<Key>Deadzone`)
- Pads: `src/core/analog_controller.cpp` L765–880; `src/core/digital_controller.cpp` L160–235; `src/core/controller.cpp` L24–45, L135–196; `src/core/settings.h` L634–635
- Sections and multitap: `src/core/settings.cpp` L160–182, L2775–2805
- Paths: `src/core/core.cpp` L140–262; `src/core/settings.cpp` L2980–3022
- Per-game and profiles: `src/core/system.cpp` L1105–1160, L1393–1404, L1505–1560
- Hotkeys: `src/core/hotkeys.cpp` L136–240, L691–716
- Game list cache: `src/core/game_list.cpp` L59–63, L746–802, L1421; `src/common/binary_reader_writer.cpp` L333–341
- Saving: `src/duckstation-qt/qthost.cpp` L108, L2190–2198, L3166–3204
- History: commits `4e97420b3b` (SDL3, 2025-01-24; SDL2 names from its parent), `edd41dff15` (persistent ids, 2026-09-25), checked with `gh api repos/stenzek/duckstation/compare/<sha>...<tag>`

Other:

- EmuDeck: https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/EmuScripts/emuDeckDuckStation.sh#L5-L34 and `configs/duckstation/settings.ini`
- SDL paddle order: https://github.com/libsdl-org/SDL/blob/8adc0f98837db84fd24f17c339e59dcf36a17156/include/SDL3/SDL_gamepad.h#L171-L175
