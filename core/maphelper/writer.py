"""Safe application of adapter patches to emulator config files. See docs/09.

Prototype scope: managed-key enforcement, pristine snapshot, no-op skip, atomic
replace, a unified diff for --dry-run, and (when the emulator is named) the touched-file manifest that
`restore` works from. The journal, drift hashes and the emulator-running check are still to do (docs/09 steps 3, 7,
8); mh-run takes the lock (step 2).

Writing is in two phases so a caller with a deadline (mh-run) can stop without leaving a half-written set: every
changed file is first staged, complete and fsynced, as a temp file next to it; then `gate()` decides; only then are
the temp files renamed over the originals. A cut-off before the gate writes nothing; after it, only renames are left.
"""

from __future__ import annotations

import difflib
import fnmatch
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .formats.ini import IniDocument


@dataclass(frozen=True)
class Patch:
    file: str        # relative to the emulator's config root
    section: Optional[str]   # None: top of the file, for formats without sections
    key: str
    value: str


@dataclass
class ApplyResult:
    changed_files: list = field(default_factory=list)
    diff: str = ""
    rejected: list = field(default_factory=list)   # patches outside managed keys
    aborted: bool = False                           # the gate said no: nothing was written


def is_managed(patch: Patch, managed: dict) -> bool:
    """managed = {"GCPadNew.ini": {"sections": "GCPad{n}", "keys": ["Buttons/*", "Main Stick/Up|Down", ...]}}.
    A file with several managed sections (PCSX2.ini: Pad{n} and Hotkeys) gives a list of such specs."""
    spec = managed.get(patch.file)
    if isinstance(spec, list):
        return any(is_managed(patch, {patch.file: s}) for s in spec)
    if not spec:
        return False
    sections = spec.get("sections") or spec.get("section")
    if sections is None:                               # a sectionless file (RetroArch .rmp): top-level keys only
        if patch.section is not None:
            return False
    elif patch.section is None or not fnmatch.fnmatchcase(patch.section, sections.replace("{n}", "[1-9]")):
        return False
    patterns = list(spec.get("keys", [])) + list(spec.get("option_keys", []))
    return any(fnmatch.fnmatchcase(patch.key, p) for p in _expand(patterns))


def _expand(patterns: list) -> list:
    """'Main Stick/Up|Down' -> ['Main Stick/Up', 'Main Stick/Down']."""
    out = []
    for p in patterns:
        prefix, _, alts = p.rpartition("/")
        if "|" in alts:
            out += [f"{prefix}/{a}" if prefix else a for a in alts.split("|")]
        else:
            out.append(p)
    return out


def apply_patches(config_root: Path, patches: list, managed: dict, state_dir: Path | None = None,
                  dry_run: bool = False, emulator: str | None = None,
                  gate: Optional[Callable[[], bool]] = None,
                  rewritten: Optional[Callable[[Path, str, dict], bool]] = None,
                  seeds: Optional[dict] = None) -> ApplyResult:
    """With state_dir and emulator, every write is recorded in the manifest (MANIFEST) so `restore` can undo it.
    gate: called once every changed file is staged; False discards the staged files and writes nothing
    (result.aborted). rewritten: the emulator's test for a created file it only saved over itself (see still_ours).
    seeds: {rel: seed_rel}, both under config_root. A file in it that doesn't exist yet starts as a copy of seed_rel
    (empty when that's missing too): the copy is its "before", so only managed keys may differ from the seed. It's
    still a created file, and restore deletes it."""
    result = ApplyResult()
    track = state_dir is not None and emulator is not None and not dry_run
    manifest = load_manifest(Path(state_dir)) if track else None
    if track:
        tracked = manifest.setdefault(emulator, {"config_root": str(Path(config_root).resolve()), "files": {}})
        if tracked["config_root"] != str(Path(config_root).resolve()):
            raise RuntimeError(f"{emulator}: {state_dir} already tracks the config at {tracked['config_root']}; "
                               f"restore it first or use another --state-dir. Nothing written")
    by_file: dict[str, list] = {}
    for patch in patches:
        if is_managed(patch, managed):
            by_file.setdefault(patch.file, []).append(patch)
        else:
            result.rejected.append(patch)

    diffs, outputs = [], []
    for rel, file_patches in sorted(by_file.items()):
        path = Path(config_root) / rel
        seed = None if path.exists() else (seeds or {}).get(rel)
        source = path if seed is None else Path(config_root) / seed
        before = source.read_text(encoding="utf-8", errors="surrogateescape") if source.is_file() else ""
        doc = IniDocument.parse(before)
        for p in file_patches:
            doc.set(p.section, p.key, p.value)
        after = doc.serialize()
        if after == before:
            continue                                   # no-op: don't touch the file or its mtime
        # Belt and braces for "never write outside managed keys": whatever the editor did, every other line must come
        # back unchanged. A parser bug fails here instead of silently rewriting a user's config.
        keys = {(p.section, p.key) for p in file_patches}
        old = IniDocument.parse(before)
        if old.untouched_lines(keys) != IniDocument.parse(after).untouched_lines(keys, set(old.sections())):
            raise RuntimeError(f"{rel}: the edit would change lines outside managed keys; nothing written")
        diffs.append("".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{seed or rel}", tofile=f"b/{rel}")))
        result.changed_files.append(rel)
        entry = tracked["files"].get(rel) if track else None
        written = None
        if track and (entry["created"] if entry else not path.exists()):   # only created files need it (still_ours)
            written = sorted([s, k, v] for (s, k), v in IniDocument.parse(after).index().items()
                             if is_managed(Patch(rel, s, k, v), managed))
        outputs.append((rel, path, after, written))
    result.diff = "".join(diffs)
    if not dry_run and outputs:
        ours = lambda rel, entry: still_ours(rewritten, Path(config_root), rel, entry)
        _commit(outputs, Path(state_dir) if state_dir is not None else None, emulator,
                (manifest, tracked) if track else None, gate, result, ours)
    return result


def _commit(outputs: list, state_dir: Optional[Path], emulator: Optional[str], track: Optional[tuple],
            gate: Optional[Callable[[], bool]], result: ApplyResult, ours: Callable[[str, dict], bool]) -> None:
    staged = []
    try:
        for rel, path, after, _ in outputs:
            staged.append((rel, path, _stage(path, after)))
        if gate is not None and not gate():
            result.aborted = True
            return
        if state_dir is not None:
            # Snapshots and manifest entries first: if the renames below are cut short, restore still knows every
            # file (one whose hash no longer matches is skipped unless --force, never lost).
            for rel, path, _ in staged:
                _snapshot_pristine(path, state_dir, rel, emulator, track[1]["files"] if track else None, ours)
            if track:
                save_manifest(state_dir, track[0])
        for rel, path, tmp in staged:
            os.replace(tmp, path)
        staged = []
        if track:
            for rel, path, _, written in outputs:
                entry = track[1]["files"][rel]
                entry["hash"] = file_hash(path)
                if entry["created"] and written is not None:
                    entry["managed"] = written   # for still_ours: what the emulator's own save should keep
            save_manifest(state_dir, track[0])
    finally:
        for _, _, tmp in staged:
            if os.path.exists(tmp):
                os.unlink(tmp)


MANIFEST = "touched.json"   # in the state dir: {emulator: {"config_root": abs, "files": {rel: {"created", "hash"}}}}
                            # created files also keep "managed": [[section, key, value], ...] as last written


def still_ours(rewritten: Optional[Callable[[Path, str, dict], bool]], config_root: Path, rel: str,
               entry: dict) -> bool:
    """A file map-helper created whose hash changed may only have been saved over by the emulator itself (RetroArch
    saves the loaded remap on quit). rewritten(config_root, rel, written), from the emulator's registry entry, says
    so, given the managed values map-helper last wrote ((section, key) -> value). Manifests from before those values
    were recorded can't tell, so the file counts as replaced."""
    written = entry.get("managed")
    return bool(rewritten and entry["created"] and written is not None
                and rewritten(Path(config_root), rel, {(s, k): v for s, k, v in written}))


def file_hash(path: Path) -> Optional[str]:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def load_manifest(state_dir: Path) -> dict:
    path = Path(state_dir) / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_manifest(state_dir: Path, manifest: dict) -> None:
    _atomic_write(Path(state_dir) / MANIFEST, json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def pristine_path(state_dir: Path, emulator: Optional[str], rel: str) -> Path:
    """$STATE/backups/pristine/<emulator>/<rel> (docs/09); snapshots taken before the manifest existed have no
    emulator directory, and are used when present."""
    legacy = Path(state_dir) / "backups" / "pristine" / rel
    if emulator is None or legacy.is_file():
        return legacy
    return Path(state_dir) / "backups" / "pristine" / emulator / rel


def _snapshot_pristine(path: Path, state_dir: Path, rel: str, emulator: Optional[str] = None,
                       files: Optional[dict] = None,
                       ours: Callable[[str, dict], bool] = lambda rel, entry: False) -> None:
    """First touch only: keep the file as it was before map-helper ever changed it. files: the manifest's entries
    for this emulator; a file that didn't exist is recorded as created, since there's nothing to snapshot.
    ours(rel, entry): a changed created file is still map-helper's (still_ours)."""
    target = pristine_path(state_dir, emulator, rel)
    if files is not None:
        entry = files.get(rel)
        if entry is None:
            files[rel] = {"created": not path.exists(), "hash": None}
        elif entry["created"] and path.exists() and file_hash(path) != entry["hash"] and not ours(rel, entry):
            # Someone else replaced a file we created (EmuDeck's abxy toggle renames Snes9x.rmp.disabled over
            # Snes9x.rmp), so it's theirs now: its content becomes the pristine one and restore won't delete it.
            entry["created"] = False
            _copy(path, target)
            return
    if target.exists() or not path.exists():
        return
    _copy(path, target)


def _copy(src: Path, target: Path) -> None:
    """copy2 through a temp file, so a snapshot cut short never stands in for the real one."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.mh-tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_write(path: Path, text: str) -> None:
    tmp = _stage(path, text)
    try:
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _stage(path: Path, text: str) -> str:
    """Write text to a temp file next to path (same mode), fsynced; the caller renames it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".mh-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return tmp
