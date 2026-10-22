"""Read-only parsers for Steam's KeyValues files: text (`localconfig.vdf`) and binary (`shortcuts.vdf`).

Nothing here writes: Steam keeps these files in memory and rewrites them itself, so map-helper only reads them.

Text format: quoted or bare tokens, `{` `}` for nested maps, `//` comments, backslash escapes inside quotes
(Valve's KeyValues, https://developer.valvesoftware.com/wiki/KeyValues). Keys are case-insensitive in Steam, so
`lookup` matches them ignoring case.

Binary format (shortcuts.vdf): a type byte, a NUL-terminated key, then the value: 0x00 nested map, 0x01
NUL-terminated string, 0x02 little-endian int32; 0x08 ends a map. Layout as read by `steam-shortcut-editor`
(Steam-ROM-Manager's shortcuts.vdf library), `lib/parser.js` at tirish/steam-shortcut-editor@d755f03.
"""

from __future__ import annotations

import struct
from typing import Optional

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


class VdfError(ValueError):
    pass


def parse_text(text: str) -> dict:
    """Text KeyValues -> nested dicts. Later duplicate keys win, as in Steam."""
    tokens = _tokens(text)
    root: dict = {}
    stack = [root]
    key: Optional[str] = None
    for tok, quoted in tokens:
        if not quoted and tok == "{":
            if key is None:
                raise VdfError("'{' without a key")
            child: dict = {}
            stack[-1][key] = child
            stack.append(child)
            key = None
        elif not quoted and tok == "}":
            if len(stack) == 1 or key is not None:
                raise VdfError("unbalanced '}'")
            stack.pop()
        elif key is None:
            key = tok
        else:
            stack[-1][key] = tok
            key = None
    if len(stack) != 1 or key is not None:
        raise VdfError("unexpected end of file")
    return root


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif c in "{}":
            yield c, False
            i += 1
        elif c == '"':
            out, i = [], i + 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    out.append(_ESCAPES.get(text[i + 1], "\\" + text[i + 1]))
                    i += 2
                else:
                    out.append(text[i])
                    i += 1
            if i >= n:
                raise VdfError("unterminated string")
            yield "".join(out), True
            i += 1
        elif c == "[":   # platform conditional ([$WIN32]) after a value; irrelevant on Linux
            j = text.find("]", i)
            i = n if j < 0 else j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '{}"':
                j += 1
            yield text[i:j], False
            i = j


def parse_binary(data: bytes) -> dict:
    """Binary KeyValues (shortcuts.vdf) -> nested dicts; int32 values come back as Python ints."""
    value, pos = _map(data, 0)
    return value


def _cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end < 0:
        raise VdfError("unterminated string")
    return data[pos:end].decode("utf-8", errors="replace"), end + 1


def _map(data: bytes, pos: int) -> tuple[dict, int]:
    out: dict = {}
    while pos < len(data):
        kind = data[pos]
        pos += 1
        if kind == 0x08:
            return out, pos
        key, pos = _cstring(data, pos)
        if kind == 0x00:
            out[key], pos = _map(data, pos)
        elif kind == 0x01:
            out[key], pos = _cstring(data, pos)
        elif kind == 0x02:
            if pos + 4 > len(data):
                raise VdfError("truncated int32")
            out[key] = struct.unpack_from("<i", data, pos)[0]
            pos += 4
        else:
            raise VdfError(f"unknown type byte 0x{kind:02x} at {pos - 1}")
    return out, pos   # the outer map's own 0x08 may be the file's last byte or missing


def lookup(tree: dict, *path: str):
    """tree["a"]["b"]... with keys matched case-insensitively; None if any step is missing."""
    node = tree
    for part in path:
        if not isinstance(node, dict):
            return None
        match = next((v for k, v in node.items() if k.lower() == part.lower()), None)
        if match is None:
            return None
        node = match
    return node
