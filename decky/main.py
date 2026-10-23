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
# Decky's plugin socket buffers 1 MiB per message (docs/14 §2); the button map is far smaller.
MAX_OUTPUT_BYTES = 512 * 1024
SUPPORTED_SCHEMA = 1


def _home() -> str:
    return decky.DECKY_USER_HOME


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
        """What the last game launched through mh-run got: `map-helper show --last --json` (docs/08)."""
        try:
            if not os.path.isfile(PYTHON):
                return _fail("no-python", "This system has no /usr/bin/python3, which map-helper needs.")
            if not os.path.isfile(_entry()):
                return _fail("not-installed", "map-helper isn't installed on this Deck yet.")
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

    async def _main(self):
        decky.logger.info("map-helper backend started (core: %s)", _entry())

    async def _unload(self):
        # Nothing runs in the background yet, so there is nothing to stop. Must stay fast (docs/14 §2).
        decky.logger.info("map-helper backend stopped")

    async def _uninstall(self):
        # Also runs on every store update (docs/14 §2): never remove hooks, the core or user data here.
        pass
