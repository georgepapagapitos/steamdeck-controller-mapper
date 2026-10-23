"""`backup` and `restore`: return the files map-helper has written to pristine or to a named backup. See docs/09.

Works only from the writer's manifest ($STATE/touched.json), so it never touches a file map-helper didn't write.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .writer import _atomic_write, file_hash, load_manifest, pristine_path, save_manifest, still_ours

BACKUP_INFO = "backup.json"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass
class Action:
    emulator: str
    rel: str
    kind: str                       # "write", "delete", "skip" or "ok" (already as wanted)
    reason: str
    content: Optional[bytes] = None  # what "write" puts there


def backups_dir(state_dir: Path) -> Path:
    return Path(state_dir) / "backups"


def list_backups(state_dir: Path) -> list[str]:
    root = backups_dir(state_dir)
    return sorted(p.parent.name for p in root.glob(f"*/{BACKUP_INFO}")) if root.is_dir() else []


def backup(state_dir: Path, name: Optional[str] = None) -> tuple[str, int]:
    """Copy every file in the manifest, as it is now, to $STATE/backups/<name>/<emulator>/<rel>. Returns
    (name, file count). Files that don't exist right now are recorded as absent."""
    manifest = load_manifest(state_dir)
    name = name or time.strftime("%Y%m%d-%H%M%S")
    if not NAME.fullmatch(name) or name == "pristine":
        raise ValueError(f"{name!r}: a backup name is letters, digits, '.', '_' and '-', and not 'pristine'")
    dest = backups_dir(state_dir) / name
    if dest.exists():
        raise ValueError(f"backup {name!r} already exists")
    files = {}
    for emulator, tracked in sorted(manifest.items()):
        for rel in sorted(tracked["files"]):
            src = Path(tracked["config_root"]) / rel
            files.setdefault(emulator, {})[rel] = {"exists": src.is_file()}
            if src.is_file():
                (dest / emulator / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest / emulator / rel)
    dest.mkdir(parents=True, exist_ok=True)
    _atomic_write(dest / BACKUP_INFO, json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "files": files},
                                                 indent=2, sort_keys=True) + "\n")
    return name, sum(len(f) for f in files.values())


def plan(state_dir: Path, emulator: Optional[str] = None, source: Optional[str] = None,
         force: bool = False) -> list[Action]:
    """What restore would do for each file in the manifest. source: a backup name; None means pristine.

    A file that's in the manifest but not in the backup was untouched when the backup was taken, so it goes back to
    pristine. A file whose content isn't what map-helper last left there belongs to someone else now (EmuDeck, the
    emulator's UI, the user) and is skipped unless force, except a created file the emulator only saved over itself
    (writer.still_ours)."""
    from .pipeline import EMULATORS
    state_dir = Path(state_dir)
    manifest = load_manifest(state_dir)
    if source is not None:
        info_path = backups_dir(state_dir) / source / BACKUP_INFO
        if not NAME.fullmatch(source) or not info_path.is_file():
            raise ValueError(f"no backup named {source!r}; see `backup --list`")
        saved = json.loads(info_path.read_text(encoding="utf-8"))["files"]
    actions = []
    for emu, tracked in sorted(manifest.items()):
        if emulator and emu != emulator:
            continue
        root = Path(tracked["config_root"]).resolve()
        rewritten = EMULATORS[emu].rewritten if emu in EMULATORS else None
        for rel, entry in sorted(tracked["files"].items()):
            path = root / rel
            act = lambda kind, reason, content=None: actions.append(Action(emu, rel, kind, reason, content))
            if Path(rel).is_absolute() or not path.resolve().is_relative_to(root):
                act("skip", f"outside the config root {root}; not touching it")
                continue
            in_backup = source is not None and rel in saved.get(emu, {})
            where = f"backup {source}" if in_backup else "pristine"
            if in_backup:
                exists = saved[emu][rel]["exists"]
                want = (backups_dir(state_dir) / source / emu / rel).read_bytes() if exists else None
            elif entry["created"]:
                want = None
            else:
                snapshot = pristine_path(state_dir, emu, rel)
                if not snapshot.is_file():
                    act("skip", "no pristine snapshot to restore from")
                    continue
                want = snapshot.read_bytes()
            have = path.read_bytes() if path.is_file() else None
            if have == want:
                act("ok", f"already as in {where}")
            elif file_hash(path) != entry["hash"] and not force and not still_ours(rewritten, root, rel, entry):
                act("skip", ("someone else changed or replaced it since map-helper last wrote it (EmuDeck, the "
                             "emulator or a manual edit); --force restores it anyway"))
            elif want is None:
                act("delete", f"map-helper created it; it doesn't exist in {where}")
            else:
                act("write", f"rewrite from {where}", want)
    return actions


def run(state_dir: Path, actions: list[Action]) -> None:
    """Carry out plan()'s writes and deletes, recording each result as what map-helper last left there."""
    manifest = load_manifest(state_dir)
    for a in actions:
        if a.kind not in ("write", "delete", "ok"):
            continue
        tracked = manifest[a.emulator]
        path = Path(tracked["config_root"]) / a.rel
        if a.kind == "write":
            # surrogateescape round-trips any bytes, so the file comes back exactly as snapshotted
            _atomic_write(path, a.content.decode("utf-8", errors="surrogateescape"))
        elif a.kind == "delete":
            path.unlink(missing_ok=True)
        tracked["files"][a.rel]["hash"] = file_hash(path)
        save_manifest(state_dir, manifest)
