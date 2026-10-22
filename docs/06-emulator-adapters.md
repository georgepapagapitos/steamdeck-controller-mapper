# 06 — Emulator Adapters

An adapter holds **everything** map-helper knows about one emulator. No
emulator-specific logic lives anywhere else.

## 1. Adapter contract

| Method | Purpose |
|--------|---------|
| `detect(paths)` | Find the install (Flatpak / AppImage / native / RetroDECK) and its config root. Return the version if it can be found. |
| `capabilities(install)` | Max players, per-game config support, input profile support, device reference styles (index / name / GUID), gyro support, hotkey support, supported systems and controller types. |
| `identify_game(rom)` | Map a ROM path to the game ID the emulator uses for per-game config (serial, title ID, game ID, content name). |
| `read(install)` | **Import**: parse current bindings into canonical form (best effort; unknown keys are kept as opaque). |
| `render(ctx)` | **Export**: canonical effective bindings → `PatchSet` (file → key edits / region replace / new file). |
| `managed_keys(install)` | Exactly which keys or sections we own. The writer refuses to touch anything else. |
| `per_game_strategy` | `native` (the emulator has per-game input config, so we write there), `global-swap` (we rewrite global input before each launch), or `profile-select` (we write a named profile and point per-game config at it). |
| `fixtures` | Real config files per supported version, under `tests/fixtures/<id>/<version>/`. |

### Strategy: global-swap is the baseline ([ADR-005](adr/005-global-swap-baseline.md))

We resolve and write **at every launch**, so the simplest strategy is enough
everywhere. Rewrite the emulator's *global* input sections with the resolved
bindings for this exact launch (these controllers, this game). Per-game files
aren't needed for correctness, because the next launch rewrites global again.

| Strategy | When | Why |
|----------|------|-----|
| **global-swap** (v1 baseline, every adapter) | Always | Works for every emulator. Only needs a game id to *resolve* game-scoped rules, never to *write* per-game files. |
| **profile-select** (enhancement) | Emulators with named profiles | Also writes the resolved set as a named `map-helper-*` profile, so it's visible and selectable in the emulator's UI. Useful in Desktop mode. |
| **native per-game** (enhancement) | Emulators with per-game input | Lets per-game rules also work when the emulator is launched *outside* our hook. P3. |

**Gotcha:** if the user set a per-game input override *inside the emulator*
(e.g. PCSX2 game properties → input profile), it beats our global write.
`read()` must detect existing per-game input overrides for the launched game
and report them (trace warning + UI prompt to import them as a game rule).

**Game ids are a separate problem.** Several emulators key per-game settings on
serial + CRC, and EmuDeck users often compress ROMs (CHD, RVZ), which makes
reading headers expensive. Sources, best first: (1) the emulator's own game
list cache, which maps path → serial (**[VERIFY]** format per emulator); (2) a
helper tool shipped with the emulator (`dolphin-tool header`); (3) header
parsing for uncompressed images; (4) filename heuristics (`(SLUS-20312)`,
No-Intro names). If none work, game-scoped rules are skipped with a warning.

## 2. Catalog

Systems as shipped by EmuDeck (**[VERIFY]** the current EmuDeck emulator list
and which install method each uses). Paths assume EmuDeck on SteamOS, and
**every path is [VERIFY]**.

| Emulator | Systems | Install (EmuDeck) | Input config | Format | Device ref | Per-game input | Profiles | Priority |
|----------|---------|-------------------|--------------|--------|-----------|----------------|----------|----------|
| **RetroArch** | Most 2D/retro + many cores | Flatpak `org.libretro.RetroArch` ✓[^install] | `retroarch.cfg`, `autoconfig/<driver>/*.cfg`, `config/remaps/<core>/<game>.rmp` | RA cfg | name + VID/PID (autoconfig), port | ✅ remaps per core/dir/game | ✅ (autoconfig + remaps) | **P0** |
| **Dolphin** | GC, Wii | Flatpak `org.DolphinEmu.dolphin-emu` ✓ | `GCPadNew.ini`, `WiimoteNew.ini`, `Profiles/GCPad/*.ini`, `GameSettings/<ID>.ini` | Dolphin INI (backtick exprs) | `SDL/<n>/<name>` or `evdev/<n>/<name>` | ✅ via `[Controls] PadProfile1=` | ✅ | **P0** |
| **PCSX2** | PS2 | AppImage `pcsx2-Qt.AppImage` ✓ | `inis/PCSX2.ini` `[Pad1]..`, `inis/inputprofiles/*.ini`, `gamesettings/*.ini` | INI | `SDL-<n>` | ✅ input profile per game | ✅ | **P0** |
| **DuckStation** | PS1 | AppImage `DuckStation.AppImage` ✓ | `settings.ini` `[Pad1]..`, `inputprofiles/*.ini`, `gamesettings/<serial>.ini` | INI | `SDL-<n>` | ✅ | ✅ | **P0** |
| **PPSSPP** | PSP | Flatpak `org.ppsspp.PPSSPP` ✓ | `PSP/SYSTEM/controls.ini` | INI (`device-keycode`) | device class id | ❌ (global-swap) | ❌ | P1 |
| **RPCS3** | PS3 | AppImage `rpcs3.AppImage` ✓ | `input_configs/global/Default.yml`, `input_configs/<serial>/...` | YAML | handler + device name | ✅ | ✅ | P1 |
| **Cemu** | Wii U | AppImage `Cemu.AppImage` ✓ (Proton variant also offered) | `controllerProfiles/controller<N>.xml`, `<name>.xml`, `gameProfiles/<titleid>.ini` | XML + INI | API + UUID/GUID | ✅ via game profile | ✅ | P1 |
| **yuzu-family** (Citron / Eden / Sudachi …) | Switch | AppImage `Eden.AppImage`, `citron.AppImage`, `yuzu.AppImage` ✓ (all off by default) | `qt-config.ini` `[Controls]`, `custom/<titleid>.ini` | Qt INI (escaped strings, `engine:sdl,port:0,guid:...`) | GUID + port | ✅ | ✅ (input profiles) | P1 |
| **Ryujinx-family** (Ryubing …) | Switch | Binary (Ryubing tar.gz) in `publish/` ✓ | `Config.json` `input_config[]`, `profiles/controller/*.json` | JSON | GUID-based id | ⚠️ **[VERIFY]** | ✅ | P1 |
| **Citra-family** (Lime3DS / Azahar) | 3DS | AppImage `azahar.AppImage` ✓ | `qt-config.ini` `[Controls]`, per-game **[VERIFY]** | Qt INI | GUID + port | ⚠️ | ✅ | P1 |
| **melonDS** | NDS | Flatpak `net.kuribo64.melonDS` ✓ | `melonDS.toml` (newer) / `melonDS.ini` (older) | TOML / INI | joystick id (index) | ❌ | ❌ | P2 |
| **xemu** | Xbox | Flatpak `app.xemu.xemu` ✓ | `xemu.toml` `[input.bindings]` | TOML | GUID | ❌ | ⚠️ newer versions have remapping **[VERIFY]** | P2 |
| **Flycast** (standalone) | DC / NAOMI / Atomiswave | Flatpak `org.flycast.Flycast` ✓ | `emu.cfg`, `mappings/SDL_<name>.cfg` | INI | name-based mapping files | ⚠️ | ✅ (per-device files) | P2 |
| **MAME** (standalone) | Arcade | Flatpak `org.mamedev.MAME` ✓ | `ctrlr/*.cfg`, `cfg/<game>.cfg` | XML | joystick index / name (`-mapdevice`) | ✅ | ✅ | P2 |
| **Vita3K** | PS Vita | Binary (AppImage renamed to `Vita3K/Vita3K`) ✓ | `config.yml` controller binds | YAML | SDL | ❌ | ❌ | P2 |
| **ScummVM** | ScummVM | Flatpak `org.scummvm.ScummVM` ✓ | `scummvm.ini` keymaps | INI | — | ✅ per game | — | P3 |
| **mGBA** (standalone) | GB/GBC/GBA | AppImage `mGBA.AppImage` ✓ | `config.ini` `[gba.input.SDLB]` **[VERIFY]** | INI | SDL name | ❌ | ✅ | P3 |
| **shadPS4** | PS4 | AppImage `Shadps4-qt.AppImage` ✓ | `config.toml` + `input_config/*.ini` **[VERIFY]** | TOML/INI | SDL | ✅ | ✅ | P3 |
| **Model 2** (Wine) | Sega Model 2 | Windows exe via Proton (`roms/model2/emulator_multicpu.exe`) ✓ | `EMULATOR.INI` + `.input` files | INI / binary | DirectInput | ✅ | — | P3 (likely skip) |
| **Supermodel** | Sega Model 3 | Flatpak `com.supermodel3.Supermodel` ✓ | `Supermodel.ini` | INI | `JOY1_...` index | ✅ (per-game sections) | — | P3 |
| **Primehack** | Metroid Prime (Wii/GC) | Flatpak `io.github.shiiion.primehack` ✓ | same as Dolphin (fork) | Dolphin INI | as Dolphin | ✅ | ✅ | P3 (reuse Dolphin adapter) |

[^install]: **Install (EmuDeck)** checked against `dragoonDorise/EmuDeck@dddb302` (main, 2026-10-05): `<Emu>_emuType` / `<Emu>_emuPath` in [`functions/EmuScripts/emuDeck*.sh`](https://github.com/dragoonDorise/EmuDeck/tree/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/EmuScripts). The install list and default selection come from `installEmus` in [`EmuDeck/emudeck-electron` `src/renderer/App.tsx`](https://github.com/EmuDeck/emudeck-electron/blob/b06bfcf5270f750c27b959dc3bca25425c99513c/src/renderer/App.tsx). AppImages and binaries live in `$emusFolder` = `~/Applications/` (`vars.sh`). Flatpaks are installed with `flatpak install flathub <id> --user` (`functions/installEmuFP.sh`). ✓ = confirmed in source (still check on device). EmuDeck also installs emulators not in this table: ares (Flatpak `dev.ares.ares`), Rosalie's Mupen GUI (Flatpak `com.github.Rosalie241.RMG`), BigPEmu and Xenia (Windows, via Proton), and ARMSX2 (AppImage, ARM only). Off by default in the GUI: ares, BigPEmu, Citron, Eden, Flycast, MAME, mGBA, RMG, Yuzu. EmuDeck's legacy RPCS3 Flatpak script (`net.rpcs3.RPCS3`) is still in the repo but not used.

### RetroArch: cores are sub-adapters

RetroArch is a single adapter with **core descriptors**. Each core maps the
RetroPad (B, Y, Select, Start, Up, Down, Left, Right, A, X, L, R, L2, R2, L3,
R3 + analogs) onto its console differently. For each core, the descriptor
gives the system(s) and a table `console input → RetroPad id`, so canonical
`snes.standard.b` can become "RetroPad B" for Snes9x, and so on. Remaps are
written as `.rmp` per core (system scope) or per game (game scope). Cores to
start with: Snes9x, bsnes, Mesen, Nestopia, mGBA, Gambatte, Genesis Plus GX,
PicoDrive, Beetle PSX HW / SwanStation, Mupen64Plus-Next / ParaLLEl N64, Beetle Saturn, FBNeo, MAME 2003+, Flycast, PPSSPP core, melonDS DS, Dolphin core.

**The MVP4 in detail:** [RetroArch](adapters/retroarch.md), [Dolphin](adapters/dolphin.md),
[PCSX2](adapters/pcsx2.md), [DuckStation](adapters/duckstation.md).
New adapters start from the [template](adapters/_template.md).

## 3. Common adapter pitfalls

- **EmuDeck AutoMap.** On by default for Dolphin, Cemu and the Switch emulators. At every launch it copies the stock input file (e.g. `GCPadNew.ini`) over the user's file and rewrites `Device=` lines, *after* our wrapper has run. Adapters for these emulators must check that AutoMap is off and report it in the trace if not. See [ADR-001](adr/001-apply-at-launch.md) and risk R14.

- **Save-on-exit clobbering.** Many emulators write their whole config back when they exit, which keeps whatever they had in memory. We only ever write *before* launch, so this mostly works out. But if the user changes bindings in the emulator UI, the next launch's apply will overwrite them. The fix is **drift detection** ([09](09-storage-safety-sync.md)): hash the managed keys after we write them. On the next launch, if the hash differs, offer to **import** the change as a user rule instead of silently reverting it.
- **Device naming varies between versions.** For example, Dolphin's SDL backend changed button naming between versions (`Button 0` vs `Button S`) **[VERIFY]**. Adapters get the version and pick a naming table to match.
- **Flatpak vs AppImage paths differ** (`~/.var/app/<id>/config/...` vs `~/.config/...`). The path provider handles both and prefers whichever one EmuDeck currently uses.
- **SD card installs.** EmuDeck's `Emulation/` folder may be on `/run/media/<label>/Emulation`, which affects ROM paths (game id) but not configs. **[VERIFY]**
- **EmuDeck's own config management.** EmuDeck "Reset / update configurations" copies templates over the configs. Our next launch re-applies, which is fine. But we must also re-snapshot "pristine" after a reset, so uninstall restores the *new* EmuDeck baseline. Detect a reset by spotting a large change across the whole file versus our journal.
- **Multiple instances / forks** (yuzu forks, Citra forks, Ryujinx forks) share a format family. Write one parameterized adapter per family, with an entry per fork for paths.
