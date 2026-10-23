"""map-helper's Decky backend.

A thin shim: the map-helper core runs out of process on the system Python
(`/usr/bin/python3 -I`), never inside Decky's bundled interpreter, which ships
only part of the stdlib (docs/14 §4). The backend runs as the desktop user,
not root (plugin.json has no "root" flag), and does nothing that needs root.

Every method called from the frontend returns a plain dict and never raises:
  {"ok": True, "data": {...}}
  {"ok": False, "code": "<code>", "error": "<plain words for the user>"}

Kept compatible with Python 3.10+ and limited to stdlib modules Decky's own
loader imports (asyncio, json, os), since the bundle can change between
Decky releases.
"""

import asyncio
import json
import os

import decky

PYTHON = "/usr/bin/python3"
SHOW_TIMEOUT_S = 5.0
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


async def _run_core(*args: str):
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
        out, err = await asyncio.wait_for(proc.communicate(), SHOW_TIMEOUT_S)
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

    async def _main(self):
        decky.logger.info("map-helper backend started (core: %s)", _entry())

    async def _unload(self):
        # Nothing runs in the background yet, so there is nothing to stop. Must stay fast (docs/14 §2).
        decky.logger.info("map-helper backend stopped")

    async def _uninstall(self):
        # Also runs on every store update (docs/14 §2): never remove hooks, the core or user data here.
        pass
