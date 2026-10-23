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
  for Dolphin/Cemu.
- In source, it fires before the emulator starts: `FileData::launchGame` calls
  `Scripting::fireEvent("game-start", ...)` (`es-app/src/FileData.cpp` L2174 @
  `a529a9d`) before it runs the launch command, and game-start scripts run
  blocking (`system()`, `es-core/src/utils/PlatformUtil.cpp` L130-131).
  **[VERIFY]** on a Deck (an mh-run log line before the emulator's first
  output). The setting survives EmuDeck's `ESDE_update`, which copies
  `es_settings.xml` with `--ignore-existing`; `ESDE_init` (install or reset)
  overwrites it (`functions/ToolScripts/emuDeckESDE.sh` @ `dddb302`).

**Decision (revised):** Option A is ruled out. For Steam/SRM, use **B via Steam
launch options or the SRM parser executable**. For ES-DE, use **E**. Either
way, disable EmuDeck AutoMap for any emulator map-helper manages, and offer to
do that as part of setup. **C** stays the long-term goal. See
[ADR-001](adr/001-apply-at-launch.md).

## `mh-run` behaviour

Implemented in `core/maphelper/mhrun.py`; `map-helper setup` puts it in the launch paths (below).

```
mh-run --emulator <id> [--system S] [--core C] [--game G] -- <command...>    wrap (Steam / SRM shortcuts)
mh-run --hook --emulator <id> --rom <path> [--system S] [--core C]          hook: apply, exit 0
mh-run --hook --es-de <rom> <game name> <system> <full system name>        ES-DE game-start event
```

`<id>` is `dolphin`, `pcsx2` or `retroarch` (the registry in `core/maphelper/pipeline.py`). Testing and
development options: `--config-root`, `--rules`, `--state-dir`, `--es-de-root`, `--no-exec`, and the probe options
of `map-helper devices`.

1. **Read the command** (`core/maphelper/launch.py`). Every arg first loses one leading and one trailing `'`, as
   EmuDeck's AppImage launchers do for legacy SRM parsers. `flatpak run [opts] <app id>` in front is skipped.
   - RetroArch: `-L <core>_libretro.so` (or `--libretro=`) names the core; the last non-option arg is the ROM. The
     core picks the descriptor in `data/adapters/retroarch/cores/` (an unknown core: nothing to do). The system is
     `--system`, else the ROM's folder under `roms/` if the core runs it, else the core's only system. The game id is
     RetroArch's content name (file name without its last extension; the member's for `a.zip#b.sfc`).
   - Dolphin: `-e <rom>` / `--exec=<rom>`. GameCube or Wii comes from the disc header, Dolphin's own test
     (`DiscIO/Volume.cpp` `CreateDisc` L121-124: `WII_DISC_MAGIC` 0x5D1C9EA3 at 0x18, `GAMECUBE_DISC_MAGIC`
     0xC2339F3D at 0x1C, `DiscIO/DiscUtils.h` L25-26 @ `2c805fee8f`), read where it's uncompressed: ISO/GCM at 0,
     WIA/RVZ at 0x58 (after the 0x48-byte `WIAHeader1` and four u32s of `WIAHeader2`, `WIABlob.h`), CISO at 0x8000
     when block 0 is stored (`CISOBlob.h`); WBFS holds only Wii discs. The header also gives the game id (`GALE01`).
     GCZ and anything else fall back to the ROM's folder (`roms/gc`, `roms/wii`). Wii isn't rendered yet, so a Wii
     disc changes nothing.
   - PCSX2: the last non-option arg (`-batch -fullscreen -nogui <rom>`), or `-elf <file>`. Always `ps2`. No game id
     yet (the serial needs SYSTEM.CNF from the disc).
   - The ROM's folder: EmuDeck keeps ROMs in `Emulation/roms/<ES-DE system name>/` (ES-DE's `%ROMPATH%/<name>`
     system paths, the `${romsdirglobal}/<name>` romDirectory of EmuDeck's SRM parsers), mapped to map-helper's
     system ids by `data/frontends/es-de.json` `aliases` (`megadrive` → `genesis`, `sfc` → `snes`, ...).
2. **ES-DE events** (`core/maphelper/esde.py`). ES-DE passes the ROM path escaped for a shell: `getEscapedPath`
   puts a backslash before `\ '"!$^&*(){}[]?;<>` (`es-core/src/utils/FileSystemUtil.cpp` L480-505), and
   `Scripting::fireEvent` runs the script through `system()` with each arg in double quotes, where sh removes only
   the backslashes before `$`, `` ` ``, `"` and `\`. mh-run removes the rest. ES-DE doesn't say which emulator it
   will run, so mh-run works it out as `FileData::launchGame` does (`es-app/src/FileData.cpp` L979-1016 @ `a529a9d`):
   the game's `<altemulator>` in `~/ES-DE/gamelists/<system>/gamelist.xml` (when `AlternativeEmulatorPerGame` is on,
   the default), else the system's `<alternativeEmulator><label>` there, else the system's first command. The
   commands come from `~/ES-DE/custom_systems/es_systems.xml` if it defines the system, else from ES-DE's bundled
   `es_systems.xml`, copied into `data/frontends/es-de.json` for the 50 systems where some command runs a managed
   emulator. ES-DE's own default for `gc`, `wii` and `ps2` is a RetroArch core; EmuDeck's `ESDE_setDefaultEmulators`
   writes `Dolphin (Standalone)` and `PCSX2 (Standalone)` labels into the gamelists. A system that isn't in the
   table, or a command that runs an emulator map-helper doesn't manage (DuckStation, PPSSPP standalone, ...), is
   logged and skipped.
3. **Apply** through the same pipeline as `map-helper apply --write` (`core/maphelper/pipeline.py`): probe → Steam's
   order and the player policy → resolve (shipped defaults + `$DATA/rules`) → render → write, with the touched-file
   manifest and pristine backups. The config root is EmuDeck's (Dolphin's and RetroArch's Flatpak dirs,
   `~/.config/PCSX2` for the AppImage); a missing one means the emulator never ran, and is skipped. The advisory lock
   `$STATE/locks/<emulator>.lock` is taken non-blocking (`flock`): if another launch holds it, skip, never wait.
4. **Budget: 500 ms** from the start of `main` (the interpreter's own start-up, ~20-40 ms, comes before it). A
   `SIGALRM` watchdog interrupts whatever is running when it runs out, and the deadline is checked between steps.
   The cut-off can't leave a half-written file: the writer stages **every** changed file complete and fsynced as a
   temp file next to it, then asks a gate. The gate turns the watchdog off and looks at the clock once more; past
   the deadline it says no, the temp files are removed and nothing is written. After a yes, all that's left is the
   pristine snapshots of first-touched files (copied through a temp file too), the manifest, and one `rename` per
   file. So a set of files is never half applied either, short of a crash between two renames, which leaves each
   file whole and the manifest still listing it. Measured on a Mac: 70-140 ms for RetroArch with four pads.
   **[VERIFY]** the time on a Deck.
5. **Fail open.** Any exception (a bad rule, an unreadable `/proc` file, bad arguments), a skip or the budget is
   logged; the command still runs. Nothing is printed: stdout and stderr are swallowed while mh-run works, because in
   wrap mode the emulator inherits them. Hook mode always exits 0. A command that can't be executed returns 127.
6. **Log**: one line per launch in `$STATE/logs/launch.log`, rolled to `launch.log.1` past 256 KB:
   `2026-10-22T18:45:27 wrap emulator=retroarch system=snes core=snes9x game=a players=4 ms=69 no changes`, or
   `changed: <files>`, `skipped: <why>`, `error: <exception>`.
7. Optional, not done: `$STATE/last-launch.json` for the Decky UI ("Active mapping: DS4 → GC (family rule)").

### The shim, and who runs the command

`~/.local/bin/mh-run` is a POSIX sh shim ([14](14-packaging-permissions.md) §6). It runs
`/usr/bin/python3 -I ~/.local/lib/map-helper/current/mh_entry.py mh-run --no-exec "$@"` with stdin, stdout and
stderr on `/dev/null` (and under coreutils `timeout -k 3 -s TERM 2` as a backstop, where it exists: TERM before the writer's gate aborts like the watchdog and writes nothing; after the gate mh-run ignores TERM so the renames finish, and KILL follows only a real hang), then the **shell**
execs the command after `--`. A missing install, a missing Python, or a Python that crashes still launches the
game, and the emulator replaces the shell, so Steam keeps the PID it started. With `--hook` the shim exits 0 instead.
Run without the shim (`python3 -I mh_entry.py mh-run ...` without `--no-exec`), mh-run execs the command itself
(`os.execvp`); `mh_entry.py` does the same when it can't even import map-helper.

### `map-helper setup` and `uninstall`

Dry runs unless `--write`; both idempotent. setup records what it changed in `$STATE/setup.json`, and uninstall
undoes exactly that: a file or value someone changed since is left alone (an SRM parser whose args changed but still
carry our prefix loses just the prefix).

- **Shim**: writes `~/.local/bin/mh-run` (0755). It refuses to overwrite a file that isn't its own.
- **SRM parsers** (`~/.config/steam-rom-manager/userData/userConfigurations.json`): every parser whose executable is
  `${retroarchpath}` with a core map-helper has a descriptor for, `.../dolphin-emu.sh` or `.../pcsx2-qt.sh` gets
  `<shim> --emulator <id> -- ` right before `%command%` in `executableArgs`, or `<shim> --emulator <id> -- %command%`
  in front when there's no `%command%`. Only those JSON values change, edited in place; the rest of the file keeps
  its bytes. A copy goes to `$STATE/backups/setup/` first. Shapes:
  - `appendArgsToExecutable: false` (Dolphin: `vblank_mode=0 %command% -b -e "${filePath}"`): the args are the
    shortcut's launch options already. Only the launch options change; the app id doesn't.
  - `appendArgsToExecutable: true` (RetroArch: `-L .../snes9x_libretro.so "${filePath}"`): SRM appends the args to
    the Exe and clears the launch options (`appendArgsPromise`, `src/lib/file-parser.ts` L851-856 @
    `SteamGridDB/steam-rom-manager@f68289a`). `%command%` only works in launch options, so setup also sets
    `appendArgsToExecutable` to `false`. The Exe then holds just the launcher, as Dolphin's does, so we never rely on
    how Steam expands `%command%` around an Exe with args. The cost: SRM's app id is
    `generateShortAppId(exe, title)` (L892-895), so these shortcuts get **new app ids** at the next "Save to Steam",
    and per-shortcut Steam state (controller layout, playtime, collections Steam keeps by id) doesn't follow. setup
    says so and lists them. Uninstall puts the old Exe back, and with it the old ids.
  - Nothing reaches Steam until the user runs SRM's **Save to Steam**; `doctor` lists emulator shortcuts in
    `shortcuts.vdf` that don't run mh-run yet. setup never writes `shortcuts.vdf`.
  - setup refuses while SRM runs: it keeps its parsers in memory and saves them from its UI. **[VERIFY]** that SRM
    writes `userConfigurations.json` only on a parser save (so a running SRM that isn't saved leaves our edit), and
    the process name (`steam-rom-manager` under the AppImage mount).
  - EmuDeck's `SRM_init` (a reset) copies its template over the file with a `.bak`, dropping the edit; `doctor`
    then reports the bare parsers and setup can run again.
- **ES-DE**: installs `~/ES-DE/scripts/game-start/map-helper.sh`, which runs
  `~/.local/bin/mh-run --hook --es-de "$1" "$2" "$3" "$4"` and always exits 0, and sets `<bool
  name="CustomEventScripts" value="true" />` in `~/ES-DE/settings/es_settings.xml` (changing the value if the
  element is there, else adding the line; uninstall puts the old value back or takes the line out). ES-DE reads that
  file once at start and **rewrites all of it** from memory whenever a settings menu closes with a change
  (`Settings::saveFile`, `es-core/src/Settings.cpp` L420-448; `GuiSettings.cpp` L65-66; at start-up only when the
  file is missing, a command-line option changed a setting, or the release number changed, `main.cpp` L803-842; not
  on exit). An edit while ES-DE runs wouldn't take effect and could be overwritten, so setup refuses that step while
  ES-DE runs (process `es-de` under the AppImage mount, **[VERIFY]**). No `es_settings.xml` yet: start ES-DE once.
  EmuDeck's `ESDE_update` copies its `es_settings.xml` with `--ignore-existing`, so the setting survives an EmuDeck
  update; `ESDE_init` (install or reset) overwrites it with a `.bak`, and `doctor` reports custom event scripts off.
- **EmuDeck AutoMap** (ADR-001 item 3): setup reads only `autoMapDolphin` from `~/.config/EmuDeck/settings.sh` and
  reports it when it's on. It doesn't change EmuDeck's settings (that file holds credentials); turning it off is
  the EmuDeck app's AutoMap page for now.

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
args in the Exe field instead; `map-helper setup` switches those to launch
options too (see "`map-helper setup` and `uninstall`"), so Steam's `%command%`
is always just the quoted launcher, the shape EmuDeck's Dolphin shortcuts
already use. **[VERIFY]** on a Deck that a shortcut with
`vblank_mode=0 /home/deck/.local/bin/mh-run --emulator dolphin -- %command% -b -e "<rom>"`
runs mh-run with the env assignment applied and the quoted ROM path intact.

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
- ES-DE custom event scripts: [`INSTALL.md` § Custom event scripts](https://gitlab.com/es-de/emulationstation-de/-/blob/a529a9d38c0af09b6fd7e38d10c8076cb0a21050/INSTALL.md#custom-event-scripts) (game-start args: ROM path, game name, system name, system full name)
- ES-DE source at `a529a9d`: `es-app/src/FileData.cpp` (`launchGame`), `es-core/src/Scripting.cpp` (`fireEvent`), `es-core/src/utils/FileSystemUtil.cpp` (`getEscapedPath`), `es-core/src/utils/PlatformUtil.cpp` (`runSystemCommand`), `es-core/src/Settings.cpp` (`saveFile`, `loadFile`, defaults `CustomEventScripts` false and `AlternativeEmulatorPerGame` true), `es-app/src/guis/GuiSettings.cpp`, `es-app/src/main.cpp`, `es-app/src/GamelistFileParser.cpp` (`alternativeEmulator`), `es-app/src/guis/GuiAlternativeEmulators.cpp`; bundled systems [`resources/systems/linux/es_systems.xml`](https://gitlab.com/es-de/emulationstation-de/-/blob/a529a9d38c0af09b6fd7e38d10c8076cb0a21050/resources/systems/linux/es_systems.xml), copied in part into `data/frontends/es-de.json`
- EmuDeck `es_settings.xml`: [`configs/emulationstation/es_settings.xml`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/configs/emulationstation/es_settings.xml) (two settings, no `CustomEventScripts`); `ESDE_init`, `ESDE_update`, `ESDE_setDefaultEmulators`, `ESDE_setEmu` in `functions/ToolScripts/emuDeckESDE.sh`
- Steam ROM Manager at [`f68289a`](https://github.com/SteamGridDB/steam-rom-manager/blob/f68289a770ff8537ac8235618b3399844580359b/src/lib/file-parser.ts) (2026-10-11): `src/lib/file-parser.ts` (`appendArgsToExecutable`, `appendArgsPromise`, `generateShortAppId(modifiedExecutableLocation, title)`)
- Dolphin disc headers at `2c805fee8f`: `Source/Core/DiscIO/DiscUtils.h`, `Volume.cpp`, `WIABlob.h`, `CISOBlob.h`, `WbfsBlob.cpp`
