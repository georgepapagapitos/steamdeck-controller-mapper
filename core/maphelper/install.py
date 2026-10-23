"""`map-helper self-install`: put a payload (mh_entry.py, maphelper/, data/) under ~/.local/lib/map-helper. See
docs/14 §6.

    versions/<ver>/     one install each: mh_entry.py, maphelper/, data/
    current             symlink to versions/<ver>, swapped atomically (a new link renamed over the old one)
    install.json        {version, installed_by, ts, sha256, previous}

<ver> is maphelper's __version__ plus the first 8 hex digits of the tree's sha256 (e.g. 0.0.1+3f9c2a1b): the same
tree always lands in the same directory, so installing it again changes nothing, and any change to the code or data,
committed or not, gets a new one. No git is needed on the Deck. The previous version stays for a rollback; older
ones are removed.

The shims in ~/.local/bin aren't written here: `map-helper setup` owns them (setup.py), so uninstall knows exactly
what it wrote.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

from . import _BASE
from .writer import _atomic_write

RECORD = "install.json"
SKIP = {"__pycache__", ".DS_Store"}

# Run in the new tree by the Python the shims use: imports the launch path and every adapter (which load their
# tables), and prints where the data was found.
CHECK = ("import sys; sys.path.insert(0, sys.argv[1]); import maphelper, maphelper.cli, maphelper.mhrun; "
         "from maphelper.pipeline import EMULATORS; [e.adapter() for e in EMULATORS.values()]; print(maphelper.DATA)")


class InstallError(Exception):
    pass


def payload(src: Path) -> dict:
    """The payload's parts in src: an unpacked payload, or core/ in the repo (data/ one level up)."""
    src = Path(src).resolve()
    parts = {"mh_entry.py": src / "mh_entry.py", "maphelper": src / "maphelper",
             "data": src / "data" if (src / "data").is_dir() else src.parent / "data"}
    missing = [str(p) for p in parts.values() if not p.exists()]
    if missing:
        raise InstallError(f"{src} isn't a map-helper payload: no {', '.join(missing)}")
    return parts


def _skip(name: str) -> bool:
    return name in SKIP or name.endswith(".pyc")


def _files(parts: dict) -> Iterator[tuple[str, Path]]:
    for name, path in parts.items():
        if path.is_file():
            yield name, path
            continue
        for p in path.rglob("*"):
            rel = p.relative_to(path)
            if p.is_file() and not any(_skip(n) for n in rel.parts):
                yield f"{name}/{rel.as_posix()}", p


def tree_hash(parts: dict) -> str:
    """sha256 over every file's path and contents (bytecode caches left out), the same on every OS."""
    h = hashlib.sha256()
    for rel, path in sorted(_files(parts)):
        h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def _version(package: Path) -> str:
    m = re.search(r'^__version__ = "([^"]+)"', (package / "__init__.py").read_text(encoding="utf-8"), re.M)
    if not m:
        raise InstallError(f"no __version__ in {package / '__init__.py'}")
    return m.group(1)


def load_record(lib: Path) -> dict:
    path = Path(lib) / RECORD
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def current_version(lib: Path) -> Optional[str]:
    current = Path(lib) / "current"
    return Path(os.readlink(current)).name if current.is_symlink() else None


def install(src: Optional[Path], lib: Path, installed_by: str = "cli",
            python: str = sys.executable) -> tuple[str, bool]:
    """Install the payload in src (default: the one this code runs from); (version, whether anything changed).
    Safe to run again, and while a launch reads `current`: a version directory is complete before `current` can
    point at it, and the one it pointed at stays."""
    lib = Path(lib)
    parts = payload(src or _BASE)
    sha = tree_hash(parts)
    ver = f"{_version(parts['maphelper'])}+{sha[:8]}"
    versions, current = lib / "versions", lib / "current"
    if current.exists() and not current.is_symlink():
        raise InstallError(f"{current} isn't a symlink, so it isn't map-helper's install; move it away")
    target = versions / ver
    changed = False
    if not (target.is_dir() and tree_hash(payload(target)) == sha):
        tmp = versions / f"{ver}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        for name, path in parts.items():
            if path.is_file():
                shutil.copy2(path, tmp / name)
            else:
                shutil.copytree(path, tmp / name, ignore=lambda d, names: [n for n in names if _skip(n)])
        _verify(tmp, sha, python)
        if target.exists():                         # damaged (its files no longer match its name): set it aside
            aside = versions / f"{ver}.old"
            shutil.rmtree(aside, ignore_errors=True)
            os.replace(target, aside)
        os.replace(tmp, target)
        changed = True

    record = load_record(lib)
    before = current_version(lib)
    if before != ver:
        link = lib / f".current.{os.getpid()}"
        if link.is_symlink():
            link.unlink()
        os.symlink(f"versions/{ver}", link)
        os.replace(link, current)
        changed = True
    previous = before if before != ver else record.get("previous")
    if changed or record.get("version") != ver:
        _atomic_write(lib / RECORD, json.dumps({"version": ver, "installed_by": installed_by,
                                                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sha256": sha,
                                                "previous": previous}, indent=2, sort_keys=True) + "\n")
    for d in versions.iterdir():                    # keep this version and the one before it
        if d.name not in (ver, previous):
            if d.is_dir() and not d.is_symlink():
                shutil.rmtree(d)
            else:
                d.unlink()
    return ver, changed


def _verify(tree: Path, sha: str, python: str) -> None:
    if tree_hash(payload(tree)) != sha:
        raise InstallError(f"the copy in {tree} doesn't match the payload")
    run = subprocess.run([python, "-I", "-c", CHECK, str(tree)], capture_output=True, text=True, encoding="utf-8",
                         timeout=60)
    if run.returncode != 0:
        last = run.stderr.strip().splitlines()[-1:] or [f"exit {run.returncode}"]
        raise InstallError(f"the new install doesn't run: {last[0]}")
    if Path(run.stdout.strip()) != (tree / "data").resolve():
        raise InstallError(f"the new install finds its data in {run.stdout.strip()}, not {tree / 'data'}")


def remove(lib: Path, write: bool) -> Optional[str]:
    """Take out what self-install put in lib (versions/, current, install.json), and lib itself when that leaves it
    empty. Only with install.json there, the evidence it's ours; None when there's nothing of ours."""
    lib = Path(lib)
    record = load_record(lib)
    if not record:
        return None
    if write:
        current = lib / "current"
        if current.is_symlink():
            current.unlink()
        shutil.rmtree(lib / "versions", ignore_errors=True)
        (lib / RECORD).unlink()
        if not any(lib.iterdir()):
            lib.rmdir()
    return record.get("version", "?")

