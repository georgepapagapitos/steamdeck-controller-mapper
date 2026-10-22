"""ES-DE's side of a launch: which emulator and core ES-DE is about to run for a game-start event.

ES-DE runs ~/ES-DE/scripts/game-start/* with four args: ROM path, game name, system name, full system name
(INSTALL.md "Custom event scripts"; Scripting::fireEvent, called from FileData::launchGame before the emulator
starts, es-app/src/FileData.cpp L2174 @ a529a9d). It doesn't pass the command, so we work it out the way
FileData::launchGame does (L979-1016): the game's own alternative emulator (`altemulator` in its gamelist entry,
when AlternativeEmulatorPerGame is on, the default), else the system's (`<alternativeEmulator><label>` in
~/ES-DE/gamelists/<system>/gamelist.xml, which EmuDeck sets and ES-DE rewrites as soon as the user changes it,
GuiAlternativeEmulators.cpp L173-176), else the system's first command. Commands come from
~/ES-DE/custom_systems/es_systems.xml when it defines the system, else from ES-DE's bundled file
(data/frontends/es-de.json).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import unescape as xml_unescape

from .launch import esde_table, system_id

ROOT = Path.home() / "ES-DE"

# FileSystemUtil.cpp getEscapedPath (L480-505 @ a529a9d) puts a backslash before each of these; Scripting::fireEvent
# wraps the result in double quotes and runs it through system(), i.e. /bin/sh, where a backslash inside double
# quotes only escapes $ ` " \ and newline. So the script receives the others still escaped: "Zelda\ \(USA\).iso".
_ESCAPED = re.compile(r"\\([ '!^&*(){}\[\]?;<>])")
_CORE = re.compile(r"([\w+-]+_libretro\.so)\b")
_SYSTEM_LABEL = re.compile(rb"<alternativeEmulator>\s*<label>(.*?)</label>", re.S)
_GAME = re.compile(rb"<game\b[^>]*>(.*?)</game>", re.S)


@dataclass
class EsdeLaunch:
    emulator: Optional[str]           # None: not an emulator map-helper manages
    system: str                       # map-helper system id
    core_file: Optional[str] = None
    label: Optional[str] = None       # the command's label, for the log
    rom: Optional[Path] = None


def unescape_rom(arg: str) -> Path:
    path = Path(_ESCAPED.sub(r"\1", arg))
    return path if path.exists() or not Path(arg).exists() else Path(arg)


def classify(command: str) -> tuple[Optional[str], Optional[str]]:
    """(emulator, RetroArch core file) for an es_systems.xml command, or (None, None) for anything we don't manage."""
    core = _CORE.search(command)
    if core and ("%EMULATOR_RETROARCH%" in command or "retroarch" in command.lower()):
        return "retroarch", core.group(1)
    if "%EMULATOR_DOLPHIN%" in command or "dolphin-emu.sh" in command:
        return "dolphin", None
    if "%EMULATOR_PCSX2%" in command or "pcsx2-qt.sh" in command:
        return "pcsx2", None
    return None, None


def commands(system: str, root: Path = ROOT) -> Optional[list]:
    """[label, command] in ES-DE's order. The custom file replaces a system it defines (INSTALL.md)."""
    custom = root / "custom_systems" / "es_systems.xml"
    if custom.is_file():
        try:
            for node in ET.parse(custom).getroot().iter("system"):
                if (node.findtext("name") or "").strip() == system:
                    return [[c.get("label"), (c.text or "").strip()] for c in node.findall("command")]
        except ET.ParseError:
            pass                                          # ES-DE would fail on it too; fall back to the bundled one
    return esde_table()["systems"].get(system)


def _label(system: str, rom: Path, root: Path) -> Optional[str]:
    gamelist = root / "gamelists" / system / "gamelist.xml"
    try:
        data = gamelist.read_bytes()
    except OSError:
        return None
    if b"<altemulator>" in data and _per_game(root):
        rel = _relative(rom, system)
        for game in _GAME.finditer(data):
            body = game.group(1)
            path = re.search(rb"<path>(.*?)</path>", body, re.S)
            alt = re.search(rb"<altemulator>(.*?)</altemulator>", body, re.S)
            if path and alt and rel and _text(path.group(1)) == rel:
                return _text(alt.group(1))
    m = _SYSTEM_LABEL.search(data)
    return _text(m.group(1)) if m else None


def _text(raw: bytes) -> str:
    return xml_unescape(raw.decode("utf-8", "replace").strip(), {"&quot;": '"', "&apos;": "'"})


def _relative(rom: Path, system: str) -> Optional[str]:
    """Gamelist paths are ./<path under the system's ROM folder>."""
    parts = rom.parts
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] == system:
            return "./" + "/".join(parts[i + 1:])
    return None


def _per_game(root: Path) -> bool:
    try:
        settings = (root / "settings" / "es_settings.xml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return not re.search(r'<bool name="AlternativeEmulatorPerGame" value="false"', settings)


def launch(rom_arg: str, system: str, root: Path = ROOT) -> Optional[EsdeLaunch]:
    """What ES-DE runs for this game-start event; None for a system ES-DE doesn't have a command we know for."""
    rom = unescape_rom(rom_arg)
    cmds = commands(system, root)
    if not cmds:
        return None
    label = _label(system, rom, root)
    chosen = next((c for c in cmds if label and c[0] == label), cmds[0])
    emulator, core = classify(chosen[1])
    return EsdeLaunch(emulator, system_id(system), core, chosen[0], rom)
