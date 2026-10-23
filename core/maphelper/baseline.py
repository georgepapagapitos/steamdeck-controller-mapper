"""The config as it would be without map-helper's earlier writes, so a rule that's gone stops counting.

Rules set keys at a launch; nothing else does. Without this, a key a rule set once kept that value after the rule
was turned off, undone or deleted, and a game-scoped binding written into a shared file leaked into every other
game. So a launch renders on top of a baseline instead of the live files:

- a key map-helper wrote that still holds what it wrote reads as it was before map-helper (the pristine snapshot;
  absent when the snapshot lacks it), and one someone changed since (the emulator's UI, the user) reads as they
  left it;
- every key map-helper wrote in a file it created reads as absent, and the file as missing, while it's still ours
  (writer.still_ours: RetroArch's own save on exit doesn't make it someone else's).

finish() then turns what this launch's patches leave out into reverts: those keys go back to the baseline, and a
created file this launch writes nothing into is deleted. What map-helper wrote comes from the writer's manifest:
`ours` for files that existed, `managed` (all managed values last written) for created ones.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .formats.ini import IniDocument
from .writer import Patch, file_hash, load_manifest, pristine_path, still_ours


class Baseline:
    def __init__(self, current: Callable, config_root: Path, state_dir: Optional[Path], emulator: Optional[str],
                 rewritten: Optional[Callable] = None):
        self.current, self.root = current, Path(config_root)
        self.overrides: dict = {}      # (file, section, key) -> baseline value (None: absent)
        self.hidden: set = set()       # created files map-helper still owns
        tracked = load_manifest(Path(state_dir)).get(emulator) if state_dir and emulator else None
        if not tracked or tracked.get("config_root") != str(self.root.resolve()):
            return
        for rel, entry in tracked["files"].items():
            path = self.root / rel
            if not path.is_file():
                continue
            if entry.get("created"):
                written = entry.get("managed")
                if written is None or not (file_hash(path) == entry.get("hash")
                                           or still_ours(rewritten, self.root, rel, entry)):
                    continue                           # replaced by someone else: theirs now
                self.hidden.add(rel)
                for section, key, _ in written:
                    self.overrides[(rel, section or None, key)] = None
                continue
            ours = entry.get("ours") or []
            if not ours:
                continue
            snapshot = pristine_path(Path(state_dir), emulator, rel)
            pristine = (IniDocument.parse(snapshot.read_text(encoding="utf-8", errors="surrogateescape")).index()
                        if snapshot.is_file() else {})
            for section, key, value in ours:
                section = section or None
                if current(rel, section, key) == value:
                    self.overrides[(rel, section, key)] = pristine.get((section, key))

    def __call__(self, file: str, section: Optional[str], key: str) -> Optional[str]:
        if (file, section, key) in self.overrides:
            return self.overrides[(file, section, key)]
        return self.current(file, section, key)

    def exists(self, rel: str) -> bool:
        """Whether the file is there without map-helper: a created file it still owns isn't."""
        return rel not in self.hidden and (self.root / rel).is_file()

    def created(self, rel: str) -> bool:
        return rel in self.hidden

    def finish(self, patches: list, scope: Optional[set] = None) -> tuple:
        """(revert patches, files to delete) for what this launch's patches don't set again. scope: the files this
        launch answers for (RetroArch: the core's, the content folder's and this game's remap and options files);
        another game's remap is that game's business, so it's neither reverted nor deleted. None: every file."""
        inside = lambda f: scope is None or f in scope
        patched = {(p.file, p.section, p.key) for p in patches}
        files = {p.file for p in patches}
        deletes = sorted(f for f in self.hidden if f not in files and inside(f))
        reverts = [Patch(f, s, k, value, revert=True) for (f, s, k), value in sorted(
            self.overrides.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2]))
            if (f, s, k) not in patched and f not in deletes and inside(f)]
        return reverts, deletes


def passthrough(current: Callable, config_root: Path) -> Baseline:
    """No state dir (a bare `apply` without tracking): the live files, nothing hidden."""
    return Baseline(current, config_root, None, None)
