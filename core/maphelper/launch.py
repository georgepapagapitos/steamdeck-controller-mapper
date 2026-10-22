"""What a launch command says: the ROM, the RetroArch core, the system and the game id. See docs/07 "mh-run behaviour".

Known shapes (EmuDeck's SRM parsers, configs/steam-rom-manager/userData/userConfigurations.json and
parsers/optional/*.json, and ES-DE's es_systems.xml commands, data/frontends/es-de.json):

- RetroArch: `retroarch.sh -L <cores>/<core>_libretro.so <rom>` (or `flatpak run org.libretro.RetroArch -L ...`)
- Dolphin:   `dolphin-emu.sh -b -e <rom>`
- PCSX2:     `pcsx2-qt.sh -batch -fullscreen -nogui <rom>` (ES-DE: `pcsx2-*.AppImage -batch <rom>`)

Older SRM parsers wrapped paths in single quotes ('/path/rom.iso' reaches the launcher with the quotes); EmuDeck's
AppImage launchers strip one leading and one trailing ' from every arg (`sed "s/^'//; s/'$//"`, pcsx2-qt.sh and
duckstation.sh @ dddb302, tests/fixtures/emudeck-launchers/). We do the same before reading them.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .store import load_json

DATA = Path(__file__).resolve().parents[2] / "data"


@dataclass
class LaunchInfo:
    rom: Optional[Path] = None
    core_file: Optional[str] = None       # RetroArch: e.g. snes9x_libretro.so
    system: Optional[str] = None          # map-helper system id, when the command or the ROM says
    game: Optional[str] = None


def _strip(arg: str) -> str:
    """The legacy-parser quote strip EmuDeck's launchers do."""
    if arg.startswith("'"):
        arg = arg[1:]
    if arg.endswith("'"):
        arg = arg[:-1]
    return arg


def _last_positional(args: list[str], skip: set) -> Optional[str]:
    for arg in reversed(args):
        if arg and not arg.startswith("-") and arg not in skip:
            return arg
    return None


def _option(args: list[str], *names: str) -> Optional[str]:
    """The value of -x VALUE or --name=VALUE."""
    for i, arg in enumerate(args):
        for name in names:
            if arg == name and i + 1 < len(args):
                return args[i + 1]
            if name.startswith("--") and arg.startswith(name + "="):
                return arg[len(name) + 1:]
    return None


def _program_args(command: list[str]) -> list[str]:
    """The emulator's own args: drop the program, and `flatpak run [opts] <app id>` in front of it."""
    args = [_strip(a) for a in command[1:]]
    if Path(command[0]).name == "flatpak" and args[:1] == ["run"]:
        args = args[1:]
        while args and args[0].startswith("-"):
            args = args[1:]
        args = args[1:]                       # the app id
    return args


def parse_retroarch(command: list[str]) -> LaunchInfo:
    args = _program_args(command)
    core = _option(args, "-L", "--libretro")
    rom = _last_positional(args, {core} if core else set())
    info = LaunchInfo(rom=Path(rom) if rom else None, core_file=Path(core).name if core else None)
    if info.rom:
        info.system = system_from_path(info.rom)
        info.game = retroarch_game_id(rom)
    return info


def retroarch_game_id(rom: str) -> str:
    """RetroArch's content basename: the file name without its last extension; for a path into an archive
    (game.zip#rom.sfc) the member's (docs/adapters/retroarch.md "Game id")."""
    name = rom.rsplit("#", 1)[-1]
    return Path(name).stem


def parse_dolphin(command: list[str]) -> LaunchInfo:
    args = _program_args(command)
    rom = _option(args, "-e", "--exec")
    info = LaunchInfo(rom=Path(rom) if rom else None)
    if info.rom:
        disc_system, info.game = dolphin_disc(info.rom)
        info.system = disc_system or system_from_path(info.rom)    # the header is the disc's own word
    return info


def parse_pcsx2(command: list[str]) -> LaunchInfo:
    args = _program_args(command)
    rom = _option(args, "-elf") or _last_positional(args, set())
    return LaunchInfo(rom=Path(rom) if rom else None, system="ps2")


PARSERS = {"dolphin": parse_dolphin, "pcsx2": parse_pcsx2, "retroarch": parse_retroarch}


# -- the system from where the ROM is --------------------------------------------

_ESDE = None


def esde_table() -> dict:
    global _ESDE
    if _ESDE is None:
        _ESDE = load_json(DATA / "frontends" / "es-de.json")
    return _ESDE


def system_id(esde_name: str) -> str:
    """ES-DE system name (= EmuDeck's roms/<dir>) -> map-helper system id."""
    return esde_table()["aliases"].get(esde_name, esde_name)


def system_from_path(rom: Path) -> Optional[str]:
    """EmuDeck keeps ROMs in Emulation/roms/<ES-DE system name>/ (ES-DE's <path>%ROMPATH%/<name></path>, and the
    `${romsdirglobal}/<name>` romDirectory of EmuDeck's SRM parsers), so the folder under `roms` names the system."""
    parts = Path(rom).parts
    for i in range(len(parts) - 2, 0, -1):
        if parts[i - 1] == "roms":
            return system_id(parts[i])
    return None


# -- Dolphin discs ---------------------------------------------------------------

# Dolphin's own test (DiscIO/Volume.cpp CreateDisc L121-124, DiscUtils.h L25-26 @ 2c805fee8f): the big-endian u32 at
# 0x18 of the disc header is WII_DISC_MAGIC on a Wii disc, the one at 0x1C GAMECUBE_DISC_MAGIC on a GameCube disc.
WII_DISC_MAGIC, GAMECUBE_DISC_MAGIC = 0x5D1C9EA3, 0xC2339F3D
WIA_HEADER_1 = 0x48            # WIABlob.h: sizeof(WIAHeader1); WIAHeader2 = 4 u32s, then disc_header[0x80]
CISO_HEADER_SIZE = 0x8000      # CISOBlob.h: magic, block_size, map[]; block 0's data follows the header


def dolphin_disc(rom: Path) -> tuple[Optional[str], Optional[str]]:
    """("gc" | "wii" | None, game id or None) from the disc header, for formats that keep it uncompressed:
    ISO/GCM, WIA/RVZ (a copy in their header) and CISO (when block 0 is stored). WBFS holds only Wii discs.
    GCZ and others: (None, None), and the caller falls back to the ROM's folder."""
    try:
        with open(rom, "rb") as f:
            head = f.read(WIA_HEADER_1 + 0x10 + 0x20)
            if head[:4] in (b"WIA\x01", b"RVZ\x01"):
                header = head[WIA_HEADER_1 + 0x10:WIA_HEADER_1 + 0x10 + 0x20]
            elif head[:4] == b"CISO":
                if len(head) < 9 or head[8] != 1:
                    return None, None
                f.seek(CISO_HEADER_SIZE)
                header = f.read(0x20)
            elif head[:4] == b"WBFS":
                return "wii", None
            else:
                header = head[:0x20]
    except OSError:
        return None, None
    if len(header) < 0x20:
        return None, None
    wii, gc = struct.unpack(">II", header[0x18:0x20])
    system = "wii" if wii == WII_DISC_MAGIC else "gc" if gc == GAMECUBE_DISC_MAGIC else None
    game = header[:6].decode("ascii", "replace")
    return system, (game if system and game.isalnum() else None)
