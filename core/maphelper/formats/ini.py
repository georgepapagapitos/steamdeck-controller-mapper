"""Round-trip-preserving INI editor.

configparser can't be used for writing: it drops comments, normalises spacing and
lower-cases keys. Emulator configs (Dolphin, PCSX2, DuckStation, ...) must come back
byte-identical except for the keys we change. See docs/02 "Language & runtime".
"""

from __future__ import annotations

import re
from typing import Optional

_SECTION = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_KEY = re.compile(r"^(?P<key>[^=;#\[][^=]*?)(?P<sep>\s*=\s*)(?P<value>.*)$")
# Only real line breaks. str.splitlines() also breaks on \f, \x1c-\x1e, \x85 and \u2028, which would split a value
# and write it back as two lines.
_BREAK = re.compile(r"(\r\n|\n)")


class IniDocument:
    def __init__(self, text: str = ""):
        self.newline = "\r\n" if "\r\n" in text else "\n"
        parts = _BREAK.split(text) if text else []
        self.lines = parts[0::2]
        self.endings = parts[1::2] + [""] * (len(self.lines) - len(parts[1::2]))  # each line's own break
        if len(self.lines) > 1 and self.lines[-1] == "" and self.endings[-1] == "":
            del self.lines[-1], self.endings[-1]  # text ended with a break

    @classmethod
    def parse(cls, text: str) -> "IniDocument":
        return cls(text)

    def serialize(self) -> str:
        return "".join(line + end for line, end in zip(self.lines, self.endings))

    # -- queries ---------------------------------------------------------------

    def sections(self) -> list[str]:
        return [m.group("name") for m in map(_SECTION.match, self.lines) if m]

    def get(self, section: Optional[str], key: str) -> Optional[str]:
        index = self._find_key(section, key)
        return None if index is None else _KEY.match(self.lines[index]).group("value")

    def items(self, section: str) -> list[tuple[str, str]]:
        start, end = self._section_bounds(section)
        if start is None:
            return []
        out = []
        for line in self.lines[start + 1:end]:
            m = _KEY.match(line)
            if m:
                out.append((m.group("key").strip(), m.group("value")))
        return out

    def untouched_lines(self, keys: set, sections: set | None = None) -> list[str]:
        """Every non-blank line except the given (section, key) entries, keeping only the section headers in
        `sections` (default: all). Two versions of a file that differ only in those keys give the same list."""
        out, section = [], None
        for line in self.lines:
            header = _SECTION.match(line)
            if header:
                section = header.group("name")
                if sections is None or section in sections:
                    out.append(line)
                continue
            m = _KEY.match(line)
            if line.strip() and not (m and (section, m.group("key").strip()) in keys):
                out.append(line)
        return out

    # -- edits -----------------------------------------------------------------

    def set(self, section: Optional[str], key: str, value: str) -> None:
        index = self._find_key(section, key)
        if index is not None:
            m = _KEY.match(self.lines[index])
            self.lines[index] = f"{m.group('key')}{m.group('sep')}{value}"
            return
        start, end = self._section_bounds(section)
        if start is None:
            if self.lines and self.lines[-1].strip():
                self._insert(len(self.lines), "")
            self._insert(len(self.lines), f"[{section}]")
            self._insert(len(self.lines), f"{key}{self._separator()}{value}")
            return
        insert_at = end
        while insert_at - 1 > start and not self.lines[insert_at - 1].strip():
            insert_at -= 1
        self._insert(insert_at, f"{key}{self._separator()}{value}")

    def remove(self, section: Optional[str], key: str) -> bool:
        index = self._find_key(section, key)
        if index is None:
            return False
        if index == len(self.lines) - 1 and index > 0:
            self.endings[index - 1] = self.endings[index]  # keep "no break at the end" if that's how it was
        del self.lines[index], self.endings[index]
        return True

    # -- internals -------------------------------------------------------------

    def _insert(self, index: int, line: str) -> None:
        """Insert a line; a line added after a last line that had no break gives that line one and takes its place."""
        if index == len(self.lines) and self.endings and self.endings[-1] == "":
            self.endings[-1] = self.newline
            self.endings.append("")
        else:
            self.endings.insert(index, self.newline)
        self.lines.insert(index, line)

    def _section_bounds(self, section: Optional[str]) -> tuple[Optional[int], int]:
        """section None is the top of the file, before any [header] (RetroArch .cfg/.rmp have no sections)."""
        if section is None:
            first = next((i for i, line in enumerate(self.lines) if _SECTION.match(line)), len(self.lines))
            return -1, first
        start = None
        for i, line in enumerate(self.lines):
            m = _SECTION.match(line)
            if not m:
                continue
            if start is not None:
                return start, i
            if m.group("name") == section:
                start = i
        return start, len(self.lines)

    def _find_key(self, section: Optional[str], key: str) -> Optional[int]:
        start, end = self._section_bounds(section)
        if start is None:
            return None
        for i in range(start + 1, end):
            m = _KEY.match(self.lines[i])
            if m and m.group("key").strip() == key:
                return i
        return None

    def _separator(self) -> str:
        """Reuse the file's existing "key = value" spacing style."""
        for line in self.lines:
            m = _KEY.match(line)
            if m:
                return m.group("sep")
        return " = "
