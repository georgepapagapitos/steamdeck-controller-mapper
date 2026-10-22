# 09 — Storage, Safety & Sync

## Locations (XDG)

| Var | Default | Contents |
|-----|---------|----------|
| `$DATA` | `~/.local/share/map-helper/` | `rules/*.json`, `devices.json`, `packs/`, `settings.json` |
| `$STATE` | `~/.local/state/map-helper/` | `journal/`, `backups/`, `logs/`, `locks/`, `hashes.json`, `last-launch.json` |
| `$INSTALL` | `~/.local/lib/map-helper/current` (symlink to a versioned dir) + shims in `~/.local/bin`; the Decky plugin dir only holds the UI and installs/updates this ([14](14-packaging-permissions.md)) | code, `data/` (controller DB, layouts, shipped defaults) |

Everything in `$DATA` is user-owned and portable. `$STATE` is machine-specific
and safe to delete, though deleting it loses backups.

## Rule file format

- One rule per file (`rules/<id>.json`), or a bundle (`rules/<name>.bundle.json` with `"rules": [...]`). One file per rule keeps sync conflicts small.
- Validated against `schema/rule.schema.json` on load. An invalid file is skipped with a warning; the rest still loads.
- Each edit bumps `revision` and writes the previous version to `$STATE/history/<id>/<rev>.json` (last 20 kept).

## Writing emulator configs safely

1. **Pristine snapshot.** The first time we touch a file, copy it to
   `$STATE/backups/pristine/<emulator>/<relpath>` along with its hash. We never overwrite this unless the user re-baselines or an EmuDeck reset is detected.
2. **Lock.** `flock $STATE/locks/<emulator>.lock`.
3. **Is the emulator running?** If so, abort (the emulator would overwrite us
   on exit anyway). Check `/proc/*/exe` / cmdline for known binaries, including Flatpak `bwrap` children. **[VERIFY]**
4. **Read → patch → serialize with a round-trip parser.** Only managed keys
   change. Formatting, comments, ordering and unknown keys are preserved.
5. **No-op check.** If the output is byte-identical, skip the write entirely and don't touch the mtime.
6. **Atomic write.** Write to `file.mh-tmp` in the same directory, `fsync`, then `rename`, keeping the mode and owner.
7. **Journal entry.** Record `{ts, emulator, file, before_hash, after_hash, managed_hash, rule_trace_ref}` to `$STATE/journal/YYYY-MM.jsonl`.
8. **Managed hash.** Hash only the managed keys' values after the write, and store it in `hashes.json`. This is what drift detection uses.

### Drift detection

At the next apply: read the current managed keys and hash them. If the hash ≠
the stored hash, someone else changed them (the emulator UI, EmuDeck, or the
user by hand). Then:
- Small diff (some managed keys changed) → **drift**: queue the UX in [08 Flow 5](08-ui-ux.md). Apply the policy (`prefer-mine` by default).
- Large diff (most of the file, including non-managed keys) → probably an **EmuDeck reset or emulator upgrade**: re-baseline the pristine snapshot (keeping the old one as `pristine.prev`), then apply.

### Generated files we own outright

Profiles we create (e.g. `Profiles/GCPad/map-helper-<hash>.ini`,
`inputprofiles/map-helper-*.ini`, RetroArch `.rmp` files) have a header
comment, where the format allows it, saying they are managed and will be
overwritten. Uninstall deletes them.

### Uninstall

`--restore pristine`: put back the pristine snapshots (warning about any file
changed by EmuDeck since).
`--restore current` (default): remove only our managed keys and files, and
restore those keys to their pristine values. This keeps any unrelated changes
made since. Then remove the hooks and optionally `$DATA`.

## Export / import / sync

- **Export:** `.mhpack.json` holds selected rules + device registry entries (optional; device ids are personal) + metadata. Shareable.
- **Community packs:** the same format, installed into `$DATA/packs/<id>/`, read-only, with enable/disable. Packs can't contain `device`-level rules (meaningless to others). Model/family/brand/style rules are fine. Example: a "Fightstick essentials" pack with `style:arcade8` rules for every fighting-game system.
- **Sync between devices:** `$DATA` is a plain folder that works with Syncthing or Decky Cloud Save. The one-file-per-rule layout and `revision` fields make conflicts rare and easy to resolve.

## Privacy

Device ids contain BT MACs and serials. They stay local. Export strips them
unless the user asks to keep them. `doctor` bundles redact MACs.
