"""map-helper's Decky backend.

A thin shim: the map-helper core runs out of process on the system Python
(`/usr/bin/python3 -I`), never inside Decky's bundled interpreter, which ships
only part of the stdlib (docs/14 §4). The backend runs as the desktop user,
not root (plugin.json has no "root" flag), and does nothing that needs root.

Every method called from the frontend returns a plain dict and never raises:
  {"ok": True, "data": {...}}
  {"ok": False, "code": "<code>", "error": "<plain words for the user>"}

Kept compatible with Python 3.10+ and limited to stdlib modules Decky's own
loader imports, since the bundle can change between Decky releases: asyncio,
json, os, re (decky_loader/helpers.py) and base64 (aiohttp/helpers.py; Decky
3.3.0's backend/pyproject.toml needs aiohttp ^3.10.11).
"""

import asyncio
import base64
import json
import os
import re

import decky

PYTHON = "/usr/bin/python3"
SHOW_TIMEOUT_S = 5.0
# An edit runs the launch pipeline twice for its before/after preview (docs/08): give it room on a busy Deck.
EDIT_TIMEOUT_S = 20.0
RULE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SYSTEM_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MAX_OPS_BYTES = 16 * 1024
MAX_LOGO_BYTES = 512 * 1024
LOGO_TYPES = {".svg": "image/svg+xml", ".png": "image/png"}
CONSOLE_ID = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
CONSOLE_TYPES = {".png": "image/png", ".jpg": "image/jpeg"}
MAX_CONSOLE_BYTES = 2 * 1024 * 1024
GLYPH_NAME = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
MAX_GLYPHS = 200
MAX_GLYPH_BYTES = 64 * 1024
# Steam's own button glyphs, the ones Steam Input hands games (GetGlyphSVGForActionOrigin): read from the user's Steam
# install at runtime, never shipped with the plugin. "knockout" are single-colour shapes, drawn as masks.
# Steam's controller pictures (its controller settings screen), by the only names the plugin asks for.
ART_DIR = (".local", "share", "Steam", "steamui", "images", "controller")
ART_FILES = {"xboxone": "controller_config_controller_xboxone.png",
             "generic": "controller_config_controller_generic.png", "ps5": "controller_config_controller_ps5.png",
             "switch_pro": "controller_config_controller_switch_pro.png",
             "steam_deck": "controller_config_controller_steam_deck.svg"}
GLYPH_DIR = (".local", "share", "Steam", "controller_base", "images", "api", "knockout")
# Decky's plugin socket buffers 1 MiB per message (docs/14 §2); the button map is far smaller.
MAX_OUTPUT_BYTES = 512 * 1024
SUPPORTED_SCHEMA = 1


def _home() -> str:
    return decky.DECKY_USER_HOME


def _steam_glyphs(names: list) -> dict:
    folder = os.path.join(_home(), *GLYPH_DIR)
    out = {}
    for name in dict.fromkeys(names):
        path = os.path.join(folder, f"{name}.svg")
        try:
            if os.path.getsize(path) <= MAX_GLYPH_BYTES:
                with open(path, encoding="utf-8") as f:
                    out[name] = f.read()
        except OSError:
            continue
    return out


def _console_art(system: str, controller: str):
    """Public-domain photo of the console's controller shipped in assets/consoles (<system>-<controller> or
    <system>), with its traced spots; None when there is none."""
    # The zip ships them in the plugin's assets/; a developer copy (tools/deck.sh plugin) goes to the plugin's data
    # folder, since an installed plugin's own folder belongs to root.
    folders = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "consoles"),
               os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "consoles")]
    for folder, name in ((f, n) for f in folders for n in (f"{system}-{controller}", system)):
        meta = os.path.join(folder, f"{name}.json")
        if not os.path.isfile(meta):
            continue
        with open(meta, encoding="utf-8") as f:
            info = json.load(f)
        image = os.path.join(folder, os.path.basename(info.get("file", "")))
        ext = os.path.splitext(image)[1]
        if ext not in CONSOLE_TYPES or not os.path.isfile(image) or os.path.getsize(image) > MAX_CONSOLE_BYTES:
            return None
        with open(image, "rb") as f:
            url = f"data:{CONSOLE_TYPES[ext]};base64,{base64.b64encode(f.read()).decode('ascii')}"
        return {"url": url, **{k: info[k] for k in ("width", "height", "spots", "hidden", "edge", "background") if k in info}}
    return None


def _entry() -> str:
    return os.path.join(_home(), ".local", "lib", "map-helper", "current", "mh_entry.py")


def _last_launch_file() -> str:
    # $STATE (docs/09). The loader's environment has no XDG_* variables (docs/14 §2), so this is the default.
    return os.path.join(_home(), ".local", "state", "map-helper", "last-launch.json")


def _child_env() -> dict:
    """A minimal environment for the core: Decky's own (root service, PyInstaller paths) must not leak in."""
    env = {
        "HOME": _home(),
        "USER": decky.DECKY_USER,
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
    }
    # PyInstaller points LD_LIBRARY_PATH at its bundle; give system programs the original back (docs/14 §4).
    original = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if original:
        env["LD_LIBRARY_PATH"] = original
    return env


def _fail(code: str, error: str) -> dict:
    return {"ok": False, "code": code, "error": error}


def _last_line(data: bytes) -> str:
    lines = data.decode("utf-8", "replace").strip().splitlines()
    return lines[-1][:200] if lines else ""


async def _run_core(*args: str, timeout: float = SHOW_TIMEOUT_S):
    """Run the core with a timeout. Returns (returncode, stdout, stderr), or None on timeout."""
    proc = await asyncio.create_subprocess_exec(
        PYTHON, "-I", _entry(), *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_child_env(),
        cwd=_home(),
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None
    return proc.returncode, out, err


def _parse_show(out: bytes) -> dict:
    text = out.decode("utf-8", "replace").strip()
    if not text or text == "null":
        return _fail("no-launch", "No game has been launched through map-helper yet.")
    if len(out) > MAX_OUTPUT_BYTES:
        decky.logger.warning("show --last printed %d bytes, over the %d limit", len(out), MAX_OUTPUT_BYTES)
        return _fail("bad-output", "map-helper's answer was too large to show.")
    try:
        data = json.loads(text)
    except ValueError as e:
        decky.logger.warning("show --last printed something that isn't JSON: %s", e)
        return _fail("bad-output", "map-helper answered, but its answer couldn't be read.")
    if not isinstance(data, dict) or not isinstance(data.get("players"), list):
        decky.logger.warning("show --last printed JSON without a players list")
        return _fail("bad-output", "map-helper answered, but its answer couldn't be read.")
    schema = data.get("schema")
    if schema != SUPPORTED_SCHEMA:
        decky.logger.warning("show --last schema %r, this plugin reads %d", schema, SUPPORTED_SCHEMA)
        return _fail("bad-output", "map-helper's data is from a different version than this plugin. Update both.")
    return {"ok": True, "data": data}


async def _rules(*args: str, timeout: float = SHOW_TIMEOUT_S) -> dict:
    """`map-helper rules ARGS --json`. The core prints {"error": ...} and exits 2 when it refuses a change."""
    if not os.path.isfile(PYTHON):
        return _fail("no-python", "This system has no /usr/bin/python3, which map-helper needs.")
    if not os.path.isfile(_entry()):
        return _fail("not-installed", "map-helper isn't installed on this Deck yet.")
    result = await _run_core("rules", *args, "--json", timeout=timeout)
    if result is None:
        decky.logger.warning("rules %s timed out after %.0f s", args[0], timeout)
        return _fail("timeout", f"map-helper took too long to answer (over {timeout:.0f} seconds).")
    code, out, err = result
    try:
        data = json.loads(out.decode("utf-8", "replace")) if len(out) <= MAX_OUTPUT_BYTES else None
    except ValueError:
        data = None
    if code == 2 and isinstance(data, dict) and "error" in data:
        return _fail("refused", str(data["error"]))
    if code != 0 or not isinstance(data, dict):
        detail = _last_line(err)
        decky.logger.warning("rules %s exited %d: %s", args[0], code, detail)
        return _fail("failed", f"map-helper couldn't do that: {detail or f'exit code {code}'}")
    return {"ok": True, "data": data}


def _ids(ids) -> list:
    if not isinstance(ids, list) or not ids or len(ids) > 64 or not all(
            isinstance(i, str) and RULE_ID.match(i) for i in ids):
        raise ValueError("bad rule ids")
    return ids


def _esde_logo(system: str):
    """(mime, bytes) of the system's logo in the user's active ES-DE theme, or None. ES-DE keeps the theme's
    directory name as the `Theme` string in ~/ES-DE/settings/es_settings.xml (es-core/src/Settings.cpp L164 @
    a529a9d); the logo path is the RetroFix Revisited layout, the theme on the owner's Deck. Themes bundled
    inside ES-DE itself (linear-es-de, slate-es-de) aren't on disk, so they give None."""
    esde = os.path.join(_home(), "ES-DE")
    try:
        with open(os.path.join(esde, "settings", "es_settings.xml"), encoding="utf-8", errors="replace") as f:
            settings = f.read(1024 * 1024)
    except OSError:
        return None
    m = re.search(r'<string\s+name="Theme"\s+value="([^"<>]*)"', settings)
    theme = m.group(1) if m else ""
    if not theme or "/" in theme or "\\" in theme or theme.startswith("."):
        return None
    for ext, mime in LOGO_TYPES.items():
        path = os.path.join(esde, "themes", theme, "_inc", "systems", "logos", system + ext)
        try:
            if os.path.isfile(path) and os.path.getsize(path) <= MAX_LOGO_BYTES:
                with open(path, "rb") as f:
                    return mime, f.read()
        except OSError:
            continue
    return None


class Plugin:
    async def get_last_launch(self) -> dict:
        """The last game launched through mh-run as it would start now, with the pads connected now and the rules as
        they are now (`map-helper show --now --json`); what that launch got (`show --last`) when that fails (docs/08)."""
        try:
            if not os.path.isfile(PYTHON):
                return _fail("no-python", "This system has no /usr/bin/python3, which map-helper needs.")
            if not os.path.isfile(_entry()):
                return _fail("not-installed", "map-helper isn't installed on this Deck yet.")
            if os.path.isfile(_last_launch_file()):
                now = await _run_core("show", "--now", "--json")
                if now is not None and now[0] == 0:
                    answer = _parse_show(now[1])
                    if answer["ok"]:
                        return answer
                decky.logger.warning("show --now failed (%s); showing the last launch as recorded",
                                     "timeout" if now is None else _last_line(now[2]) or f"exit {now[0]}")
            result = await _run_core("show", "--last", "--json")
            if result is None:
                decky.logger.warning("show --last timed out after %.0f s", SHOW_TIMEOUT_S)
                return _fail("timeout", f"map-helper took too long to answer (over {SHOW_TIMEOUT_S:.0f} seconds).")
            code, out, err = result
            # With nothing recorded the core says so in plain text, even with --json (and exits 0).
            if not os.path.isfile(_last_launch_file()):
                return _fail("no-launch", "No game has been launched through map-helper yet.")
            if code != 0:
                detail = _last_line(err)
                decky.logger.warning("show --last exited %d: %s", code, detail)
                return _fail("failed", f"map-helper couldn't read the last launch: {detail or f'exit code {code}'}")
            return _parse_show(out)
        except Exception:
            decky.logger.exception("get_last_launch failed")
            return _fail("failed", "Something went wrong while asking map-helper. The plugin log has details.")

    async def get_rules(self) -> dict:
        """Every rule in $DATA/rules and rules-off, on and off: `map-helper rules list`."""
        try:
            return await _rules("list")
        except Exception:
            decky.logger.exception("get_rules failed")
            return _fail("failed", "Something went wrong while asking map-helper. The plugin log has details.")

    async def get_targets(self, system: str) -> dict:
        """The console inputs a rule can set for a system, for "Give it a job"."""
        try:
            if not isinstance(system, str) or not SYSTEM_ID.match(system):
                return _fail("refused", "That isn't a system map-helper knows.")
            return await _rules("targets", "--system", system)
        except Exception:
            decky.logger.exception("get_targets failed")
            return _fail("failed", "Something went wrong while asking map-helper. The plugin log has details.")

    async def edit_rules(self, ops: list, dry_run: bool = False) -> dict:
        """Carry out edit ops (map-helper rules edit; the core validates every op and the rules it writes) and say
        what they change for the pads connected now. dry_run previews without writing."""
        try:
            text = json.dumps(ops)
            if not isinstance(ops, list) or not ops or len(text) > MAX_OPS_BYTES:
                return _fail("refused", "That change couldn't be read.")
            return await _rules("edit", "--ops", text, *(["--dry-run"] if dry_run else []), timeout=EDIT_TIMEOUT_S)
        except Exception:
            decky.logger.exception("edit_rules failed")
            return _fail("failed", "Something went wrong while saving. The plugin log has details.")

    async def set_player_order(self, models: list) -> dict:
        """`map-helper players set MODEL...` (player 1 first), or `clear` for an empty list: Steam's order again."""
        try:
            if not isinstance(models, list) or len(models) > 16 or not all(
                    isinstance(m, str) and RULE_ID.match(m) for m in models):
                return _fail("refused", "Those aren't pad models.")
            if not os.path.isfile(_entry()):
                return _fail("not-installed", "map-helper isn't installed on this Deck yet.")
            result = await _run_core("players", *(["set", *models] if models else ["clear"]), "--json")
            if result is None:
                return _fail("timeout", "map-helper took too long to answer.")
            code, out, err = result
            if code != 0:
                return _fail("refused" if code == 2 else "failed", _last_line(err) or f"exit code {code}")
            return {"ok": True, "data": json.loads(out.decode("utf-8", "replace"))}
        except Exception:
            decky.logger.exception("set_player_order failed")
            return _fail("failed", "Something went wrong while saving the player order.")

    async def set_rules_on(self, ids: list, on: bool) -> dict:
        try:
            return await _rules("enable" if on else "disable", *_ids(ids))
        except ValueError:
            return _fail("refused", "That rule couldn't be found.")
        except Exception:
            decky.logger.exception("set_rules_on failed")
            return _fail("failed", "Something went wrong while saving. The plugin log has details.")

    async def delete_rules(self, ids: list) -> dict:
        try:
            return await _rules("delete", *_ids(ids))
        except ValueError:
            return _fail("refused", "That rule couldn't be found.")
        except Exception:
            decky.logger.exception("delete_rules failed")
            return _fail("failed", "Something went wrong while deleting. The plugin log has details.")

    async def reset_rules(self, system: str, game, dry_run: bool = False) -> dict:
        """Turn off the rules for one game (game set) or a whole system; turning them on again undoes it."""
        try:
            if not isinstance(system, str) or not SYSTEM_ID.match(system) or not (
                    game is None or (isinstance(game, str) and 0 < len(game) <= 512)):
                return _fail("refused", "That isn't a system or game map-helper knows.")
            args = ["reset", "--system", system, *(["--game", game] if game else []),
                    *(["--dry-run"] if dry_run else [])]
            return await _rules(*args)
        except Exception:
            decky.logger.exception("reset_rules failed")
            return _fail("failed", "Something went wrong while resetting. The plugin log has details.")

    async def get_system_logo(self, system: str) -> dict:
        """The system's logo from the active ES-DE theme, as a data URL; never shipped with the plugin."""
        try:
            if not isinstance(system, str) or not SYSTEM_ID.match(system):
                return _fail("refused", "That isn't a system id.")
            found = await asyncio.get_running_loop().run_in_executor(None, _esde_logo, system)
            if found is None:
                return _fail("no-logo", "The ES-DE theme has no logo for this system.")
            mime, data = found
            return {"ok": True, "data": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}}
        except Exception:
            decky.logger.exception("get_system_logo failed")
            return _fail("failed", "Couldn't read the ES-DE theme.")

    async def get_controller_art(self, name: str) -> dict:
        """Steam's picture of a pad as a data URL; never shipped with the plugin."""
        try:
            if name not in ART_FILES:
                return _fail("refused", "That isn't a controller picture map-helper knows.")
            path = os.path.join(_home(), *ART_DIR, ART_FILES[name])
            if not os.path.isfile(path) or os.path.getsize(path) > MAX_LOGO_BYTES:
                return _fail("no-art", "Steam has no picture of this controller.")
            with open(path, "rb") as f:
                data = f.read()
            mime = LOGO_TYPES[os.path.splitext(path)[1]]
            return {"ok": True, "data": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}}
        except Exception:
            decky.logger.exception("get_controller_art failed")
            return _fail("failed", "Couldn't read Steam's controller picture.")

    async def get_console_art(self, system: str, controller: str) -> dict:
        """A photo of the emulated console's controller and where its buttons are."""
        try:
            if not all(isinstance(v, str) and CONSOLE_ID.match(v) for v in (system, controller)):
                return _fail("refused", "That isn't a console map-helper knows.")
            found = await asyncio.get_running_loop().run_in_executor(None, _console_art, system, controller)
            return {"ok": True, "data": found} if found else _fail("no-art", "No picture of this console's controller.")
        except Exception:
            decky.logger.exception("get_console_art failed")
            return _fail("failed", "Couldn't read the console picture.")

    async def get_steam_glyphs(self, names: list) -> dict:
        """{name: svg text} for each of Steam's knockout glyphs asked for that exists; missing names are left out."""
        try:
            if not isinstance(names, list) or len(names) > MAX_GLYPHS or \
                    not all(isinstance(n, str) and GLYPH_NAME.match(n) for n in names):
                return _fail("refused", "Those aren't glyph names.")
            found = await asyncio.get_running_loop().run_in_executor(None, _steam_glyphs, names)
            return {"ok": True, "data": found}
        except Exception:
            decky.logger.exception("get_steam_glyphs failed")
            return _fail("failed", "Couldn't read Steam's controller glyphs.")

    async def _main(self):
        decky.logger.info("map-helper backend started (core: %s)", _entry())

    async def _unload(self):
        # Nothing runs in the background yet, so there is nothing to stop. Must stay fast (docs/14 §2).
        decky.logger.info("map-helper backend stopped")

    async def _uninstall(self):
        # Also runs on every store update (docs/14 §2): never remove hooks, the core or user data here.
        pass
