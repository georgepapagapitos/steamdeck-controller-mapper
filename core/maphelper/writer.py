"""Safe application of adapter patches to emulator config files. See docs/09.

Prototype scope: managed-key enforcement, pristine snapshot, no-op skip, atomic
replace, a unified diff for --dry-run, and (when the emulator is named) the touched-file manifest that
`restore` works from. Locking, the journal, drift hashes and the emulator-running check are still to do (docs/09
steps 2, 3, 7, 8).
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
from typing import Optional

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
                  dry_run: bool = False, emulator: str | None = None) -> ApplyResult:
    """With state_dir and emulator, every write is recorded in the manifest (MANIFEST) so `restore` can undo it."""
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

    diffs = []
    for rel, file_patches in sorted(by_file.items()):
        path = Path(config_root) / rel
        before = path.read_text(encoding="utf-8", errors="surrogateescape") if path.exists() else ""
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
            fromfile=f"a/{rel}", tofile=f"b/{rel}")))
        result.changed_files.append(rel)
        if not dry_run:
            if state_dir is not None:
                _snapshot_pristine(path, Path(state_dir), rel, emulator, tracked["files"] if track else None)
            _atomic_write(path, after)
            if track:
                tracked["files"][rel]["hash"] = file_hash(path)
                save_manifest(Path(state_dir), manifest)
    result.diff = "".join(diffs)
    return result


MANIFEST = "touched.json"   # in the state dir: {emulator: {"config_root": abs, "files": {rel: {"created", "hash"}}}}


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
                       files: Optional[dict] = None) -> None:
    """First touch only: keep the file as it was before map-helper ever changed it. files: the manifest's entries
    for this emulator; a file that didn't exist is recorded as created, since there's nothing to snapshot."""
    target = pristine_path(state_dir, emulator, rel)
    if files is not None:
        entry = files.get(rel)
        if entry is None:
            files[rel] = {"created": not path.exists(), "hash": None}
        elif entry["created"] and path.exists() and file_hash(path) != entry["hash"]:
            # Someone else replaced a file we created (EmuDeck's abxy toggle renames Snes9x.rmp.disabled over
            # Snes9x.rmp), so it's theirs now: its content becomes the pristine one and restore won't delete it.
            entry["created"] = False
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            return
    if target.exists() or not path.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _atomic_write(path: Path, text: str) -> None:
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
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
