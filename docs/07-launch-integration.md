# 07 — Launch Integration

Mappings must be on disk **before** the emulator reads its config. That means
we have to run in the launch path.

All facts below come from EmuDeck's source at `dragoonDorise/EmuDeck@dddb302`
(main, 2026-10-05) unless marked otherwise. See [Sources](#sources).

## How EmuDeck launches an emulator

EmuDeck keeps its backend as a git clone at `~/.config/EmuDeck/backend/`.
Launcher scripts are copied from `backend/tools/launchers/` to
`$toolsPath/launchers/` (default `~/Emulation/tools/launchers/`, or
`<sd card>/Emulation/tools/launchers/` for SD installs) **and** to
`$romsPath/emulators/` (`flushEmulatorLaunchers` in `functions/helperFunctions.sh`).

File names: `dolphin-emu.sh`, `pcsx2-qt.sh`, `duckstation.sh`, `retroarch.sh`,
`ppsspp.sh`, `rpcs3.sh`, `cemu.sh`, `cemu-native.sh`, `ryujinx.sh`, `eden.sh`,
`citron.sh`, `yuzu.sh`, `azahar.sh`, `melonds.sh`, `mgba.sh`, `flycast.sh`,
`mame.sh`, `primehack.sh`, `scummvm.sh`, `xemu-emu.sh`, `xenia.sh`,
`xenia-emu.sh`, `vita3k.sh`, `shadps4.sh`, `supermodel.sh`,
`model-2-emulator.sh`, `bigpemu.sh`, `ares-emu.sh`, `armsx2.sh`,
`rosaliesmupengui.sh`, plus `es-de/es-de.sh`, `pegasus/pegasus-frontend.sh`
and `srm/steamrommanager.sh`. Verbatim copies of four of them are in
[tests/fixtures/emudeck-launchers/](../tests/fixtures/emudeck-launchers/).

Every launcher has the same skeleton (Dolphin shown):

```bash
#!/usr/bin/env bash
cd "$HOME/.config/EmuDeck/backend/"
git pull
. "$HOME/.config/EmuDeck/backend/functions/all.sh"
launcherInit                          # update_launchers: re-copies ALL launchers from backend
emulatorInit "dolphin" "${@}"         # git reset --hard && git pull, auto-install, launch fixes (AutoMap), cloud sync
flatpak run org.DolphinEmu.dolphin-emu "${@}"
cloud_sync_uploadForced
rm -rf "$savesPath/.gaming";
```

- **Args.** The launcher passes `"$@"` straight to the emulator. AppImage
  launchers (`pcsx2-qt.sh`, `duckstation.sh`) first strip a leading/trailing
  `'` from each arg (legacy parsers quoted paths), find the newest
  `~/Applications/<name>*.AppImage`, and launch it without args if none were
  given. `pcsx2-qt.sh` falls back to a Flatpak if no AppImage is found;
  `duckstation.sh` doesn't. `retroarch.sh` inserts `$netplayCMD` before `"$@"`.
- **`emulatorInit <name>`** (`functions/helperFunctions.sh`) does, in order:
  install the emulator if missing; show an AutoMap notice if launched with no
  args; `git reset --hard && git pull` in the backend; re-source `all.sh`; run
  `emulatorLaunchFixes`, which calls `<Prefix>_launch_fixes` if it exists;
  then start cloud sync. Only `dolphin-emu.sh` and `cemu.sh` pass the ROM args
  to `emulatorInit`.
- **Launch fixes that touch input.** `Dolphin_launch_fixes` →
  `Dolphin_setGamepads`, `Cemu_launch_fixes` → `Cemu setControllers`, and
  `Ryujinx_launch_fixes` (SDL2 → SDL3 input migration). This is EmuDeck's
  **AutoMap** feature (setting `automap.{dolphin,cemu,yuzu}` in
  `~/.config/EmuDeck/settings.json`; the GUI defaults all three to `true`).
  With AutoMap on, `Dolphin_setGamepads` **copies the shipped `GCPadNew.ini`
  over the user's file**, re-applies the ABXY/BAYX swap, then runs
  `tools/gamepads/dolphinGamepads.py --write` inside the Flatpak. That script
  enumerates SDL pads (Steam virtual pads ordered by Steam slot, otherwise
  external pads before built-in ones) and rewrites `Device =` in
  `GCPadNew.ini`, `WiimoteNew.ini` and `Hotkeys.ini`, `SIDevice0..3` in
  `Dolphin.ini`, and `Source =` per Wiimote. On a Deck (`Jupiter`/`Galileo`)
  with the setting unset, it's skipped. "Unset" means the variable is empty
  or absent from `settings.sh`: `jsonToBashVars` writes
  `autoMapDolphin=$(jq .automap.dolphin settings.json)`, and jq prints `null`
  for a missing key, which is neither empty nor `false`, so AutoMap runs.
  The EmuDeck app's AutoMap page writes the same variables directly
  (`setSetting autoMapDolphin …; setSetting autoMapSwitch …; setSetting
  autoMapCemu …`, `src/renderer/pages/AutoMapConfigPage.jsx` @ `b06bfcf`).
  Cemu (`emuDeckCemu.sh`) and Ryujinx (`emuDeckRyujinx.sh`, `autoMapSwitch`)
  use the same unset-on-a-Deck rule. `map-helper doctor` reports AutoMap on for
  Dolphin as an error, and for Cemu and the Switch emulators (not managed yet)
  as info (`functions/jsonToBashVars.sh` L150–153,
  `functions/EmuScripts/emuDeckDolphin.sh` `Dolphin_setGamepads` L263–273 @
  `dddb302`). Both EmuDeck repos' heads were still `dddb302` and `b06bfcf` on
  2026-10-22, and AutoMap there covers only those three. EmuDeck 2.7's
  announced "AutoMap Controllers" toggle (SteamOS/Linux opt-in, up to 4
  players) isn't in either repo yet; recheck the variable names and the
  unset-means-off rule when it lands **[VERIFY]**.
- **No pre-launch hook mechanism exists.** `all.sh` sources a fixed list of
  backend files plus `~/.config/EmuDeck/settings.sh` (EmuDeck-generated from
  `settings.json`). There's no `hooks/` directory, glob or user script.

### EmuDeck overwrites launchers on every launch

`launcherInit` → `update_launchers` copies every `*.sh` under
`$toolsPath/launchers/` and `$romsPath/emulators/` back from
`backend/tools/launchers/`. It runs at the start of **every** launcher, and
also from `appImageInit` when the EmuDeck app starts. On top of that,
`emulatorInit` runs `git reset --hard` on the backend at every launch, so edits
to backend files are reverted as well (untracked files survive, but nothing
sources them).

## Launch paths on a Deck with EmuDeck

| Path | What actually runs | Goes through launcher? |
|------|--------------------|------------------------|
| Steam Game Mode via **SRM** shortcuts | Shortcut Exe = `$toolsPath/launchers/<emu>.sh` (shipped parsers use the placeholder `/run/media/mmcblk0p1/Emulation/tools`, which `SRM_setEmulationFolder` rewrites to `$toolsPath`). RetroArch parsers use `${retroarchpath}` = `…/tools/launchers/retroarch.sh` with args `-L <cores>/<core>_libretro.so "${filePath}"`. Examples: PCSX2 `-batch -fullscreen -nogui "${filePath}"`, DuckStation `-batch -fullscreen -nogui "${filePath}"`, Dolphin launch options `vblank_mode=0 %command% -b -e "${filePath}"`. | **Yes** for every shipped parser **except Vita3K**, which points straight at `~/Applications/Vita3K/Vita3K`. |
| **ES-DE** | EmuDeck installs `~/ES-DE/custom_systems/es_find_rules.xml` and `es_systems.xml`. The custom find rules send **only** `CEMU`, `DOLPHIN`, `SHADPS4`, `RYUJINX` and `XENIA` to launchers. `RETROARCH` resolves to the Flatpak `org.libretro.RetroArch` directly, and `EDEN`/`AZAHAR`/`CITRON`/`YUZU` to `~/Applications/*.AppImage` directly. Everything else (**PCSX2, DuckStation**, PPSSPP, …) uses ES-DE's bundled find rules, which point at `~/Applications/pcsx2-*.AppImage`, `~/Applications/DuckStation*.AppImage` or the Flatpak exports. Custom `es_systems.xml` routes atarijaguar (BigPEmu), model2 and wiiu through launchers with `/bin/bash <launcher> %ROM%`. | **Partly.** Dolphin and Cemu yes; **RetroArch, PCSX2 and DuckStation no.** `ESDE_launch_fixes` (run by `es-de.sh` at ES-DE start) re-asserts the Dolphin/Cemu/Ryujinx launcher rules. |
| **Pegasus** | `roms/<system>/metadata.txt` `launch:` lines, e.g. `…/launchers/duckstation.sh -batch -fullscreen -nogui {file.path}`, `…/launchers/retroarch.sh -L CORESPATH/snes9x_libretro.so {file.path}` | **Yes** (checked for psx, ps2, gc, snes) |
| Desktop mode / direct | The user runs an emulator by hand | No hook, but `map-helper apply --emulator X` can be run by hand |

**Correction to the original plan:** not every path ends in a launcher. ES-DE
launches RetroArch, PCSX2 and DuckStation directly. Steam/SRM and Pegasus do
go through launchers.

## Options

### Option A: Patch EmuDeck launcher scripts (insert one line) — **not viable**

```bash
# --- map-helper hook (managed) ---
command -v mh-run >/dev/null && mh-run --hook --emulator dolphin --args "$@" || true
# --- end map-helper hook ---
```

- ❌ `update_launchers` restores the stock launchers at the start of **every**
  launch, and the EmuDeck app does the same on start. A patched launcher
  overwrites itself (via `launcherInit`) before our line would run, and the
  patch is gone for the next launch. Re-patching from a Decky plugin would
  race every launch.
- ❌ It wouldn't cover ES-DE → RetroArch/PCSX2/DuckStation anyway.

### Option B: Wrap the launcher (shim)

SRM/ES-DE point to `mh-run --emulator dolphin -- ~/Emulation/tools/launchers/dolphin-emu.sh <rom>`.

- ✅ Doesn't modify EmuDeck files.
- ❌ Requires changing SRM parsers (`~/.config/steam-rom-manager/userData/userConfigurations.json`,
  which `SRM_init` overwrites with a `.bak` backup on reset) and ES-DE find
  rules (`~/ES-DE/custom_systems/es_find_rules.xml`, overwritten with `.bak`
  by `ESDE_init`; `ESDE_launch_fixes` also re-asserts the Dolphin/Cemu/Ryujinx rules).
- ❌ **AutoMap ordering.** We would write *before* `emulatorInit`, so for
  Dolphin (and Cemu / Switch emulators) AutoMap then copies the stock
  `GCPadNew.ini` over our output and rewrites `Device =` lines. Wrap mode only
  works for these emulators if AutoMap is off for them
  (`automap.dolphin=false` etc.), or if map-helper takes over AutoMap's job of
  setting device lines. **[VERIFY]** on device that AutoMap really fires with
  GUI defaults.

### Option C: EmuDeck-provided hook (upstream)

Propose a tiny hook to EmuDeck. The natural insertion point is the end of
`emulatorInit` (after `emulatorLaunchFixes`), which every launcher already
calls. It would run `~/.config/EmuDeck/hooks/pre-launch.d/*` if present,
passing the emulator id and ROM args. This needs launchers to pass `"$@"` to
`emulatorInit` (today only Dolphin and Cemu do).

- ✅ Clean, survives updates, runs after AutoMap, and benefits the whole ecosystem.
- ❌ Depends on upstream accepting it. It still doesn't cover ES-DE launches
  that bypass launchers.

### Option D: Decky lifecycle event

The Decky plugin listens for app launch (`SteamClient.GameSessions.RegisterForAppLifetimeNotifications` or similar **[VERIFY]**) and applies.

- ❌ It races the emulator's config read, and it doesn't cover ES-DE launches. **Not used for applying**; at most for UX (e.g., "show which mapping is active" toast).

### Option E: ES-DE `game-start` event script (ES-DE only)

ES-DE runs every file in `~/ES-DE/scripts/game-start/` on game launch, in
lexicographic order, and waits for each one to finish. It passes the ROM path,
game name, system name and full system name. This needs ES-DE's *Enable custom
event scripts* setting (`CustomEventScripts`, off by default; EmuDeck's
`es_settings.xml` doesn't set it).

- ✅ User-owned directory that EmuDeck doesn't touch. Covers the ES-DE paths
  that bypass launchers (RetroArch, PCSX2, DuckStation).
- ❌ Fires before the launcher, so the same AutoMap caveat as Option B applies
  for Dolphin/Cemu. **[VERIFY]** that it fires before the emulator process
  starts and that enabling the setting survives EmuDeck's `ESDE_update`
  (which uses `--ignore-existing`; `ESDE_init`/reset overwrites it).

**Decision (revised):** Option A is ruled out. For Steam/SRM, use **B via Steam
launch options or the SRM parser executable**. For ES-DE, use **E**. Either
way, disable EmuDeck AutoMap for any emulator map-helper manages, and offer to
do that as part of setup. **C** stays the long-term goal. See
[ADR-001](adr/001-apply-at-launch.md) (needs updating to match).

## `mh-run` behaviour

```
mh-run --hook --emulator <id> [--system <sys>] --args <original args...>
```

1. Parse the original args with the adapter (`adapter.parse_launch_args`) to
   get the ROM path, plus the system if the launcher handles several (RetroArch:
   the core path implies the system; Dolphin: the file extension or header gives GC vs Wii).
   Known arg shapes from EmuDeck parsers: Dolphin `-b -e <rom>`; PCSX2 and
   DuckStation `-batch -fullscreen -nogui <rom>` (possibly wrapped in single
   quotes by legacy parsers); RetroArch `-L <core>.so <rom>`.
2. Probe → slots → resolve → render → write (see [02](02-architecture.md)).
3. **Hard time budget: 500 ms** (target < 150 ms). Past the budget, abort and launch unchanged.
4. In hook mode, return 0 and let the launcher continue. In wrap mode, `exec` the command.
5. Log to `$STATE/logs/launch.log` (rotated), with the resolution trace summary.
6. Optional: write `$STATE/last-launch.json` for the Decky UI ("Active mapping: DS4 → GC (family rule)").

### Post-exit (optional)

Some users want the emulator's config restored after exit, for example so that
running the emulator by hand in Desktop mode gets the EmuDeck defaults. That's
`restore_after_exit: true`. It needs wrap mode (we have to wait for exit), or
in hook mode a `trap` added to the launcher. Default **off**. Next launch
applies again anyway.

## Steam launch options alternative

Non-Steam shortcuts do support `%command%` in launch options. EmuDeck's own
SRM parsers depend on it: Dolphin, PrimeHack, Cemu, Eden, Citron and Yuzu
shortcuts set `executableArgs` to `vblank_mode=0 %command% -b -e "${filePath}"`
with `appendArgsToExecutable: false`, so SRM writes it as the shortcut's launch
options. So `mh-run --emulator dolphin -- %command% -b -e "<rom>"` per
shortcut, or in bulk by editing the SRM parser `executableArgs`, is Option B's
cleanest form. Parsers with `appendArgsToExecutable: true` (RetroArch) put
args in the Exe field instead. **[VERIFY]** how Steam expands `%command%` when
the Exe field already holds args.

## Desktop mode

`map-helper apply --emulator dolphin [--system gc] [--game <id>]` resolves with
the currently connected controllers and writes. A `.desktop` action could wrap
the emulator's own desktop entry. That's P3.

## Sources

EmuDeck backend, `https://github.com/dragoonDorise/EmuDeck` at commit
`dddb30229adbbd54d5ff7283cfd70e11c4322c26` (branch `main`, GPL-3.0). This is
the canonical backend repo; the GUI is `EmuDeck/emudeck-electron`.

- Launchers: [`tools/launchers/`](https://github.com/dragoonDorise/EmuDeck/tree/dddb30229adbbd54d5ff7283cfd70e11c4322c26/tools/launchers) (`dolphin-emu.sh`, `pcsx2-qt.sh`, `duckstation.sh`, `retroarch.sh`, `es-de/es-de.sh`)
- `update_launchers`, `flushEmulatorLaunchers`, `emulatorInit`, `emulatorLaunchFixes`: [`functions/helperFunctions.sh`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/helperFunctions.sh)
- `launcherInit`: [`functions/launcherInit.sh`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/launcherInit.sh); also called from `functions/appImageInit.sh`
- Sourcing order: [`functions/all.sh`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/all.sh)
- AutoMap: [`functions/EmuScripts/emuDeckDolphin.sh`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/EmuScripts/emuDeckDolphin.sh) (`Dolphin_setGamepads`), [`tools/gamepads/dolphinGamepads.py`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/tools/gamepads/dolphinGamepads.py), `cemuGamepads.py`, `ryujinxGamepads.py`
- SRM parsers: [`configs/steam-rom-manager/userData/userConfigurations.json`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/configs/steam-rom-manager/userData/userConfigurations.json), `userSettings.json` (`retroarchPath`), `parsers/optional/*.json` (PCSX2, melonDS, mGBA, Azahar, …); `SRM_init` / `SRM_setEmulationFolder` in `functions/ToolScripts/emuDeckSRM.sh`
- ES-DE: [`configs/emulationstation/custom_systems/es_find_rules.xml`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/configs/emulationstation/custom_systems/es_find_rules.xml), `es_systems.xml`; install paths in `functions/ToolScripts/emuDeckESDE.sh`
- Pegasus: `roms/<system>/metadata.txt`
- GUI defaults (`automap`, `controllerLayout: 'baxy'`): [`EmuDeck/emudeck-electron` `src/renderer/App.tsx`](https://github.com/EmuDeck/emudeck-electron/blob/b06bfcf5270f750c27b959dc3bca25425c99513c/src/renderer/App.tsx) at `b06bfcf`
- ES-DE bundled find rules: [`resources/systems/linux/es_find_rules.xml`](https://gitlab.com/es-de/emulationstation-de/-/blob/a529a9d38c0af09b6fd7e38d10c8076cb0a21050/resources/systems/linux/es_find_rules.xml) at `a529a9d`
- ES-DE custom event scripts: [`INSTALL.md` § Custom event scripts](https://gitlab.com/es-de/emulationstation-de/-/blob/a529a9d38c0af09b6fd7e38d10c8076cb0a21050/INSTALL.md#custom-event-scripts)
