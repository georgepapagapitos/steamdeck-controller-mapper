# Shipped defaults

Rules in this folder have source `shipped`. They are the lowest-priority layer.

**Rule #1:** shipped defaults must reproduce EmuDeck's out-of-the-box bindings
and hotkeys exactly (spike S7), so installing map-helper changes nothing a user
can feel until they make a rule.

The summary below is taken from EmuDeck's shipped templates and scripts at
`dragoonDorise/EmuDeck@dddb302` (main, 2026-10-05). The raw files are in
[tests/fixtures/](../../tests/fixtures/) (`<emu>/emudeck-default/`). Button
names are **positional** and use Xbox/SDL names: A = south, B = east, X = west,
Y = north, Select = Back/View, L3/R3 = stick clicks.

## Where EmuDeck's defaults come from

| Emulator | Shipped template (repo path) | Copied to | What actually sets the bindings |
|----------|------------------------------|-----------|---------------------------------|
| RetroArch | `configs/org.libretro.RetroArch/config/retroarch/retroarch.cfg`, `config/remaps/<core>/<core>.rmp.disabled` | `~/.var/app/org.libretro.RetroArch/config/retroarch/` | `retroarch.cfg` (hotkeys only). Pad bindings come from RetroArch's own autoconfig; **EmuDeck ships no autoconfig**. `RetroArch_maincfg.sh` also lists hotkey values, but nothing calls it. |
| Dolphin | `configs/org.DolphinEmu.dolphin-emu/config/dolphin-emu/{GCPadNew,WiimoteNew,Hotkeys,GCKeyNew}.ini`, `Profiles/GCPad/*`, `Profiles/Wiimote/*` | `~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/` | Template, then the layout swap on `GCPadNew.ini`, then **AutoMap at every launch** (see below) |
| PCSX2 | `configs/pcsx2qt/.config/PCSX2/inis/PCSX2.ini` | `~/.config/PCSX2/inis/PCSX2.ini` | `PCSX2QT_init` runs `pcsx2-Qt.AppImage -testconfig` and only copies the template **if that fails**. Then `PCSX2QT_setupControllers` always overwrites `[Hotkeys]`, `[Pad1]`, `[Pad2]` with inline values (fixture `pcsx2/emudeck-default/PCSX2QT_setupControllers.ini`). **The inline values win.** |
| DuckStation | `configs/duckstation/settings.ini` | `~/.local/share/duckstation/settings.ini` | Template only |

Copy semantics (`functions/configEmuFP.sh`, `functions/configEmuAI.sh`):
`<Emu>_init`, which is what install, "reset configuration" and overwrite-config
updates run, uses `rsync --backup --suffix=.bak`. The template replaces the
user's file and the old one is kept as `<file>.bak`. `<Emu>_update` uses
`rsync --ignore-existing`, which only adds missing files. `<Emu>_resetConfig`
is just `<Emu>_init`. For RetroArch, `RetroArch_resetCoreConfigs` first renames
every `*.cfg`/`*.opt` under `config/` to `.bak`, then runs `RetroArch_init`.

## Controller layout setting (`controllerLayout`)

The EmuDeck GUI default is `"baxy"` (`emudeck-electron` `App.tsx`). The
templates already match `baxy`, which puts Nintendo face buttons in Nintendo
positions (console A = east). `"abxy"` swaps to label-match on an
Xbox-labelled pad (console A = south). It only affects Nintendo-style systems:

- **Dolphin GC:** `baxy` gives `Buttons/A = Button E`, `B = Button S`,
  `X = Button N`, `Y = Button W`. `abxy` gives A=S, B=E, X=W, Y=N
  (`Dolphin_setBAYXstyle` / `Dolphin_setABXYstyle` sed `GCPadNew.ini` only).
- **RetroArch:** `abxy` enables the shipped remaps (renames `.rmp.disabled` →
  `.rmp`) for mGBA, Gambatte, bsnes-hd beta, melonDS DS, Mupen64Plus-Next,
  SameBoy, Snes9x, Mesen, Nestopia and Beetle VB. Each remap swaps RetroPad
  A↔B and X↔Y (`input_player1_btn_a = "0"`, `btn_b = "8"`, `btn_x = "1"`,
  `btn_y = "9"`). With `baxy` (default) no remaps are active.
- Cemu, Azahar, melonDS, RMG, Ryujinx and Yuzu have their own swaps. PCSX2
  and DuckStation have none (`PCSX2QT_setABXYstyle` is `NYI`).

## Pad bindings per emulator (defaults)

- **RetroArch:** no player binds in `retroarch.cfg`. `input_joypad_driver = "sdl2"`,
  `input_autodetect_enable = "true"`, `input_max_users = "5"`,
  `input_playerN_joypad_index = N-1`, `input_remap_binds_enable = "true"`,
  `auto_remaps_enable = "true"`, `config_save_on_exit = "false"`. Some per-core
  overrides set `input_player1_analog_dpad_mode = "1"` (e.g. Beetle PCE,
  Beetle Cygne/WonderSwan).
- **Dolphin GC (`GCPadNew.ini`, GCPad1–4):** `Device = SDL/<n>/Steam Deck Controller`.
  A/B/X/Y as above (`baxy`). Z = `Shoulder R`, Start = `Start`, L/R and
  L-/R-Analog = `Trigger L`/`Trigger R`, Main Stick = `Axis 0/1`, C-Stick =
  `Axis 3/4`, D-Pad = `Pad N/S/W/E`, Main/C-Stick Modifier = `Thumb L`/`Thumb R`
  (range 50), Rumble = Strong. **L1 is unbound.**
- **Dolphin Wii (`WiimoteNew.ini`, Wiimote1–4):** upright Wiimote +
  Nunchuk. A = `Button S` | `Thumb R` | mouse click, B = `Button E`,
  1 = `Button N`, 2 = `Button W`, − = Back, + = Start, Home = `Return`
  (keyboard), IR = mouse cursor, Shake = `Shoulder L`, Tilt = `Trigger L` +
  left stick, Nunchuk C = `Shoulder R`, Z = `Trigger R`, stick = left stick.
  Classic: A=E, B=S, X=W, Y=N, ZL/ZR = shoulders. Sideways toggle = Select+R3.
  `[BalanceBoard] Source = 0`.
- **PCSX2 (effective inline values):** Pad1 `DualShock2` on `SDL-0`: Cross=A,
  Circle=B, Square=X, Triangle=Y, Select=Back, Start, L1/R1 = shoulders,
  L2/R2 = `+LeftTrigger`/`+RightTrigger`, L3/R3, both sticks, motors,
  **Analog = `Keyboard/F6`**, Pressure = `Keyboard/S`, PressureModifier 0.3,
  AxisScale 1.33. Pad2 is the same on `SDL-1` with Analog = `SDL-1/Guide`.
  (The fallback template differs: Pad1 Analog = `SDL-0/Guide`, PressureModifier 0.5.)
- **DuckStation:** Pad1–4 `AnalogController` on `SDL-0..3`, same positional
  face map as PCSX2. Pad1 Analog = `Keyboard/F6`, Pad2–4 Analog = `SDL-n/Guide`.
  Pad5–8 = `None`. `[InputSources] SDL = true`, Evdev/XInput/RawInput false.

## Hotkey scheme

EmuDeck uses one convention everywhere: **Select + button = actions,
Start + button = display**, bound to player 1's pad only. All bindings are
positional (south button), so the layout setting doesn't affect them.

| Action | RetroArch¹ | Dolphin | PCSX2 | DuckStation |
|--------|-----------|---------|-------|-------------|
| Quit | Select+Start | Select+Start (Exit) | Select+Start (ShutdownVM) | Select+Start (PowerOff) |
| Pause | Select+A | Select+A | Select+A | Select+A |
| Save state (current slot) | Select+R1 | Select+R1 | Select+R1 | Select+R1 |
| Load state (current slot) | Select+L1 | Select+L1 | Select+L1 | Select+L1 |
| Slot − / + | Select+D-Left / D-Right | Start+L1 / R1 | Start+L1 / R1 | Start+L1 / R1 |
| Reset | Select+L3 | Select+L3 | Select+L3 | Select+L3 |
| Menu | Select+R3, or L3+R3 | — | Select+R3 (pause menu) | Select+R3 (pause menu) |
| Fast-forward | Select+R2 (toggle) | Select+R2 (speed +), Start+R2 (unlimited) | Select+R2 (turbo) | Select+R2 (toggle) |
| Rewind / slow | Select+L2 (rewind) | Select+L2 (speed −) | Select+L2 (slow motion) | Select+L2 (rewind) |
| Screenshot | Select+B | `F9` (keyboard) | `F8` (keyboard) | Select+B |
| Fullscreen | — | Start+L3 | Start+L3 | Start+L3 |
| Resolution + / − | — | Start+D-Up / D-Down | Start+D-Up / D-Down | Start+D-Up / D-Down |
| Aspect / widescreen | — | Start+D-Right | Start+D-Right | Start+D-Right |
| Software renderer | — | — | Start+D-Left | Start+D-Left |
| Other | Select+X FPS, Select+Y next disc, Select+D-Up run-ahead | Select+X stop; Select+left stick ←/→ prev/next controller profile, ↑ connect Wii Remote 1 / prev game profile, ↓ next game profile | — | Select+X change disc, Select+Y toggle PGXP |

¹ RetroArch: `input_enable_hotkey_btn = "4"` (Select), then `_btn` indices in
SDL GameController order (0 A, 1 B, 2 X, 3 Y, 4 Back, 6 Start, 7 L3, 8 R3,
9 L1, 10 R1, 11–14 D-pad U/D/L/R). Rewind and fast-forward are axes `+4` (L2)
and `+5` (R2). `input_menu_toggle_gamepad_combo = "2"` (L3+R3),
`input_quit_gamepad_combo = "4"` (Start+Select), `input_hotkey_block_delay = "5"`,
`menu_swap_ok_cancel_buttons = "true"`.

Dolphin: `[Hotkeys] Device = SDL/0/Steam Deck Controller`. The player 2–4
profile/Wii Remote hotkeys reference `SDL/<n>/Steam Virtual Gamepad`. Many
hotkeys also keep keyboard binds (F1–F8 load slots, Shift+F1–F8 save).

## EmuDeck AutoMap (interacts with our writes)

AutoMap is on by default (`automap.dolphin`, `automap.cemu`, `automap.yuzu`
covers all Switch emulators). For Dolphin, every launch copies the shipped
`GCPadNew.ini` back over the user's file, re-applies the layout swap, and runs
`tools/gamepads/dolphinGamepads.py --write`. That script sets
`Device = SDL/<idx>/<name>` per player (Steam virtual pads by Steam slot,
otherwise external pads before the built-in one) in `GCPadNew.ini`,
`WiimoteNew.ini` and `Hotkeys.ini`. It also sets `SIDevice0..3` (6 = standard
pad) and each Wiimote's `Source`. Our shipped defaults have to reproduce the
**post-AutoMap** result, and our launch-time writes must happen after AutoMap
or AutoMap must be off ([07](../../docs/07-launch-integration.md)).

## Planned files

- `any.global.hotkeys.json`: the hotkey table above, for every emulator
- `any.<system>.positional.json`: one per system, from each layout's
  `positional_default`. These must equal EmuDeck's `baxy` default
  (Nintendo positions).
- `style.nintendo.*.json`: **disabled by default**; offered in the UI as "use
  label-match for Nintendo-style pads". This is EmuDeck's `abxy` setting, so
  import the user's `controllerLayout` and enable it when it's `abxy`.
- `family.valve.steamdeck.*.json`: Deck-specific defaults (e.g., paddles
  unbound; EmuDeck binds no back buttons anywhere)

Per-family/brand improvements beyond EmuDeck's behaviour ship **disabled** and
are surfaced as suggestions.

## Sources

- Templates: [`configs/`](https://github.com/dragoonDorise/EmuDeck/tree/dddb30229adbbd54d5ff7283cfd70e11c4322c26/configs) at `dddb302`
- Copy/reset logic and layout swaps: [`functions/EmuScripts/`](https://github.com/dragoonDorise/EmuDeck/tree/dddb30229adbbd54d5ff7283cfd70e11c4322c26/functions/EmuScripts) (`emuDeckDolphin.sh`, `emuDeckPCSX2QT.sh`, `emuDeckDuckStation.sh`, `emuDeckRetroArch.sh`), `functions/configEmuFP.sh`, `functions/configEmuAI.sh`, `controllerLayout_ABXY`/`_BAYX` in `functions/helperFunctions.sh`
- AutoMap: [`tools/gamepads/dolphinGamepads.py`](https://github.com/dragoonDorise/EmuDeck/blob/dddb30229adbbd54d5ff7283cfd70e11c4322c26/tools/gamepads/dolphinGamepads.py)
- GUI defaults: [`EmuDeck/emudeck-electron` `src/renderer/App.tsx`](https://github.com/EmuDeck/emudeck-electron/blob/b06bfcf5270f750c27b959dc3bca25425c99513c/src/renderer/App.tsx) at `b06bfcf`
