# map-helper Decky plugin

The Game Mode face of map-helper. In the Quick Access menu it shows what the
game you launched last got: the game, system, emulator and core, whether the
mappings were applied, each player's controller, and who counts as player 1.
**Show button map** opens a full-screen page with one tab per player: the pad
drawn in its own shape, every button labelled with the pad's glyph and coloured
by where its mapping comes from (your rule, the emulator's default, EmuDeck),
what each one does in the game, and the buttons only Steam sees (back buttons,
paddles, touchpad click). Everything works with the D-pad and A/B; L1/R1 switch
players on the button map.

On the button map only the list of buttons takes focus: the D-pad moves up and down it, the drawing and the card
follow, L1/R1 switch players, B goes back, ≡ opens the menu (rules list, undo, resets) and Y undoes the last
change; Steam's footer names them. The header's buttons and tabs answer to touch.

To change a mapping, press A on a button (**Change button**, or **Assign** for one that does nothing) and press
the button you want, while the console's pad (N64 so far) shows the input being changed lit beside yours. One
screen then says what happens ("N64 A moves from A to Y"), swaps the two buttons when the one you pressed already
had a job (or keeps both), previews what changes for the controllers connected now, and saves with one of three
buttons: this game, all the system's games, or only this controller. The rule goes in
`~/.local/share/map-helper/rules` and applies the next time a game starts. X on a button one of your rules set is
**Back to default**. Every change is undone with Y. The resets in ≡ turn rules off rather than delete them.
**Your rules** (in the Quick Access panel and ≡) lists every rule with an on/off switch, including the ones parked
in `~/.local/share/map-helper/rules-off`.

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
│   ├── rulesPage/     the rules list (/map-helper/rules)
│   ├── backend.ts     the last-launch call, and the dev fixture switch
│   ├── rules.ts       the rule calls: list, targets, edit (with preview), on/off, delete, reset, system logo
│   ├── glyphs.tsx     Kenney glyphs per pad style, controller icons
│   ├── data.ts        the show JSON (schema 1) and the backend's answer, typed
│   ├── format.ts      game titles, program names, source words, times
│   ├── strings.ts     every user-visible string
│   └── styles.tsx     colours and CSS
├── assets/kenney/     the Kenney Input Prompts SVGs the plugin uses, and their License.txt (CC0)
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

The rule calls run `map-helper rules ... --json` the same way (the core checks every op and every rule it writes,
and writes only in `rules/` and `rules-off/`): `get_rules()`, `get_targets(system)`, `edit_rules(ops, dry_run)`
(20 s: it previews by running the launch pipeline before and after), `set_rules_on(ids, on)`, `delete_rules(ids)`
and `reset_rules(system, game, dry_run)`. A refused change comes back as `code: "refused"` with the core's reason.
`get_system_logo(system)` reads the active theme's name from `~/ES-DE/settings/es_settings.xml` and returns
`~/ES-DE/themes/<theme>/_inc/systems/logos/<system>.svg` (or `.png`) as a data URL; with no such file the header
names the system instead. No logo ships with the plugin.

## Developing against the Deck

From the repo root, with developer mode on and the plugin installed once from the zip:

```sh
tools/deck.sh plugin                    # build, copy dist/index.js and main.py over, reload backend + frontend
tools/deck.sh ui nav /map-helper/map    # open a route
tools/deck.sh shot out.png              # screenshot Big Picture (854x534 CSS px; Steam's UI is at 1.5x)
tools/deck.sh ui eval 'JS'              # evaluate in SharedJSContext (window.DFL, DeckyPluginLoader, ...)
```

`tools/cdp.py` is the client: stdlib Python, run on the Deck, where Steam's CEF debugger listens on localhost.

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

