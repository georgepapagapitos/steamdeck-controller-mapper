# Contributing

## Running the prototype

Python 3.11+ and nothing else. There are no dependencies.

```bash
# tests
python3 -m unittest discover -s tests -t .

# CLI (run from core/, or put core/ on PYTHONPATH)
cd core
python3 -m maphelper validate ../examples
python3 -m maphelper explain --system gc --emulator dolphin --game GALE01 \
    --vid-pid 054c:09cc --device-id mac:aa:bb:cc:dd:ee:ff
python3 -m maphelper devices --proc-file /proc/bus/input/devices   # on Linux / a Deck

# write Dolphin's config for P1 = DS4, P2 = Xbox pad, launching Melee (prints a diff; add --write to apply)
cp -r ../tests/fixtures/dolphin/emudeck-default /tmp/dolphin-demo
python3 -m maphelper apply --emulator dolphin --system gc --game GALE01 \
    --config-root /tmp/dolphin-demo --player sony.ds4.v2@mac:aa:bb:cc:dd:ee:ff --player ms.xbox-one

# undo: every file map-helper wrote goes back to pristine, files it created are deleted (--state-dir as for apply)
python3 -m maphelper backup --name before-melee      # or no --name for a timestamp; --list shows them
python3 -m maphelper restore --dry-run               # what would change
python3 -m maphelper restore --emulator dolphin      # or all emulators; --from before-melee for a backup
```

Everything above runs the same on macOS, Linux and Windows. On Windows, use Git Bash (the shell scripts in
`tools/` need it). Git checks every file out with LF line endings (`.gitattributes`), so fixtures and goldens
compare byte for byte on every OS.

## Working with a Steam Deck

Write and test code on your own machine, then ship it to the Deck over ssh. Don't develop on the Deck itself:
SteamOS's root filesystem is read-only and gets replaced on every update. One-time setup, in Desktop Mode on the Deck:

```bash
passwd                              # give the deck user a password
sudo systemctl enable --now sshd
```

Then, from the Mac or Git Bash on Windows, run `ssh-copy-id deck@steamdeck` (or the Deck's IP), and:

```bash
export DECK_HOST=deck@192.168.0.50     # only if deck@steamdeck doesn't resolve
tools/deck.sh run devices               # copy the core over and list the controllers the Deck sees
tools/deck.sh capture ds4-bt-steam-input  # dump devices + emulator configs into tests/fixtures/*/ds4-bt-steam-input/
tools/deck.sh ssh
```

`capture` is read-only on the Deck. It redacts MACs and blanks emulator credentials before anything leaves the
device; check the diff anyway before committing.

Regenerate golden files after an intended output change with
`UPDATE_GOLDEN=1 python3 -m unittest discover -s tests -t .`, and review the diff.

## Ground rules

1. **Core stays stdlib-only** ([ADR-002](docs/adr/002-python-stdlib-core.md)). Dev tools (ruff, mypy) are fine; runtime imports are not.
2. **Every emulator fact needs a source.** Adapter docs and `data/adapters/*.json` cite the emulator source file or a captured fixture. If you can't cite something, tag it **[VERIFY]**.
3. **Never write outside managed keys.** Adapters declare their managed keys, and the writer refuses everything else.
4. **Fail open.** Nothing in the launch path may stop an emulator from starting.
5. **Fixtures are real files.** Don't hand-edit fixtures. Capture them, and record where they came from in `tests/fixtures/README.md`.
6. No AI-tool attribution in commits, PRs, code or docs.

## Adding an emulator

1. Copy [docs/adapters/_template.md](docs/adapters/_template.md) to `docs/adapters/<id>.md` and fill it in with sources.
2. Capture fixtures (EmuDeck default + "user changed bindings in the emulator UI") under `tests/fixtures/<id>/<version>/`.
3. Add the naming table `data/adapters/<id>.json` (see the Dolphin one for the shape).
4. Implement `core/maphelper/adapters/<id>.py` against the adapter contract in [docs/06](docs/06-emulator-adapters.md).
5. Add golden tests: fixture + resolution → expected file.

## Adding a controller

Add or extend entries in `data/controllers.json` (brand → family → model, with
VID:PIDs and capabilities). Cite a source for every VID:PID (SDL `controller_list.h`, kernel `hid-ids.h`, or a device dump). If a pad impersonates
another vendor in some mode, set `"ambiguous": true` on the impersonated model and add the real model so users can claim it.

## Commit style

Short imperative subject (`Add Cemu adapter`), with a body explaining *why* when it isn't obvious.
