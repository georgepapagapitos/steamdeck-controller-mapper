"""`map-helper setup` / `uninstall`: put mh-run in the launch paths, and take it out again. See docs/07 and ADR-001.

setup does three things, each recorded in $STATE/setup.json so uninstall reverses exactly that and nothing else:

1. Installs the `mh-run` POSIX sh shim in ~/.local/bin (docs/14 §6).
2. Edits Steam ROM Manager's parsers (~/.config/steam-rom-manager/userData/userConfigurations.json) so each parser
   for an emulator map-helper manages runs `mh-run --emulator <id> -- %command% ...`. Steam only sees it after the
   user's next "Save to Steam" in SRM. shortcuts.vdf is never written.
3. Installs the ES-DE game-start event script and turns on ES-DE's CustomEventScripts setting.

Both are dry runs unless write=True, and both are idempotent. A file someone changed after setup is left alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from json.decoder import scanstring
from pathlib import Path
from typing import Callable, Optional

from .writer import _atomic_write

HOME = Path.home()
RECORD = "setup.json"
MARK = "--emulator"           # what our launch-options prefix carries after the shim's path


@dataclass
class Places:
    """Everything setup touches; tests point these into a temp dir."""
    home: Path = HOME
    entry: Optional[Path] = None              # mh_entry.py the shim runs (default: the `current` install, docs/14)
    python: str = "/usr/bin/python3"
    state_dir: Optional[Path] = None
    proc_root: Path = Path("/proc")

    def __post_init__(self):
        self.home = Path(self.home)
        self.entry = Path(self.entry) if self.entry else self.home / ".local/lib/map-helper/current/mh_entry.py"
        self.state_dir = Path(self.state_dir) if self.state_dir else self.home / ".local/state/map-helper"

    @property
    def shim(self) -> Path:
        return self.home / ".local/bin/mh-run"

    @property
    def srm_config(self) -> Path:
        return self.home / ".config/steam-rom-manager/userData/userConfigurations.json"

    @property
    def esde_root(self) -> Path:
        return self.home / "ES-DE"           # ESDE_newConfigDirectory, functions/ToolScripts/emuDeckESDE.sh @ dddb302

    @property
    def esde_script(self) -> Path:
        return self.esde_root / "scripts" / "game-start" / "map-helper.sh"

    @property
    def esde_settings(self) -> Path:
        return self.esde_root / "settings" / "es_settings.xml"

    @property
    def emudeck_settings(self) -> Path:
        return self.home / ".config/EmuDeck/settings.sh"


@dataclass
class Change:
    part: str                 # shim | srm | es-de script | es-de setting | automap
    action: str               # install | update | ok | remove | leave | refuse | report
    message: str


@dataclass
class Report:
    changes: list = field(default_factory=list)

    def add(self, part, action, message):
        self.changes.append(Change(part, action, message))

    @property
    def refused(self) -> bool:
        return any(c.action == "refuse" for c in self.changes)


# -- file contents ---------------------------------------------------------------

def shim_text(entry: Path, python: str) -> str:
    # docs/14 §6. The shell, not Python, starts the command, so not even a broken install can stop a launch; Python's
    # own output goes nowhere (the emulator keeps the terminal) and mh-run logs to $STATE/logs/launch.log. mh-run
    # keeps its own 500 ms budget; coreutils' timeout (in SteamOS's base image) is only a backstop for a hang the
    # in-process watchdog can't interrupt, and is skipped where it doesn't exist.
    return f"""#!/bin/sh
# map-helper launch shim (managed file: `map-helper setup` wrote it, `map-helper uninstall` removes it).
# Applies controller mappings, then runs the command after -- unchanged. Never blocks a launch.
MH={_sh_quote(str(entry))}
PY={_sh_quote(python)}
if [ -x "$PY" ] && [ -f "$MH" ]; then
    T=""
    command -v timeout >/dev/null 2>&1 && T="timeout -s KILL 2"
    $T "$PY" -I "$MH" mh-run --no-exec "$@" </dev/null >/dev/null 2>&1
fi
[ "$1" = "--hook" ] && exit 0
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done
[ "$#" -gt 0 ] && shift
[ "$#" -gt 0 ] && exec "$@"
exit 0
"""


def esde_script_text(shim: Path) -> str:
    # ES-DE passes ROM path, game name, system name, full system name (INSTALL.md "Custom event scripts" @ a529a9d)
    # and waits for the script; it must always exit 0 and quickly.
    return f"""#!/bin/sh
# map-helper (managed file: `map-helper setup` wrote it, `map-helper uninstall` removes it).
# Applies controller mappings before ES-DE starts a game. Args from ES-DE: ROM path, game name, system, full name.
MH_RUN={_sh_quote(str(shim))}
[ -x "$MH_RUN" ] && "$MH_RUN" --hook --es-de "$1" "$2" "$3" "$4" </dev/null >/dev/null 2>&1
exit 0
"""


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _hash(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except FileNotFoundError:
        return None


# -- running programs ---------------------------------------------------------------

def running(proc_root: Path, pattern: str) -> bool:
    """Is a process whose argv[0] matches `pattern` (lower case) running? Reads /proc/<pid>/cmdline."""
    rx = re.compile(pattern)
    try:
        pids = [p for p in Path(proc_root).iterdir() if p.name.isdigit()]
    except OSError:
        return False
    for pid in pids:
        try:
            argv0 = (pid / "cmdline").read_bytes().split(b"\0")[0].decode("utf-8", "replace").lower()
        except OSError:
            continue
        if rx.search(argv0):
            return True
    return False


# ES-DE's AppImage runs as /tmp/.mount_ES-DE*/usr/bin/es-de; EmuDeck starts it from ~/Applications/ES-DE.AppImage.
# SRM's AppImage runs as .../steam-rom-manager (Electron). [VERIFY] both names on a Deck.
ESDE_PROCESS = r"(^|/)es-de(\.appimage)?$"
SRM_PROCESS = r"(^|/)steam-?rom-?manager[^/]*$"


# -- the record ---------------------------------------------------------------------

def load_record(state_dir: Path) -> dict:
    path = Path(state_dir) / RECORD
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_record(state_dir: Path, record: dict) -> None:
    path = Path(state_dir) / RECORD
    if record:
        _atomic_write(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    elif path.exists():
        path.unlink()


# -- managed files (shim, ES-DE script) ----------------------------------------------

def _install_file(report: Report, record: dict, part: str, key: str, path: Path, text: str, write: bool,
                  mode: int = 0o755) -> None:
    have = _read(path)
    mine = record.get(key)
    if have == text:
        report.add(part, "ok", f"{path} is installed")
        if write and not mine:
            record[key] = {"path": str(path), "hash": _hash(text)}
        return
    if have is not None and not (mine and _hash(have) == mine["hash"]):
        report.add(part, "refuse", f"{path} exists and isn't map-helper's; move it away and run setup again")
        return
    report.add(part, "update" if have is not None else "install",
               f"{'would write' if not write else 'wrote'} {path}")
    if write:
        _atomic_write(path, text)
        os.chmod(path, mode)
        record[key] = {"path": str(path), "hash": _hash(text)}


def _remove_file(report: Report, record: dict, part: str, key: str, write: bool) -> None:
    mine = record.get(key)
    if not mine:
        return
    path = Path(mine["path"])
    have = _read(path)
    if have is None:
        report.add(part, "ok", f"{path} is already gone")
    elif _hash(have) != mine["hash"]:
        report.add(part, "leave", f"{path} changed since setup wrote it; left in place")
    else:
        report.add(part, "remove", f"{'would remove' if not write else 'removed'} {path}")
        if write:
            path.unlink()
    if write:
        del record[key]


# -- SRM parsers -------------------------------------------------------------------

def _emulator_of(parser: dict) -> Optional[str]:
    """The managed emulator an SRM parser launches, by its executable (EmuDeck's parsers: ${retroarchpath},
    .../launchers/dolphin-emu.sh, .../launchers/pcsx2-qt.sh). RetroArch parsers count only when map-helper has a
    descriptor for their core: wrapping one changes the shortcut's app id for nothing otherwise."""
    exe = str((parser.get("executable") or {}).get("path") or "")
    name = exe.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "retroarch" in exe.lower():
        core = re.search(r"([\w+-]+?)_libretro\.", str(parser.get("executableArgs") or ""))
        return "retroarch" if core and f"{core.group(1)}_libretro.so" in _core_files() else None
    if name == "dolphin-emu.sh":
        return "dolphin"
    if name == "pcsx2-qt.sh":
        return "pcsx2"
    return None


def _core_files() -> set:
    from .adapters.retroarch import RetroArchAdapter
    return {f for desc in RetroArchAdapter().cores.values() for f in desc["core_files"]}


def prefix(shim: Path, emulator: str) -> str:
    path = str(shim)
    return f'{chr(34) + path + chr(34) if " " in path else path} {MARK} {emulator} -- '


def wrap_args(args: str, emulator: str, shim: Path) -> str:
    """Launch options that run mh-run in front of the emulator. With %command% (EmuDeck's Dolphin parsers:
    `vblank_mode=0 %command% -b -e "${filePath}"`) the prefix goes right before it, so env assignments still apply
    to everything after. Without it, Steam appends launch options to the Exe, so `%command% <args>` is the same."""
    if "%command%" in args:
        return args.replace("%command%", prefix(shim, emulator) + "%command%", 1)
    return prefix(shim, emulator) + "%command%" + (" " + args.strip() if args.strip() else "")


def _srm_setup(report: Report, record: dict, places: Places, write: bool) -> None:
    path = places.srm_config
    text = _read(path)
    if text is None:
        report.add("srm", "ok", f"no SRM parsers at {path}; skipped")
        return
    try:
        parsers, spans = parse_spans(text)
    except ValueError as e:
        report.add("srm", "refuse", f"{path}: can't read it ({e})")
        return
    mine = record.get("srm", {}).get("parsers", {})
    edits, planned, appid = [], {}, []
    for i, parser in enumerate(parsers if isinstance(parsers, list) else []):
        emulator = _emulator_of(parser) if isinstance(parser, dict) else None
        args_span, append_span = spans.get((i, "executableArgs")), spans.get((i, "executable", "appendArgsToExecutable"))
        pid = str(parser.get("parserId")) if emulator else None
        if not emulator or args_span is None or pid in mine:
            continue
        args = parser["executableArgs"]
        title = parser.get("configTitle") or pid
        if MARK in args and "mh-run" in args:
            continue                                  # wrapped by hand, or by another setup: leave it be
        new_args = wrap_args(args, emulator, places.shim)
        entry = {"title": title, "emulator": emulator,
                 "args": [text[args_span[0]:args_span[1]], json.dumps(new_args, ensure_ascii=False)]}
        edits.append((args_span, entry["args"][1]))
        if parser["executable"].get("appendArgsToExecutable") and append_span is not None:
            # SRM puts these args in the Exe field (file-parser.ts appendArgsPromise L851-856 @ f68289a); %command%
            # needs them in the launch options, so the parser stops appending. The Exe changes, and with it the
            # shortcut's app id (generateShortAppId(exe, title), L892-895).
            entry["append"] = [text[append_span[0]:append_span[1]], "false"]
            edits.append((append_span, "false"))
            appid.append(title)
        planned[pid] = entry
    if not planned:
        report.add("srm", "ok", f"every SRM parser for a managed emulator runs mh-run ({path})")
        return
    if running(places.proc_root, SRM_PROCESS):
        report.add("srm", "refuse", "Steam ROM Manager is running; it keeps its parsers in memory and saves them "
                                    "over ours. Close it and run setup again")
        return
    for pid, entry in planned.items():
        report.add("srm", "install", f"{'would wrap' if not write else 'wrapped'} parser \"{entry['title']}\" "
                                     f"({entry['emulator']})")
    if appid:
        report.add("srm", "report", f"{len(appid)} parser(s) put their args in the shortcut's Exe until now "
                                    f"({', '.join(appid[:3])}{', ...' if len(appid) > 3 else ''}). Their Steam "
                                    "shortcuts get new app ids at the next Save to Steam: per-shortcut Steam "
                                    "settings (controller layout, playtime) don't carry over")
    report.add("srm", "report", "takes effect when you next run Steam ROM Manager's \"Save to Steam\"")
    if not write:
        return
    srm = record.setdefault("srm", {"path": str(path), "parsers": {}})
    if "backup" not in srm:
        backup = Path(places.state_dir) / "backups" / "setup" / f"userConfigurations.{time.strftime('%Y%m%d-%H%M%S')}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        srm["backup"] = str(backup)
    _atomic_write(path, _replace(text, edits))
    srm["parsers"].update(planned)


def _srm_uninstall(report: Report, record: dict, places: Places, write: bool) -> None:
    srm = record.get("srm")
    if not srm:
        return
    path = Path(srm["path"])
    text = _read(path)
    if text is None:
        report.add("srm", "ok", f"{path} is gone; nothing to undo")
        if write:
            del record["srm"]
        return
    parsers, spans = parse_spans(text)
    by_id = {str(p.get("parserId")): i for i, p in enumerate(parsers) if isinstance(p, dict)}
    edits = []
    for pid, entry in srm["parsers"].items():
        i = by_id.get(pid)
        span = spans.get((i, "executableArgs")) if i is not None else None
        if span is None:
            report.add("srm", "ok", f"parser \"{entry['title']}\" is gone")
            continue
        current = text[span[0]:span[1]]
        if current == entry["args"][1]:
            edits.append((span, entry["args"][0]))
            if "append" in entry:
                aspan = spans.get((i, "executable", "appendArgsToExecutable"))
                if aspan and text[aspan[0]:aspan[1]] == entry["append"][1]:
                    edits.append((aspan, entry["append"][0]))
            report.add("srm", "remove", f"{'would unwrap' if not write else 'unwrapped'} parser \"{entry['title']}\"")
        elif prefix(places.shim, entry["emulator"]) in parsers[i]["executableArgs"]:
            # Changed since, but our prefix is still there: take out just the prefix.
            value = parsers[i]["executableArgs"].replace(prefix(places.shim, entry["emulator"]), "", 1)
            edits.append((span, json.dumps(value, ensure_ascii=False)))
            report.add("srm", "remove", f"{'would take' if not write else 'took'} mh-run out of parser "
                                        f"\"{entry['title']}\" (its args changed since setup; the rest kept)")
        else:
            report.add("srm", "leave", f"parser \"{entry['title']}\" no longer runs mh-run; left alone")
    if edits and running(places.proc_root, SRM_PROCESS):
        report.add("srm", "refuse", "Steam ROM Manager is running; close it and run uninstall again")
        return
    if edits:
        report.add("srm", "report", "takes effect when you next run Steam ROM Manager's \"Save to Steam\"")
    if write:
        if edits:
            _atomic_write(path, _replace(text, edits))
        del record["srm"]


def _replace(text: str, edits: list) -> str:
    for (start, end), new in sorted(edits, key=lambda e: e[0][0], reverse=True):
        text = text[:start] + new + text[end:]
    return text


_WS = re.compile(r"[ \t\n\r]*")
_SCALAR = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?|true|false|null")


def parse_spans(text: str) -> tuple[object, dict]:
    """json.loads, plus where each scalar value sits in the text: {(index or key, ...): (start, end)}. Edits replace
    exactly those characters, so the rest of a file (SRM's or EmuDeck's formatting) stays byte for byte."""
    spans = {}

    def value(i: int, path: tuple):
        i = _WS.match(text, i).end()
        c = text[i:i + 1]
        if c == "{":
            out, i = {}, _WS.match(text, i + 1).end()
            if text[i:i + 1] == "}":
                return out, i + 1
            while True:
                if text[i:i + 1] != '"':
                    raise ValueError(f"expected a key at {i}")
                key, i = scanstring(text, i + 1)
                i = _WS.match(text, i).end()
                if text[i:i + 1] != ":":
                    raise ValueError(f"expected ':' at {i}")
                out[key], i = value(i + 1, path + (key,))
                i = _WS.match(text, i).end()
                if text[i:i + 1] == ",":
                    i = _WS.match(text, i + 1).end()
                    continue
                if text[i:i + 1] == "}":
                    return out, i + 1
                raise ValueError(f"expected ',' or '}}' at {i}")
        if c == "[":
            out, i = [], _WS.match(text, i + 1).end()
            if text[i:i + 1] == "]":
                return out, i + 1
            while True:
                item, i = value(i, path + (len(out),))
                out.append(item)
                i = _WS.match(text, i).end()
                if text[i:i + 1] == ",":
                    i += 1
                    continue
                if text[i:i + 1] == "]":
                    return out, i + 1
                raise ValueError(f"expected ',' or ']' at {i}")
        if c == '"':
            s, end = scanstring(text, i + 1)
            spans[path] = (i, end)
            return s, end
        m = _SCALAR.match(text, i)
        if not m:
            raise ValueError(f"unexpected {c!r} at {i}")
        spans[path] = m.span()
        return json.loads(m.group()), m.end()

    doc, end = value(0, ())
    if _WS.match(text, end).end() != len(text):
        raise ValueError("trailing data")
    return doc, spans


# -- ES-DE -----------------------------------------------------------------------

# Settings::saveFile writes every setting as <bool name="..." value="..." /> at the top level, no root element
# (es-core/src/Settings.cpp L420-448 @ a529a9d); EmuDeck's own es_settings.xml is in the same flat form.
_SETTING = re.compile(r'<bool name="CustomEventScripts" value="([^"]*)"\s*/>')
SETTING_LINE = '<bool name="CustomEventScripts" value="true" />'


def _esde_setting_setup(report: Report, record: dict, places: Places, write: bool) -> None:
    path = places.esde_settings
    text = _read(path)
    if text is None:
        report.add("es-de setting", "refuse", f"no {path}; start ES-DE once so it writes its settings, then run "
                                              "setup again")
        return
    m = _SETTING.search(text)
    if m and m.group(1) == "true":
        report.add("es-de setting", "ok", "ES-DE's custom event scripts are on")
        return
    if running(places.proc_root, ESDE_PROCESS):
        # ES-DE reads es_settings.xml once at start and writes the whole file from memory whenever a settings menu
        # closes with changes (GuiSettings.cpp L65-66, Settings::saveFile), so an edit now could be lost and
        # wouldn't take effect before a restart anyway.
        report.add("es-de setting", "refuse", "ES-DE is running; quit it and run setup again to turn on its "
                                              "custom event scripts")
        return
    report.add("es-de setting", "install", f"{'would turn' if not write else 'turned'} on CustomEventScripts in {path}")
    if not write:
        return
    if m:
        new = text[:m.start(1)] + "true" + text[m.end(1):]
        record["esde_setting"] = {"path": str(path), "before": m.group(1)}
    else:
        new = text + ("" if text.endswith("\n") or not text else "\n") + SETTING_LINE + ("\n" if text.endswith("\n")
                                                                                         else "")
        record["esde_setting"] = {"path": str(path), "before": None}
    _atomic_write(path, new)


def _esde_setting_uninstall(report: Report, record: dict, places: Places, write: bool) -> None:
    mine = record.get("esde_setting")
    if not mine:
        return
    path = Path(mine["path"])
    text = _read(path)
    m = _SETTING.search(text) if text is not None else None
    if not m or m.group(1) != "true":
        report.add("es-de setting", "leave", "CustomEventScripts isn't on any more; left as it is")
        if write:
            del record["esde_setting"]
        return
    if running(places.proc_root, ESDE_PROCESS):
        report.add("es-de setting", "refuse", "ES-DE is running; quit it and run uninstall again")
        return
    report.add("es-de setting", "remove", f"{'would turn' if not write else 'turned'} CustomEventScripts back off")
    if not write:
        return
    if mine["before"] is not None:
        new = text[:m.start(1)] + mine["before"] + text[m.end(1):]
    else:
        # Take out the line we added, with the line break that came with it.
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        line_end = len(text) if end == -1 else end + 1
        if text[start:line_end].strip() != m.group(0):
            new = text[:m.start()] + text[m.end():]          # not alone on its line (ES-DE rewrote it): just it
        elif end == -1 and start > 0:
            new = text[:start - 1]                           # last line, no break after: drop the break before
        else:
            new = text[:start] + text[line_end:]
    _atomic_write(path, new)
    del record["esde_setting"]


# -- EmuDeck AutoMap (ADR-001 item 3): reported, not changed here -----------------------

def _automap(report: Report, places: Places) -> None:
    from .doctor import read_emudeck_settings
    settings = read_emudeck_settings(places.emudeck_settings)
    if settings is None:
        return
    value = settings.get("autoMapDolphin")              # read this one key only; the file holds credentials too
    if value == "false":
        return
    if value:
        report.add("automap", "report", f"EmuDeck AutoMap is on for Dolphin (autoMapDolphin={value}): every launch "
                                        "through EmuDeck's Dolphin launcher puts the stock GCPadNew.ini back after "
                                        "mh-run. Turn it off in the EmuDeck app (AutoMap page); setup doesn't "
                                        "change EmuDeck's settings")
    else:
        report.add("automap", "report", "EmuDeck's autoMapDolphin is unset: AutoMap is skipped on a Steam Deck but "
                                        "runs on other PCs")


# -- entry points ------------------------------------------------------------------

def setup(places: Places, write: bool = False) -> Report:
    report, record = Report(), load_record(places.state_dir)
    _install_file(report, record, "shim", "shim", places.shim, shim_text(places.entry, places.python), write)
    if not places.entry.is_file():
        report.add("shim", "report", f"{places.entry} isn't there yet: until map-helper is installed there, the "
                                     "shim just runs the command")
    _srm_setup(report, record, places, write)
    if places.esde_root.is_dir():
        _install_file(report, record, "es-de script", "esde_script", places.esde_script,
                      esde_script_text(places.shim), write)
        _esde_setting_setup(report, record, places, write)
    else:
        report.add("es-de script", "ok", f"no ES-DE at {places.esde_root}; skipped")
    _automap(report, places)
    if write:
        save_record(places.state_dir, record)
    return report


def uninstall(places: Places, write: bool = False) -> Report:
    report, record = Report(), load_record(places.state_dir)
    if not record:
        report.add("setup", "ok", "setup hasn't changed anything; nothing to undo")
        return report
    _srm_uninstall(report, record, places, write)
    _esde_setting_uninstall(report, record, places, write)
    _remove_file(report, record, "es-de script", "esde_script", write)
    _remove_file(report, record, "shim", "shim", write)
    if write:
        save_record(places.state_dir, record)
    return report


def render(report: Report) -> str:
    return "".join(f"{c.part}: {c.message}\n" for c in report.changes)
