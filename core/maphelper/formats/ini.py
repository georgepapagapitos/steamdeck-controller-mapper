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


class IniDocument:
    def __init__(self, text: str = ""):
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.trailing_newline = text.endswith(("\n", "\r\n")) or text == ""
        self.lines = text.splitlines()

    @classmethod
    def parse(cls, text: str) -> "IniDocument":
        return cls(text)

    def serialize(self) -> str:
        body = self.newline.join(self.lines)
        return body + self.newline if self.trailing_newline and self.lines else body

    # -- queries ---------------------------------------------------------------

    def sections(self) -> list[str]:
        return [m.group("name") for m in map(_SECTION.match, self.lines) if m]

    def get(self, section: str, key: str) -> Optional[str]:
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

    # -- edits -----------------------------------------------------------------

    def set(self, section: str, key: str, value: str) -> None:
        index = self._find_key(section, key)
        if index is not None:
            m = _KEY.match(self.lines[index])
            self.lines[index] = f"{m.group('key')}{m.group('sep')}{value}"
            return
        start, end = self._section_bounds(section)
        if start is None:
            if self.lines and self.lines[-1].strip():
                self.lines.append("")
            self.lines += [f"[{section}]", f"{key}{self._separator()}{value}"]
            return
        insert_at = end
        while insert_at - 1 > start and not self.lines[insert_at - 1].strip():
            insert_at -= 1
        self.lines.insert(insert_at, f"{key}{self._separator()}{value}")

    def remove(self, section: str, key: str) -> bool:
        index = self._find_key(section, key)
        if index is None:
            return False
        del self.lines[index]
        return True

    # -- internals -------------------------------------------------------------

    def _section_bounds(self, section: str) -> tuple[Optional[int], int]:
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

    def _find_key(self, section: str, key: str) -> Optional[int]:
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
