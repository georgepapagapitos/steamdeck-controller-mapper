# map-helper Decky plugin

The Game Mode face of map-helper. In the Quick Access menu it shows what the
game you launched last got: the game, system, emulator and core, whether the
mappings were applied, each player's controller, and who counts as player 1.
**Show button map** opens a full-screen page with one tab per player: the pad
drawn in its own shape, every button labelled with the pad's glyph and coloured
by where its mapping comes from (your rule, the emulator's default, EmuDeck),
what each one does in the game, and the buttons only Steam sees (back buttons,
paddles, touchpad click). Everything works with the D-pad and A/B; L1/R1 switch
players on the button map. Editing ("Change button") is not built yet.

The data is `map-helper show --last --json`, which prints
`~/.local/state/map-helper/last-launch.json`, written by `mh-run` at every
launch it handles (docs/08, "The data"). The plugin doesn't install the core;
until it does, install it with `tools/deck.sh install` from a computer.

Removing the plugin leaves the launch hook and the `map-helper` CLI working;
`map-helper uninstall` removes them.

## Layout

```
decky/
├── plugin.json, package.json, pnpm-lock.yaml, rollup.config.js, tsconfig.json
├── main.py            backend: runs the core on /usr/bin/python3, never as root
├── src/
│   ├── index.tsx      definePlugin: QAM panel + the /map-helper/map route
│   ├── panel/         Quick Access panel
│   ├── map/           button map: drawing, shapes, list, detail card, strip, chips
│   ├── backend.ts     the one backend call, and the dev fixture switch
│   ├── data.ts        the show JSON (schema 1) and the backend's answer, typed
│   ├── format.ts      game titles, program names, source words, times
│   ├── strings.ts     every user-visible string
│   └── styles.tsx     colours and CSS
├── dev/               fixture data for development (never shipped)
├── TEMPLATE-LICENSE   decky-plugin-template's BSD-3-Clause notice
└── package.sh         build + out/map-helper.zip
```

## Backend

`get_last_launch()` runs

```
/usr/bin/python3 -I ~/.local/lib/map-helper/current/mh_entry.py show --last --json
```

with a 5 s timeout and a minimal environment, and returns either
`{"ok": true, "data": <show JSON>}` or
`{"ok": false, "code": <code>, "error": "<plain words>"}`, where `code` is
`not-installed`, `no-launch`, `no-python`, `timeout`, `bad-output` or `failed`.
It never raises into the frontend; problems go to the plugin log
(`~/homebrew/logs/map-helper/`).

## Build

Needs Node 18+ with corepack (no global pnpm, no sudo). pnpm 9.15.9 comes from
`packageManager` in package.json.

```sh
cd decky
corepack pnpm install --frozen-lockfile
corepack pnpm run typecheck
corepack pnpm run build          # dist/index.js
./package.sh                     # all of the above, then out/map-helper.zip
```

`package.sh` runs on macOS and in Git Bash on Windows (it zips with
`python3`). The zip holds `map-helper/` with `dist/`, `package.json`,
`plugin.json`, `main.py`, `LICENSE` (the repo's GPL-3.0 on top, the template's
BSD-3-Clause notice below) and this README. There's no `py_modules/` yet.

## Seeing the UI without a launch

```sh
corepack pnpm run build:fixture                                   # answers with dev/last-launch.json
corepack pnpm exec rollup -c --environment MH_FIXTURE:no-launch   # or any dev/responses/<name>.json
```

A fixture build never calls the backend; it answers with the file instead and
shows a "Sample data" banner on both screens. `dev/last-launch.json` is the show
engine's golden output for Ocarina of Time (`tests/golden/show/n64-ocarina.json`
on the `show` branch): four players (Switch Pro, 8BitDo Ultimate 2, DualSense,
Steam Deck), N64 layout 1, rumble pak and a 5% deadzone. `dev/responses/` holds
the error answers. `package.sh` always makes a real build and refuses a bundle
that contains sample data, so a fixture build can't end up in the zip.

## Installing on the Deck for testing

Copying into `~/homebrew/plugins` needs root, so use Decky's developer mode:

1. Decky settings (the gear in Decky's Quick Access tab) → General →
   **Developer mode** on.
2. Copy `out/map-helper.zip` to the Deck (e.g. `scp out/map-helper.zip
   deck@steamdeck:~/Downloads/`).
3. Decky settings → Developer → **Install plugin from ZIP file** → pick it.
   Decky unpacks it into `~/homebrew/plugins/map-helper` and starts it.

Reinstalling the same way replaces it. Steam's CEF console
(`http://<deck>:8081` from a computer, with CEF remote debugging on in Decky's
developer settings) shows the frontend's errors; the backend logs to
`~/homebrew/logs/map-helper/`.

