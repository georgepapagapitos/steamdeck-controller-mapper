# 09 — Storage, Safety & Sync

## Locations (XDG)

| Var | Default | Contents |
|-----|---------|----------|
| `$DATA` | `~/.local/share/map-helper/` | `rules/*.json`, `devices.json`, `packs/`, `settings.json` |
| `$STATE` | `~/.local/state/map-helper/` | `touched.json`, `journal/`, `backups/`, `logs/`, `locks/`, `hashes.json`, `last-launch.json` |
| `$INSTALL` | `~/.local/lib/map-helper/current` (symlink to a versioned dir) + shims in `~/.local/bin`; the Decky plugin dir only holds the UI and installs/updates this ([14](14-packaging-permissions.md)) | code, `data/` (controller DB, layouts, shipped defaults) |

Everything in `$DATA` is user-owned and portable. `$STATE` is machine-specific
and safe to delete, though deleting it loses backups.

## Rule file format

- One rule per file (`rules/<id>.json`), or a bundle (`rules/<name>.bundle.json` with `"rules": [...]`). One file per rule keeps sync conflicts small.
- Validated against `schema/rule.schema.json` on load. An invalid file is skipped with a warning; the rest still loads.
- Each edit bumps `revision` and writes the previous version to `$STATE/history/<id>/<rev>.json` (last 20 kept).

## Writing emulator configs safely

1. **Pristine snapshot.** The first time we touch a file, copy it to
   `$STATE/backups/pristine/<emulator>/<relpath>`, and record the file in `$STATE/touched.json` (below). A file that
   doesn't exist yet has nothing to snapshot, so it's recorded as `created`. We never overwrite the snapshot unless
   the user re-baselines or an EmuDeck reset is detected. An adapter can ask for a new file to start as a copy of
   another (the writer's `seeds`, `{file: seed file}`): RetroArch's game options file starts from the file RetroArch
   would otherwise load ([adapters/retroarch.md](adapters/retroarch.md) "Core options"). The copy is the new file's
   "before", so only managed keys may differ from it, and the file is still `created`.
2. **Lock.** `flock $STATE/locks/<emulator>.lock`, non-blocking: mh-run skips the apply if it's held (implemented in mh-run).
3. **Is the emulator running?** If so, abort (the emulator would overwrite us
   on exit anyway). Check `/proc/*/exe` / cmdline for known binaries, including Flatpak `bwrap` children. **[VERIFY]**
4. **Read → patch → serialize with a round-trip parser.** Only managed keys
   change. Formatting, comments, ordering and unknown keys are preserved.
5. **No-op check.** If the output is byte-identical, skip the write entirely and don't touch the mtime.
6. **Atomic write.** Write to `file.mh-tmp` in the same directory, `fsync`, then `rename`, keeping the mode and owner.
   Every changed file is staged this way before any is renamed, with a gate in between, so mh-run can stop at
   its deadline without leaving a half-written file or a half-applied set (implemented; [07](07-launch-integration.md)).
7. **Journal entry.** Record `{ts, emulator, file, before_hash, after_hash, managed_hash, rule_trace_ref}` to `$STATE/journal/YYYY-MM.jsonl`.
8. **Managed hash.** Hash only the managed keys' values after the write, and store it in `hashes.json`. This is what drift detection uses.

### Drift detection

At the next apply: read the current managed keys and hash them. If the hash ≠
the stored hash, someone else changed them (the emulator UI, EmuDeck, or the
user by hand). Then:
- Small diff (some managed keys changed) → **drift**: queue the UX in [08 Flow 5](08-ui-ux.md). Apply the policy (`prefer-mine` by default).
- Large diff (most of the file, including non-managed keys) → probably an **EmuDeck reset or emulator upgrade**: re-baseline the pristine snapshot (keeping the old one as `pristine.prev`), then apply.

### The touched-file manifest

`$STATE/touched.json` lists every file map-helper has written, per emulator (implemented):

```json
{"retroarch": {"config_root": "/home/deck/.var/app/org.libretro.RetroArch/config/retroarch",
               "files": {"config/remaps/Snes9x/Snes9x.rmp": {"created": true, "hash": "<sha256>",
                         "managed": [[null, "input_player1_btn_a", "\"0\""], [null, "input_player1_btn_b", "\"8\""]]}}}}
```

- `created`: the file didn't exist before map-helper wrote it (EmuDeck ships only `Snes9x.rmp.disabled`), so its
  pristine state is "absent".
- `hash`: the sha256 of what map-helper last left there (`null` when that is "absent"). A file whose hash no longer
  matches was changed by someone else since.
- `managed` (created files only): `[section, key, value]` for every managed key, as map-helper last wrote it.
  Manifests from before it was recorded still load; they just can't tell the emulator's own save apart (next item).
- If a file we created turns up with other content at the next apply (EmuDeck's abxy toggle renames
  `.rmp.disabled` over our `.rmp`), it's theirs now: its content becomes the pristine snapshot and `created` is
  cleared, so restore puts it back instead of deleting it. The exception is the emulator saving our file over
  itself: RetroArch writes the loaded remap back on quit when `remap_save_on_exit` is on, and flushes the loaded
  core options file when content closes. The emulator's registry
  entry (`rewritten` in `pipeline.EMULATORS`) decides from `managed`; for RetroArch the test and its sources are in
  [adapters/retroarch.md](adapters/retroarch.md) ("Load precedence and save behaviour", "Core options"). Then the file stays
  `created`, apply writes over it, and restore deletes it, even when no apply ran since the save.
- One config root per emulator per state dir; apply refuses a second one.

Snapshots taken before the manifest existed sit at `backups/pristine/<relpath>` (no emulator directory) and are
still used.

### Backup and restore (implemented)

`map-helper backup [--name N]` copies every file in the manifest, as it is now, to `$STATE/backups/<N>/<emulator>/
<relpath>`, with `backup.json` recording which ones existed. The default name is the local time
(`20261022-153000`); `pristine` is reserved. `backup --list` lists them.

`map-helper restore [--emulator E] [--from N] [--dry-run] [--force]` walks the manifest (only that emulator's part
with `--emulator`) and, per file, works out the wanted state: the backup's copy if `--from N` has the file (or
"absent" if it was absent then), otherwise pristine (the snapshot, or "absent" for a created file; a file the backup
doesn't list was untouched when it was taken). Then:

- already the wanted content: nothing to do;
- current hash ≠ the manifest's hash: **skipped** with a message, since someone else owns the change, unless
  `--force`;
- wanted "absent": deleted; otherwise rewritten atomically from the copy, byte for byte.

It only ever deletes paths in the manifest, and refuses any that resolve outside the emulator's config root. The
manifest keeps every entry, with the hash updated to what restore left, so a later apply or restore still knows the
file. `--dry-run` prints the same list and changes nothing. Exit 1 if anything was skipped. Directories the writer
created for a file are left in place.

### Generated files we own outright

Profiles we create (e.g. `Profiles/GCPad/map-helper-<hash>.ini`,
`inputprofiles/map-helper-*.ini`, RetroArch `.rmp` files) have a header
comment, where the format allows it, saying they are managed and will be
overwritten. Uninstall deletes them.

### Uninstall

`--restore pristine`: put back the pristine snapshots (warning about any file
changed by EmuDeck since). This is `map-helper restore` above.
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
