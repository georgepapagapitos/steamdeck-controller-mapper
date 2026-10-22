"""Safe application of adapter patches to emulator config files. See docs/09.

Prototype scope: managed-key enforcement, pristine snapshot, no-op skip, atomic
replace, and a unified diff for --dry-run. Locking, the journal, drift hashes and
the emulator-running check are still to do (docs/09 steps 2, 3, 7, 8).
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .formats.ini import IniDocument


@dataclass(frozen=True)
class Patch:
    file: str        # relative to the emulator's config root
    section: str
    key: str
    value: str


@dataclass
class ApplyResult:
    changed_files: list = field(default_factory=list)
    diff: str = ""
    rejected: list = field(default_factory=list)   # patches outside managed keys


def is_managed(patch: Patch, managed: dict) -> bool:
    """managed = {"GCPadNew.ini": {"sections": "GCPad{n}", "keys": ["Buttons/*", "Main Stick/Up|Down", ...]}}."""
    spec = managed.get(patch.file)
    if not spec:
        return False
    sections = spec.get("sections") or spec.get("section", "")
    if not fnmatch.fnmatchcase(patch.section, sections.replace("{n}", "[1-9]")):
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
                  dry_run: bool = False) -> ApplyResult:
    result = ApplyResult()
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
        diffs.append("".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}")))
        result.changed_files.append(rel)
        if not dry_run:
            if state_dir is not None:
                _snapshot_pristine(path, Path(state_dir), rel)
            _atomic_write(path, after)
    result.diff = "".join(diffs)
    return result


def _snapshot_pristine(path: Path, state_dir: Path, rel: str) -> None:
    """First touch only: keep the file as it was before map-helper ever changed it."""
    target = state_dir / "backups" / "pristine" / rel
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
