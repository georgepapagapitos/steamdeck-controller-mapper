"""`map-helper doctor`: read-only checks for settings that silently defeat map-helper's mappings.

Nothing here writes. Each check returns findings with a severity:

- error:   map-helper's writes can't take effect (or no controller works at all) until the user changes something.
- warning: they're defeated in some cases (a game, a layout switch) or rest on an assumption that no longer holds.
- info:    state worth knowing, or a check that was skipped.

Facts and sources are in docs/05 ("Per-game Steam Input override"), docs/adapters/retroarch.md ("doctor checks")
and docs/07 (EmuDeck AutoMap).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .adapters.retroarch import REMAP_DIR
from .formats import vdf

HOME = Path.home()
STEAM_ROOT = HOME / ".local/share/Steam"
RETROARCH_ROOT = HOME / ".var/app/org.libretro.RetroArch/config/retroarch"
EMUDECK_SETTINGS = HOME / ".config/EmuDeck/settings.sh"

# How EmuDeck's retroarch.cfg spells the Flatpak config root (tests/fixtures/retroarch/emudeck-default).
FLATPAK_RA_ROOT = "~/.var/app/org.libretro.RetroArch/config/retroarch"

# UseSteamControllerConfig values: Steam-ROM-Manager src/models/parser.model.ts (`steamInputEnabled`).
STEAM_INPUT_OFF, STEAM_INPUT_DEFAULT, STEAM_INPUT_ON = "0", "1", "2"

# A shortcut that runs a frontend or emulator EmuDeck sets up. Matched against AppName, Exe, StartDir and
# LaunchOptions, so SRM shortcuts (Exe = a launcher under Emulation/tools/launchers) and hand-made ones both count.
EMULATION = re.compile(
    r"es-de|emulationstation|emudeck|emulation/tools/launchers|emulation/roms/emulators|retroarch|org\.libretro"
    r"|dolphin|primehack|pcsx2|duckstation|ppsspp|cemu|ryujinx|yuzu|rpcs3|melonds|xemu|flycast|azahar|citra"
    r"|mame|scummvm|vita3k|shadps4|xenia|retrodeck",
    re.I)

# Cores whose core-level .rmp EmuDeck's layout switch renames to and from .rmp.disabled
# (RetroArch_setABXYstyle / RetroArch_setBAYXstyle, functions/EmuScripts/emuDeckRetroArch.sh @ dddb302).
EMUDECK_TOGGLED = ("mGBA", "Gambatte", "bsnes-hd beta", "melonDS DS", "Mupen64Plus-Next", "SameBoy", "Snes9x",
                   "Mesen", "Nestopia", "Beetle VB")

# RetroPad bind suffixes in retroarch.cfg (input_config_bind_map, configuration.c). A non-nul _btn/_axis here beats
# the controller profile's bind (input_driver.c falls back to auto_binds only for NO_BTN / AXIS_NONE).
PAD_BINDS = ("b", "y", "select", "start", "up", "down", "left", "right", "a", "x", "l", "r", "l2", "r2", "l3", "r3",
             "l_x_plus", "l_x_minus", "l_y_plus", "l_y_minus", "r_x_plus", "r_x_minus", "r_y_plus", "r_y_minus")
_PAD_BIND = re.compile(rf"^input_player(\d+)_({'|'.join(PAD_BINDS)})_(btn|axis)$")


@dataclass(frozen=True)
class Finding:
    severity: str   # error | warning | info
    check: str
    message: str


def run(steam_root: Path = STEAM_ROOT, retroarch_root: Path = RETROARCH_ROOT,
        emudeck_settings: Path = EMUDECK_SETTINGS, home: Path = HOME) -> list[Finding]:
    from . import setup
    from .writer import load_manifest
    settings = read_emudeck_settings(emudeck_settings)
    tracked = load_manifest(setup.Places(home=home).state_dir).get("retroarch", {}).get("files", {})
    return (check_steam_input(steam_root) + check_emudeck_automap(emudeck_settings, settings)
            + check_retroarch(retroarch_root, (settings or {}).get("controllerLayout"),
                              [rel for rel in sorted(tracked) if rel.endswith(".rmp")])
            + check_launch_hooks(home, steam_root))


# -- Steam Input per-game override ---------------------------------------------

def check_steam_input(steam_root: Path) -> list[Finding]:
    """A non-Steam shortcut set to "Disable Steam Input": the physical pads stay hidden from SDL (Steam's ignore
    list doesn't change) while Steam stops feeding the virtual pad, so the game gets no input at all (docs/13 S2).

    Read from userdata/<account>/config/localconfig.vdf, UserLocalConfigStore/apps/<unsigned shortcut id>/
    UseSteamControllerConfig, the key Steam-ROM-Manager writes for the same setting (docs/05). [VERIFY] on a Deck: the
    override set from Game Mode wasn't in localconfig.vdf 14 minutes later (Steam may only save it on exit).
    """
    userdata = Path(steam_root) / "userdata"
    if not userdata.is_dir():
        return [Finding("info", "steam-input", f"steam: no userdata under {steam_root}; Steam Input check skipped")]
    out, seen = [], 0
    for user in sorted(p for p in userdata.iterdir() if p.is_dir() and p.name.isdigit() and p.name != "0"):
        local = user / "config" / "localconfig.vdf"
        if not local.is_file():
            continue
        seen += 1
        try:
            apps = vdf.lookup(vdf.parse_text(local.read_text(encoding="utf-8", errors="replace")),
                              "UserLocalConfigStore", "apps") or {}
        except vdf.VdfError as e:
            out.append(Finding("warning", "steam-input", f"steam: couldn't read localconfig.vdf ({e})"))
            continue
        shortcuts, problem = _shortcuts(user / "config" / "shortcuts.vdf")
        if problem:
            out.append(Finding("info", "steam-input", f"steam: {problem}; shortcuts are shown by app id only"))
        matched = set()
        for sc in shortcuts:
            appid = vdf.lookup(sc, "appid")
            if not isinstance(appid, int):
                continue
            unsigned = appid & 0xFFFFFFFF
            legacy = str(unsigned - (1 << 32) if unsigned >= 1 << 31 else unsigned)
            matched.update((str(unsigned), legacy))
            name = vdf.lookup(sc, "AppName") or "?"
            text = " ".join(str(vdf.lookup(sc, k) or "") for k in ("AppName", "Exe", "StartDir", "LaunchOptions"))
            if not EMULATION.search(text):
                continue
            value = _steam_input(apps, [str(unsigned)])
            if value is None and _steam_input(apps, [legacy]) == STEAM_INPUT_OFF:
                # Older SRM wrote the signed id; current Steam reads only the unsigned one (SRM#891).
                out.append(Finding("info", "steam-input",
                                   f'steam: localconfig.vdf disables Steam Input for "{name}" under its old signed '
                                   f"id ({legacy}), which current Steam ignores"))
            if value == STEAM_INPUT_OFF:
                out.append(Finding("error", "steam-input",
                                   f'steam: "Disable Steam Input" is set on the non-Steam shortcut "{name}" '
                                   f"(app {unsigned}). EmuDeck's emulators bind Steam's virtual pad, so no "
                                   "controller works in anything it launches. In Game Mode: the shortcut's "
                                   "Properties > Controller, set it back to Default."))
        for key, entry in apps.items():
            if key in matched or not _is_shortcut_id(key) or not isinstance(entry, dict):
                continue
            if _steam_input({key: entry}, [key]) == STEAM_INPUT_OFF:
                out.append(Finding("warning", "steam-input",
                                   f"steam: Steam Input is disabled for app {int(key) & 0xFFFFFFFF}, a non-Steam "
                                   "shortcut that isn't in shortcuts.vdf; if it launches an emulator, no controller "
                                   "will work in it"))
    if not seen:
        out.append(Finding("info", "steam-input", f"steam: no localconfig.vdf under {userdata}; check skipped"))
    return out


def _shortcuts(path: Path) -> tuple[list[dict], Optional[str]]:
    if not path.is_file():
        return [], None
    try:
        tree = vdf.parse_binary(path.read_bytes())
    except vdf.VdfError as e:
        return [], f"couldn't read shortcuts.vdf ({e})"
    entries = vdf.lookup(tree, "shortcuts") or {}
    return [v for v in entries.values() if isinstance(v, dict)], None


def _steam_input(apps: dict, keys: list[str]) -> Optional[str]:
    for key in keys:
        value = vdf.lookup(apps, key, "UseSteamControllerConfig")
        if isinstance(value, str):
            return value.strip()
    return None


def _is_shortcut_id(key: str) -> bool:
    """Shortcut ids have the top bit set (SRM generatePreliminaryId: crc32 | 0x80000000); Steam's own don't."""
    try:
        n = int(key)
    except ValueError:
        return False
    return n < 0 or n >= 1 << 31


# -- EmuDeck AutoMap -------------------------------------------------------------

def read_emudeck_settings(path: Path) -> Optional[dict]:
    """EmuDeck's settings.sh (`name=value` lines it sources; generated from settings.json by jsonToBashVars)."""
    path = Path(path)
    if not path.is_file():
        return None
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


# settings.sh variable -> (emulator, managed by map-helper). EmuDeck's GUI keys are automap.{dolphin,cemu,yuzu}
# (yuzu covers every Switch emulator); jsonToBashVars and the GUI's AutoMapConfigPage write these variables.
AUTOMAP = (("autoMapDolphin", "Dolphin", True), ("autoMapCemu", "Cemu", False),
           ("autoMapSwitch", "the Switch emulators", False))


def check_emudeck_automap(path: Path, settings: Optional[dict]) -> list[Finding]:
    """EmuDeck AutoMap copies the stock input file over the emulator's at every launch through its launcher, after
    anything map-helper wrote (Dolphin_setGamepads, docs/07). Each emulator's script skips it only when its variable
    is "false", or empty/unset on a Deck. jq writes `null` for a missing JSON key, and "null" is neither, so it runs.
    Dolphin is the only emulator AutoMap touches that map-helper manages; the others are reported as info."""
    if settings is None:
        return [Finding("info", "emudeck-automap", f"emudeck: no settings at {path}; AutoMap check skipped")]
    out = []
    for var, emulator, managed in AUTOMAP:
        value = settings.get(var)
        if value == "false":
            continue
        if not value:
            if managed:
                out.append(Finding("info", "emudeck-automap",
                                   f"emudeck: {var} isn't set; EmuDeck skips AutoMap for {emulator} on a Steam Deck "
                                   "when it's unset, but runs it on other PCs"))
        elif managed:
            out.append(Finding("error", "emudeck-automap",
                               f"emudeck: AutoMap is on for {emulator} ({var}={value}). Every launch through EmuDeck's "
                               "launcher copies the stock GCPadNew.ini back and rewrites its devices, undoing "
                               f"map-helper's {emulator} bindings. Turn AutoMap off for {emulator} in the EmuDeck "
                               "app."))
        else:
            out.append(Finding("info", "emudeck-automap",
                               f"emudeck: AutoMap is on for {emulator} ({var}={value}); map-helper doesn't manage "
                               f"{emulator} yet, so nothing of ours is undone"))
    return out


# -- mh-run in the launch paths ---------------------------------------------------

def check_launch_hooks(home: Path = HOME, steam_root: Path = STEAM_ROOT) -> list[Finding]:
    """Is mh-run where `map-helper setup` puts it (docs/07): the shim, ES-DE's game-start script with custom event
    scripts on, SRM's parsers, and the Steam shortcuts SRM made from them. Before setup has run, it's all info."""
    import os
    from . import setup
    places = setup.Places(home=home)
    done = bool(setup.load_record(places.state_dir))
    missing = "error" if done else "info"
    out = []
    shim = setup._read(places.shim)
    if shim is None:
        out.append(Finding(missing, "launch-hooks", f"mh-run: no shim at {places.shim}, so launches don't apply "
                                                    "mappings; run `map-helper setup --write`"))
    else:
        entry = re.search(r"^MH='((?:[^']|'\\'')*)'$", shim, re.M)
        entry = Path(entry.group(1).replace("'\\''", "'")) if entry else None
        if not os.access(places.shim, os.X_OK):
            out.append(Finding("error", "launch-hooks", f"mh-run: {places.shim} isn't executable; launches through "
                                                        "it fail"))
        elif entry is None or not entry.is_file():
            out.append(Finding("warning", "launch-hooks", f"mh-run: the shim runs {entry or 'nothing'}, which isn't "
                                                          "there; launches go ahead without applying mappings"))
    if places.esde_root.is_dir():
        settings = setup._read(places.esde_settings) or ""
        m = setup._SETTING.search(settings)
        if not places.esde_script.is_file():
            out.append(Finding(missing, "launch-hooks", f"es-de: no game-start script at {places.esde_script}, so "
                                                        "games ES-DE starts don't get mappings applied"))
        elif not (m and m.group(1) == "true"):
            out.append(Finding("error", "launch-hooks", "es-de: custom event scripts are off, so ES-DE never runs "
                                                        "map-helper's game-start script. ES-DE: Main menu > Other "
                                                        "settings > Enable custom event scripts"))
    out += _srm_hooks(places, steam_root, done)
    return out


def _srm_hooks(places, steam_root: Path, done: bool) -> list[Finding]:
    from . import setup
    text = setup._read(places.srm_config)
    if text is None:
        return []
    try:
        parsers, _ = setup.parse_spans(text)
    except ValueError as e:
        return [Finding("warning", "launch-hooks", f"srm: couldn't read {places.srm_config} ({e})")]
    bare = [p.get("configTitle") or str(p.get("parserId")) for p in parsers if isinstance(p, dict)
            and setup.wrappable(p) and "mh-run" not in str(p.get("executableArgs") or "")]
    out = []
    if bare:
        out.append(Finding("warning" if done else "info", "launch-hooks",
                           f"srm: {len(bare)} parser(s) for emulators map-helper manages don't run mh-run "
                           f"({', '.join(bare[:3])}{', ...' if len(bare) > 3 else ''}); `map-helper setup --write` "
                           "adds it"))
    if not done:
        return out
    userdata = Path(steam_root) / "userdata"
    for user in sorted(p for p in userdata.iterdir() if p.is_dir()) if userdata.is_dir() else []:
        shortcuts, _ = _shortcuts(user / "config" / "shortcuts.vdf")
        stale = []
        for sc in shortcuts:
            exe, opts = str(vdf.lookup(sc, "Exe") or ""), str(vdf.lookup(sc, "LaunchOptions") or "")
            path, _, exe_args = exe.strip('"').partition('" ')
            parser = {"executable": {"path": path, "appendArgsToExecutable": bool(exe_args.strip())},
                      "executableArgs": exe + " " + opts}
            if setup.wrappable(parser) and "mh-run" not in exe + opts:
                stale.append(str(vdf.lookup(sc, "AppName") or "?"))
        if stale:
            out.append(Finding("warning", "launch-hooks",
                               f"steam: {len(stale)} emulator shortcut(s) don't run mh-run yet "
                               f"({', '.join(stale[:3])}{', ...' if len(stale) > 3 else ''}); run Steam ROM "
                               "Manager's \"Save to Steam\" to pick up the parser change"))
    return out


# -- RetroArch -------------------------------------------------------------------

def check_retroarch(root: Path, controller_layout: Optional[str] = None, managed: list[str] = ()) -> list[Finding]:
    """managed: the .rmp files map-helper writes (from its manifest)."""
    root = Path(root)
    cfg_path = root / "retroarch.cfg"
    if not cfg_path.is_file():
        return [Finding("info", "retroarch", f"retroarch: no retroarch.cfg in {root}; RetroArch checks skipped")]
    cfg = _read_cfg(cfg_path)
    out = _settings(cfg, "retroarch.cfg")
    if managed and cfg.get("remap_save_on_exit", "true") != "false":
        # Default true (config.def.h DEFAULT_REMAP_SAVE_ON_EXIT): input_remapping_deinit saves the loaded remap from
        # memory when content closes (docs/adapters/retroarch.md "doctor checks").
        names = ", ".join(Path(rel).name for rel in managed)
        out.append(Finding("warning", "retroarch-remap-save",
                           f"retroarch: remap_save_on_exit is on, so when a game closes RetroArch saves its remaps "
                           f"over map-helper's {names}; map-helper rewrites them at the next launch, so remap changes "
                           "made in RetroArch's Quick Menu don't last"))
    if cfg.get("auto_overrides_enable", "true") != "false":
        overrides = root / "config"
        for path in sorted(overrides.glob("*/*.cfg")) if overrides.is_dir() else []:
            out += _settings(_read_cfg(path), f"the override {path.relative_to(root).as_posix()}")
    remaps = remap_dir(root, cfg.get("input_remapping_directory"))
    if remaps is None:
        out.append(Finding("info", "retroarch-remaps",
                           f"retroarch: input_remapping_directory ({cfg['input_remapping_directory']}) is outside "
                           f"{root}; remap files not checked"))
    elif remaps.is_dir() and cfg.get("input_remap_sort_by_controller_enable") != "true":
        out += _remap_files(root, remaps, controller_layout)
    return out


def _read_cfg(path: Path) -> dict:
    """key -> unquoted value for every `key = "value"` line (RetroArch's config_file format)."""
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r'^\s*([^=#;\s]+)\s*=\s*"?(.*?)"?\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _settings(cfg: dict, where: str) -> list[Finding]:
    """Settings that switch remaps or controller profiles off. Overrides (config/<core>/*.cfg) can set them too."""
    out = []
    if cfg.get("auto_remaps_enable") == "false":
        out.append(Finding("error", "retroarch-remaps",
                           f"retroarch: auto_remaps_enable is false in {where}, so RetroArch never loads remap files "
                           "and map-helper's .rmp has no effect"))
    if cfg.get("input_remap_binds_enable") == "false":
        out.append(Finding("error", "retroarch-remaps",
                           f"retroarch: input_remap_binds_enable is false in {where}, so remaps are ignored"))
    if cfg.get("input_remap_sort_by_controller_enable") == "true":
        out.append(Finding("error", "retroarch-remaps",
                           f"retroarch: input_remap_sort_by_controller_enable is on in {where}; RetroArch looks for "
                           "remaps per controller name, so the core-level file map-helper writes isn't used"))
    if cfg.get("input_autodetect_enable") == "false":
        out.append(Finding("error", "retroarch-autoconfig",
                           f"retroarch: input_autodetect_enable is false in {where}, so RetroArch loads no controller "
                           "profile: pads get only the binds in retroarch.cfg (EmuDeck leaves them nul), and "
                           "map-helper's remaps assume the Steam Virtual Gamepad profile"))
    bound: dict[int, list[str]] = {}
    for key, value in cfg.items():
        m = _PAD_BIND.match(key)
        if m and value not in ("nul", ""):
            bound.setdefault(int(m.group(1)), []).append(f"{key} = {value}")
    for user, binds in sorted(bound.items()):
        more = f" and {len(binds) - 1} more" if len(binds) > 1 else ""
        out.append(Finding("warning", "retroarch-autoconfig",
                           f"retroarch: {where} binds pad buttons for user {user} ({sorted(binds)[0]}{more}). A bind "
                           "there beats the controller profile, so the RetroPad button a press sends isn't the one "
                           "map-helper's remaps assume"))
    return out


def remap_dir(root: Path, configured: Optional[str]) -> Optional[Path]:
    """input_remapping_directory, read against `root` when it names the Flatpak config root (as EmuDeck's does)."""
    if not configured or configured == "default":
        return root / REMAP_DIR
    if configured == FLATPAK_RA_ROOT or configured.startswith(FLATPAK_RA_ROOT + "/"):
        return root / configured[len(FLATPAK_RA_ROOT):].lstrip("/")
    path = Path(configured).expanduser()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _remap_files(root: Path, remaps: Path, layout: Optional[str]) -> list[Finding]:
    """config_load_remap tries <game>.rmp, then <content dir>.rmp, then <core>.rmp, and stops at the first that
    exists (docs/adapters/retroarch.md "Load precedence"). EmuDeck's layout switch renames core-level files."""
    out, parked = [], []
    for folder in sorted((p for p in remaps.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        core = folder.name
        own, disabled = folder / f"{core}.rmp", folder / f"{core}.rmp.disabled"
        rel = own.relative_to(root).as_posix()
        for shadow in sorted(folder.glob("*.rmp")):
            if shadow.name != own.name:
                out.append(Finding("warning", "retroarch-shadow",
                                   f"retroarch: {shadow.relative_to(root).as_posix()} is a game or content-dir remap; "
                                   f"when it matches, RetroArch loads it instead of {own.name}, with no layering"))
        if own.is_file() and disabled.is_file():
            out.append(Finding("warning", "emudeck-layout",
                               f"retroarch: {rel} sits next to EmuDeck's {disabled.name}. Switching EmuDeck's "
                               f"controller layout to ABXY moves EmuDeck's file over {own.name}; switching to BAYX "
                               "renames it to .rmp.disabled"))
        elif own.is_file() and core in EMUDECK_TOGGLED:
            whose = " (likely EmuDeck's own, controllerLayout=abxy)" if layout == "abxy" else ""
            out.append(Finding("warning", "emudeck-layout",
                               f"retroarch: {rel} is active{whose}. Switching EmuDeck's controller layout to BAYX "
                               "renames it to .rmp.disabled, which turns the core remap off"))
        elif disabled.is_file():
            parked.append(core)
    if parked:
        out.append(Finding("info", "emudeck-layout",
                           f"retroarch: EmuDeck's ABXY remaps are parked as .rmp.disabled (not loaded) for "
                           f"{len(parked)} cores: {', '.join(parked)}"))
    return out


# -- output ----------------------------------------------------------------------

def render(findings: list[Finding]) -> str:
    lines = [f"{f.severity}: {f.message}" for f in findings]
    errors = sum(f.severity == "error" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    if not errors and not warnings:
        lines.append("No problems found.")
    else:
        lines.append(f"{errors} error{'s' * (errors != 1)}, {warnings} warning{'s' * (warnings != 1)}.")
    return "\n".join(lines) + "\n"
