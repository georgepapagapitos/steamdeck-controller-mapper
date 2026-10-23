# ADR-001: Apply mappings at launch time, by wrapping the launch command

**Status:** Accepted (revised after spike S5; mh-run and setup implemented)

## Context

Emulators read their input config at startup. We need our mappings on disk
before that happens, and they must reflect the controllers connected *now*.

Options considered: a background daemon reacting to hotplug, Decky app-launch
events, patching EmuDeck's launcher scripts, wrapping the launch command,
ES-DE event scripts, and an upstream EmuDeck hook.

The original decision was to patch EmuDeck's launchers. Spike S5 ruled that
out. Every EmuDeck launcher runs `git pull` on the EmuDeck backend and then
`launcherInit`, which restores all launchers from the backend
(`update_launchers`), and `emulatorInit` runs `git reset --hard`. A patch is
gone before it would run. EmuDeck also has no pre-launch hook mechanism.

Spike S5 also found that EmuDeck **AutoMap** (on by default for Dolphin, Cemu
and the Switch emulators) runs inside `emulatorInit`. It copies the stock
`GCPadNew.ini` over the user's file at every Dolphin launch, after any wrapper
we put in front of the launcher. See [07](../07-launch-integration.md).

## Decision

1. **Steam / SRM launches:** wrap the command. `mh-run --emulator <id> -- %command%`
   goes in the shortcut's launch options. `map-helper setup` puts it in every
   SRM parser for a managed emulator (`userConfigurations.json`), so it reaches
   Steam at the user's next "Save to Steam"; map-helper never writes
   `shortcuts.vdf`. Parsers that append their args to the Exe (RetroArch) are
   left alone: wrapping them would give their shortcuts new Steam app ids and
   lose per-shortcut settings and playtime (the owner's call, 2026-10-23;
   docs/07 "`map-helper setup` and `uninstall`").
2. **ES-DE launches:** an ES-DE `game-start` custom event script calls
   `mh-run --hook --es-de`, which works out the emulator and core from ES-DE's
   system commands and the gamelist's alternative emulator. setup installs the
   script and turns on `CustomEventScripts`. ES-DE launches RetroArch, PCSX2 and
   DuckStation directly, not through launchers.
3. **Turn off EmuDeck AutoMap** for every emulator map-helper manages.
   map-helper's setup reports it (it doesn't write EmuDeck's settings yet), and
   `doctor` warns if it's back on.
4. **Long term:** propose an upstream hook in EmuDeck that runs at the end of
   `emulatorInit` (after AutoMap). That is the one point where every frontend
   converges and EmuDeck's own writes are finished. Move to it once it ships.

## Consequences

- ➕ Deterministic: no race with the emulator's config read.
- ➕ No resident process; nothing in EmuDeck's tree is modified.
- ➖ Two integration points (Steam launch options, ES-DE events) instead of one.
- ➖ Depends on AutoMap being off. If EmuDeck re-enables it (e.g. on a settings
  reset), Dolphin bindings revert silently until `doctor`/the plugin notices.
- ➖ SRM regenerating shortcuts can drop launch options unless the parser config carries them.
- ➖ Launch latency budget (500 ms max, fail-open). A cut-off stops before the
  writer commits, so it never leaves a half-written file; the shim, not Python,
  starts the emulator, so nothing in map-helper can stop a launch (docs/07).
- ➖ RetroArch games launched from their SRM Steam shortcuts aren't wrapped (doing so would change those shortcuts' app ids); only ES-DE launches of RetroArch get mappings applied.
- ES-DE's `game-start` fires before the emulator starts and blocks until the
  script ends, per ES-DE's source (docs/07 Option E), confirmed on a Deck
  (2026-10-23: about 135 ms per launch). [VERIFY] that Steam runs
  `VAR=x <mh-run> --emulator <id> -- %command% <args>` launch options as
  expected.
