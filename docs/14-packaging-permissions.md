# 14 — Packaging, Runtime & Permissions

How map-helper is packaged as a Decky plugin, which Python runs it, what it may
touch, how the launch hook and CLI get `mh-core`, and how releases reach users.

Facts below come from the Decky Loader, plugin template, frontend library,
CLI, plugin database and wiki repos at the commits listed in
[Sources](#sources) (all read on 2026-10-22), plus Valve's SteamOS package
mirror. Anything not confirmed on a device is tagged **[VERIFY]**.

## Summary of decisions

| Topic | Decision |
|-------|----------|
| Backend privilege | **Not root** (`"flags": []`). The backend runs as `deck`. |
| Where `mh-core` runs | In a **subprocess on the system Python** (`/usr/bin/python3 -I`), not inside Decky's bundled interpreter. `main.py` is a thin RPC shim. |
| Where `mh-core` is installed | `~/.local/lib/map-helper/versions/<ver>/` with an atomic `current` symlink. The plugin directory is only the payload that gets installed from. |
| Launch hook / CLI | POSIX `sh` shims in `~/.local/bin/` (`mh-run`, `map-helper`) that call the `current` install and **fail open**. |
| Python floor | **3.11** for `mh-core` (oldest system Python on a supported SteamOS). `main.py` stays 3.10-compatible. |
| Store repo shape | The store submodule points at a generated **`decky-release` branch** whose root is the plugin (real files, no symlinks). |
| Versioning | One semver for plugin and core. `package.json` `version` is the source of truth for the store. |

## 1. Decky plugin structure

### What Decky expects

From the plugin template README ("Distribution") and the Decky CLI packager
(`src/cli/plugin/build.rs`, `zip_plugin`):

```
<plugin>.zip
└── <plugin>/
    ├── dist/index.js      required (frontend bundle built by rollup)
    ├── package.json       required (version comes from here)
    ├── plugin.json        required
    ├── main.py            required if there is a Python backend
    ├── LICENSE            required by the store
    ├── README.md          optional
    ├── *.py               every top-level .py file is zipped too
    ├── py_modules/        optional; appended to sys.path of the backend
    ├── bin/               optional; output of backend/ custom-binary builds (mode 0755)
    └── <contents of defaults/>   copied into the plugin root (defaults/ itself disappears)
```

- `py_modules/` is appended to `sys.path` by the loader
  (`sandboxed_plugin.py`: `sys.path.append(path.join(DECKY_PLUGIN_DIR, "py_modules"))`).
- The CLI **skips symlinks** in `py_modules/` unless run with follow-symlinks;
  the store CI doesn't pass that flag (`build-plugins.yml` runs
  `decky plugin build -b -o /tmp/output -s directory plugins/$plugin`). So the
  core must be committed as real files in the store branch.
- `defaults/` entries are zipped with default permissions, so the execute bit
  is lost. Shims must be `chmod`ed when we install them, or invoked via `sh`.
- Review rule: remove `backend/`, `assets/` and `defaults/` if unused, and
  delete the template's `defaults/defaults.txt` (wiki, *Review and Testing* step 7).

### `plugin.json` fields

The loader reads `name`, `author`, `flags` and `api_version`
(`plugin/plugin.py`). The store CI reads `publish.description`,
`publish.image` and `publish.tags` (`build-plugins.yml`, upload step).

- `flags`: `"root"` runs the backend as root (`sandboxed_plugin.py` calls
  `setgid`/`setuid` to the host user unless `"root" in flags`). The template
  ships `"_root"`, which is just an inert string that disables it. `"debug"`
  makes the loader hot-reload the plugin when files change (`loader.py`
  `import_plugin`: without `debug`, a refresh is ignored).
- `api_version: 1` is needed for the current API: positional args from
  `callable`, and `Plugin` instantiated as an object (`api_version > 0`
  branches in `sandboxed_plugin.py`).
- `name` is the plugin's identity. It's used for routing backend calls, for
  update matching (`checkForPluginUpdates` keys on it), and for the
  settings, data and log directory names.

Draft:

```json
{
  "name": "map-helper",
  "author": "<maintainer>",
  "flags": [],
  "api_version": 1,
  "publish": {
    "tags": ["controller", "emulation", "input"],
    "description": "Per-controller, per-system and per-game controller mappings for emulators, applied at launch.",
    "image": "https://raw.githubusercontent.com/<owner>/map-helper/main/decky/assets/store.png"
  }
}
```

### `package.json`

Template (at `90d0780`): `"type": "module"` (the loader then uses the ES module
load path, `PluginLoadType.ESMODULE_V1`), rollup build via `@decky/rollup`,
`@decky/ui` ^4.11 (dev), `@decky/api` ^1.1.3 (runtime), pnpm **v9** with
`pnpm-lock.yaml` `lockfileVersion: 9.0` (the store CI pins pnpm 9.4.0;
reviewers check the lockfile version). Current npm releases: `@decky/ui`
4.16.0 (2026-10-20), `@decky/api` 1.1.3 (2025-11-20).

### Store branch file tree

The repo stays as laid out in [02](02-architecture.md). A release workflow
renders the plugin into an orphan branch `decky-release`, and the store
submodule pins a commit on it:

```
(decky-release branch root)
├── plugin.json
├── package.json            version = release version
├── pnpm-lock.yaml          lockfileVersion 9.0
├── rollup.config.js
├── tsconfig.json
├── LICENSE                 our license on top, template BSD-3-Clause notice below
├── README.md
├── main.py                 thin shim: lifecycle, install, worker RPC (no mh-core import on the hot path)
├── src/                    TypeScript frontend (index.tsx, routes/, components/)
├── assets/store.png
└── py_modules/
    └── maphelper/          real copy of core/maphelper, incl. package data
        ├── VERSION
        ├── data/           controllers.json, layouts/, defaults/
        ├── shims/          mh-run.sh, map-helper.sh (installed + chmod 0755)
        └── ...
```

The source stays readable and unminified. The store bans private repos,
black-box binaries and obfuscation (wiki, *Submitting Plugins*), and the store
CI builds the frontend from `src/` itself.

## 2. Backend API (Decky 3.x)

- **Class and methods.** `main.py` defines `class Plugin` with `async` methods.
  Any public coroutine is callable from the frontend with positional,
  JSON-serialisable args (`on_new_message`: `getattr(self.Plugin, method)(*args)`).
  Exceptions come back as `success: false` with `str(e)`. Messages between
  loader and plugin travel over a per-plugin Unix socket
  (`/tmp/plugin_socket_<ts>`, line-delimited JSON, 1 MiB buffer limit:
  `localsocket.py` `BUFFER_LIMIT`). Keep responses small and page large lists.
- **Lifecycle.** `_migration()` runs synchronously before `_main()`.
  `_main()` runs as a task on the plugin's own event loop. `_unload()` runs on
  stop. `_uninstall()` runs after `_unload()` when the loader sends
  `{"uninstall": true}`.
  - **`_uninstall` also fires on every store update.** `browser.py`
    `_install` calls `uninstall_plugin(name)` when the plugin is already
    installed, which calls `stop(uninstall=True)` and then `rmtree(plugin_dir)`.
    Never undo hooks or delete user data in `_uninstall`. **[VERIFY]** on
    device by updating a test plugin and checking its log.
  - **Stops are SIGKILLed after 5 s** (`plugin.py` `kill_if_still_running`).
    Open issue #975 (2026-10-03) reports `_unload` / `_uninstall` often never
    completing because of a socket EOF spin. Treat both hooks as best effort.
    They must be fast, idempotent and non-critical.
- **Events to frontend.** `await decky.emit("event", *args)`. The frontend
  listens with `addEventListener("event", fn)` from `@decky/api`. We stream
  capture events this way.
- **`decky` module** (`decky.pyi` in the template): `HOME`, `USER`,
  `DECKY_USER`, `DECKY_USER_HOME`, `DECKY_HOME`, `DECKY_VERSION`,
  `DECKY_PLUGIN_SETTINGS_DIR` (`~/homebrew/settings/<dir>`),
  `DECKY_PLUGIN_RUNTIME_DIR` (`~/homebrew/data/<dir>`),
  `DECKY_PLUGIN_LOG_DIR` (`~/homebrew/logs/<dir>`), `DECKY_PLUGIN_DIR`,
  `DECKY_PLUGIN_NAME`, `DECKY_PLUGIN_VERSION`, `DECKY_PLUGIN_AUTHOR`,
  `DECKY_PLUGIN_LOG`, `logger`, `emit`, and `migrate_*` helpers. These are also
  exported as environment variables, so subprocesses inherit them.
- **Environment caveat.** The loader runs as a root systemd service
  (`dist/plugin_loader-release.service`: `User=root`). The plugin process
  inherits that environment and then gets `HOME` and `USER` overridden.
  Don't expect `XDG_RUNTIME_DIR`, `XDG_*_HOME` or a D-Bus session bus. `mh-core`
  must derive paths from `DECKY_USER_HOME` and `os.getuid()`
  (`/run/user/<uid>`), not from `XDG_*` defaults. **[VERIFY]** with
  `cat /proc/<backend pid>/environ`.

We keep map-helper's own state in the XDG locations from
[09](09-storage-safety-sync.md), not in the `DECKY_PLUGIN_*` dirs, because the
CLI and hook have to find it without Decky. The template docstring says
"Avoid writing outside of `DECKY_HOME`", but that's advice, not a store rule.
Only Decky-specific UI state (last tab and similar) goes in
`DECKY_PLUGIN_SETTINGS_DIR`.

## 3. Frontend API

From `@decky/api` (`loader-api` `src/index.ts`, `types.ts`) and the loader
frontend (`plugin-loader.tsx`, `router-hook.tsx`):

| API | Use in map-helper |
|-----|-------------------|
| `definePlugin(() => ({ name, titleView, content, icon, onDismount, alwaysRender? }))` | QAM panel entry |
| `callable<[args], Ret>("method")` / `call("method", ...args)` | All backend calls. They go over the loader's WebSocket (`loader/call_plugin_method`) and on to the plugin socket. |
| `addEventListener` / `removeEventListener` | Capture event stream, "new controller" and "drift" notices |
| `routerHook.addRoute(path, Component, props)` / `removeRoute(path)` | Full-screen Wizard, Matrix and Rule editor. Remove them in `onDismount`. |
| `toaster.toast({ title, body, onClick?, duration?, critical?, ... })` | Notifications. **No action buttons**, only one `onClick`. |
| `openFilePicker`, `useQuickAccessVisible`, `fetchNoCors` | Import/export `.mhpack.json`. Pause polling while the QAM is hidden. We don't use the network. |

Navigation to a route uses the template's pattern:
`Navigation.Navigate("/map-helper/wizard"); Navigation.CloseSideMenus();`.

Gamepad handling in `@decky/ui` 4.16 (`components/FooterLegend.ts`,
`Focusable.ts`): `onButtonDown` / `onButtonUp` (there is no
`onGamepadButtonDown`), `onOKButton`, `onCancelButton`, `onSecondaryButton`,
`onOptionsButton`, `onMenuButton`, `onGamepadDirection`, and `Focusable`'s
`onActivate` / `onCancel`. The event detail is `{ button: GamepadButton,
is_repeat?, source }`, with **no controller index**. Feasibility for capture
is discussed in [08](08-ui-ux.md#flow-2-the-mapping-wizard).

## 4. Python runtime facts

### Decky's bundled Python

- Decky ships as a single **PyInstaller** executable (`backend/pyinstaller.spec`,
  `EXE(... name="PluginLoader")`). Plugins run inside that interpreter: the
  loader forks a `multiprocessing.Process` per plugin and execs `main.py`
  with `spec_from_file_location`.
- Version: **Python 3.14.8 since Decky v3.3.0** (released 2026-10-18; CI
  changed from 3.11.7 in commit `636b86cf`). v3.2.x used 3.11.7 (since
  2024-06, `e266258f`) and before that 3.10.6. `pyproject.toml` allows
  `>=3.10,<3.15`. Users update Decky on their own schedule, so a plugin must
  run on 3.11 **and** 3.14.
- **Only part of the stdlib is available.** PyInstaller bundles only what
  the loader imports plus `hiddenimports` (`logging.handlers`, `sqlite3`,
  `http.server`, `socketserver`, `configparser`). Issue #968 (2026-09): v3.2.9
  dropped from 642 to 398 bundled modules after a setuptools bump, and plugins
  importing `http.server`, `glob` or `configparser` broke. A maintainer's
  first reply was "you shouldn't be relying on this". Modules `mh-core` needs
  (`tomllib`, `xml.etree`, `fcntl`, `zipfile`, `difflib`, ...) may or may not
  be in the bundle, and that can change between Decky releases.
- `py_modules/` lets a plugin ship pure-Python modules. It can't fill in
  missing C-extension stdlib modules (`_elementtree`, `_hashlib`, ...).
- **No sandbox.** The plugin process is a normal process with the host user's
  uid/gid (or root). The loader calls `os.setgid` and then `os.setuid`
  without `setgroups`/`initgroups`, so the process keeps the root service's
  supplementary group list. **[VERIFY]** `grep Groups /proc/<backend pid>/status`
  (likely empty). Either way, map-helper must not depend on `deck`'s groups.
- Child processes inherit PyInstaller's `LD_LIBRARY_PATH`. PyInstaller's docs
  say to restore `LD_LIBRARY_PATH_ORIG` (or unset it) before spawning system
  programs. Decky's own `localplatformlinux.run()` passes
  `LD_LIBRARY_PATH: ""`. Our worker spawn must do the same.

### SteamOS system Python

From Valve's package mirror (`steamdeck-packages.steamos.cloud/archlinux-mirror`):

| SteamOS branch | `python` package |
|----------------|------------------|
| 3.5 | 3.11.3 |
| 3.6 | 3.11.7 |
| 3.7 | 3.13.1 |
| **3.8 (Stable; 3.8.28 released 2026-09-24)** | **3.13.5** |
| 3.9 (Beta: 3.9.4 out, 2026-10) | 3.14.6 |

- On a Deck, `/usr/bin/python3` is a **hard dependency of Valve's hardware
  support package**. `jupiter-hw-support` 3.8 depends on `python>=3.13`,
  `python<3.14` and `python-evdev` (repo db `jupiter-3.8`). It's in the
  read-only image, so it's always present on Steam Deck SteamOS. It's
  replaced, and its minor version may change, on every OS update.
- Non-Deck SteamOS hardware doesn't install `jupiter-hw-support`. **[VERIFY]**
  that `python` is in the base image there (it's widely depended on by other
  SteamOS tools).
- `python-evdev`, `python-hid` and `python-pyudev` are in Valve's repos and
  (via `jupiter-hw-support`) installed on Decks. ADR-002 still holds: **don't
  depend on them** (not portable to other handhelds, and the version
  changes with the OS). The core uses `fcntl.ioctl` and `struct` directly.
- Usable from launcher scripts: yes. Call it as **`/usr/bin/python3 -I`**.
  `-I` ignores `PYTHON*` env vars, user site-packages and the script/cwd
  path, so a Steam- or emulator-provided environment can't inject modules.
  Because `-I` drops the script dir from `sys.path`, the entry script inserts
  its own real directory explicitly.
- PEP 594 removals (3.13: `cgi`, `crypt`, `telnetlib`, ...) don't affect us.
  CI must test 3.11, 3.13 and 3.14.

### Decision: run `mh-core` out of process

`main.py` imports only the stdlib modules the loader itself uses (`asyncio`,
`json`, `os`, `shutil`, `subprocess`). It:

1. installs or updates `mh-core` into `~/.local/lib/map-helper/` (§6),
2. spawns one long-lived worker on demand:
   `/usr/bin/python3 -I ~/.local/lib/map-helper/current/mh_entry.py rpc`,
   with a cleaned environment (`LD_LIBRARY_PATH` restored, `HOME` =
   `DECKY_USER_HOME`, `XDG_RUNTIME_DIR=/run/user/<uid>`, minimal `PATH`),
3. forwards each frontend call as one JSON line on the worker's stdin and
   returns the matching JSON line from stdout. Capture events are pushed on
   with `decky.emit`,
4. kills the worker in `_unload` (fast, so the stop doesn't hit the 5 s SIGKILL).

Why: the CLI, the hook and the UI then share **one interpreter and one code
path**. Decky's shrinking stdlib bundle can't break us, and one worker
startup is paid once per session, not per call. There's precedent: *Controller
Tools* (store plugin, non-root) also runs its real backend as a subprocess
from `_main`. Fallback if `/usr/bin/python3` is missing (non-SteamOS distro):
import `maphelper` from `py_modules` in-process in a degraded, read-only mode,
and show a warning in Settings.

This changes ADR-002's "Decky backend imports `mh-core` directly" (also in
[02](02-architecture.md) components table). The core is still a library. Only
the process boundary moves.

## 5. Root vs user backend

**Decision: user (`"flags": []`).**

| Need | As `deck` | Needs root? |
|------|-----------|-------------|
| Read/write emulator configs, rules, state under `~` | Yes, with correct ownership automatically | No. As root it's actively harmful: files would end up root-owned. |
| Read `/dev/input/event*` for **gamepads** | Yes, via `uaccess` ACL (below) | No |
| Read `/dev/hidraw*` for Sony/Nintendo/8BitDo/Valve pads | Yes, if Valve's udev rules are present **[VERIFY]** | Only for pads not covered |
| sysfs (`/sys/class/input`, `/sys/class/hidraw`, `/sys/class/drm`) | Yes (world-readable) | No |
| `/proc/<pid>/cmdline`, `cgroup` of any process | Yes | No |
| `/proc/<pid>/exe`, `environ`, `root/` of emulators | Yes. Emulators run as `deck`, so same-uid ptrace-read access applies. | No |
| Install udev rules, edit `/etc`, write the rootfs | n/a | Yes, and **out of scope** |

Rationale:

- Root plugins get a "This plugin has full access to your Steam Deck" warning
  in the store (wiki *Root Access*). That costs user trust for no gain.
- Every file we write lives in the user's home. As `deck`, the atomic-write
  rule in [09](09-storage-safety-sync.md) ("keep mode and owner") holds
  without `chown` gymnastics.
- Gamepad input is readable as `deck` (§7). If S3/S8 find a device that
  can't be read, the answer is a narrow helper for that device, not a root
  backend.

If root ever becomes necessary: write as root only to root-owned paths. For
anything under `/home/deck`, `os.open(..., O_NOFOLLOW)` and create the temp
file, then `fchown` it to `DECKY_USER`'s uid/gid before `rename`. Create
directories as the user (Decky's `mkdir_as_user` is the model). Never follow
symlinks in user-writable directories.

## 6. Install layout: how the hook and CLI get `mh-core`

The plugin directory is **deleted and re-extracted on every store update**
(`rmtree(plugin_dir)` in `uninstall_plugin`), and removed on uninstall. Launch
hooks must therefore never point into `~/homebrew/plugins/map-helper/`.

```
~/.local/lib/map-helper/
├── versions/
│   ├── 0.4.0/            mh_entry.py, maphelper/, maphelper/data/
│   └── 0.4.1/
├── current -> versions/0.4.1      (atomic symlink swap: symlink to tmp name, rename over)
└── install.json          { version, installed_by: "decky"|"cli", ts, sha256 of tree }
~/.local/bin/
├── mh-run                POSIX sh shim, 0755, owned by deck
└── map-helper            POSIX sh shim, 0755
```

- **One installer.** `python3 -I <payload>/mh_entry.py self-install --from <payload>`
  copies the tree to `versions/<ver>.tmp`, verifies it, renames it into place,
  swaps `current`, writes the shims, and keeps the last two versions. Decky's
  `_main` runs it (payload = `DECKY_PLUGIN_DIR/py_modules`) when
  `VERSION` differs from `install.json`. The standalone CLI tarball runs the
  same command.
- **`mh-run` fails open.** The shim does the prepare step under a timeout,
  then the *shell* execs the original command, so no Python failure can stop
  the launch:

  ```sh
  #!/bin/sh
  # map-helper launch shim (managed file). Never blocks a launch.
  MH="$HOME/.local/lib/map-helper/current/mh_entry.py"
  if [ -x /usr/bin/python3 ] && [ -f "$MH" ]; then
      timeout 10 /usr/bin/python3 -I "$MH" prepare "$@" \
          >>"$HOME/.local/state/map-helper/logs/mh-run.log" 2>&1 || true
  fi
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done
  [ "$1" = "--" ] && shift
  exec "$@"
  ```

  This keeps PID semantics for Steam (the emulator replaces the shell) and
  satisfies "never block a launch" from [02](02-architecture.md). The timeout
  value goes on the S5/S6 checklist. `timeout` is coreutils, which is in the
  base image.
- **Removing the Decky plugin leaves the hook and CLI working.** Because
  `_uninstall` can't tell an update from an uninstall (§2), real uninstall is
  explicit: Settings → Uninstall, or `map-helper uninstall`. That restores
  configs, removes hooks, removes `~/.local/lib/map-helper` and the shims, and
  optionally `$DATA`. The plugin README and store description must say so.
- **CLI-only install** (no Decky): a release asset
  `map-helper-<ver>.tar.gz` containing the same payload plus `install.sh`
  (`exec /usr/bin/python3 -I ./mh_entry.py self-install --from .`). No root,
  no pip, nothing on the rootfs. `~/.local/bin` may not be on `PATH` in
  Konsole **[VERIFY]**. The installer prints the absolute path, and hooks
  always use absolute paths.

This replaces the two separate `$INSTALL` locations in
[09](09-storage-safety-sync.md) with one: `~/.local/lib/map-helper/current`.

## 7. Device permissions

| Node | Default owner/mode | Access for `deck` | Source |
|------|-------------------|-------------------|--------|
| `/dev/input/event*` | `root:input 0660` | **Gamepads only**, via ACL: `SUBSYSTEM=="input", ENV{ID_INPUT_JOYSTICK}=="?*", TAG+="uaccess"`. Keyboards and mice are not readable. | systemd `50-udev-default.rules.in`, `70-uaccess.rules.in:73` |
| `/dev/input/event*` from Valve (VID `28de`, incl. Steam's virtual pads) | `0660` + `uaccess` | Yes | `60-steam-input.rules:14` |
| `/dev/hidraw*` | `root 0600` | Only devices tagged by Valve's rules: Valve, DS3, DS4 (USB, dongle, BT), DualSense, DualSense Edge, Switch Pro/Joy-Cons, 8BitDo (`2dc8`, USB+BT), some Xbox (e.g. Elite 2 BT) and others; 101 hidraw rules | `ValveSoftware/steam-devices` `60-steam-input.rules` |
| `/dev/uinput` | `uaccess` | Yes (not needed by us) | same |

- `uaccess` grants an ACL to the user with the **active seat session**. In
  Game Mode that's `deck`. ACLs are per-uid, so they work even without
  supplementary groups. **[VERIFY]** `getfacl /dev/input/eventN` and
  `getfacl /dev/hidrawN` for each test pad, and check that SteamOS installs
  Valve's rules (`ls /usr/lib/udev/rules.d | grep -i steam`).
- `deck` is probably not in the `input` group. **[VERIFY]** `id deck`. Don't
  rely on it.
- Whether Steam holds `EVIOCGRAB` on a pad (which would starve our reader)
  is spike S3. A root backend can open the node too, but it can't read
  events from a device another fd has grabbed either. **Root doesn't fix a
  grab**, which is one more reason not to use it.
- Reading needs only `os.open(O_RDONLY|O_NONBLOCK)`, `fcntl.ioctl`
  (`EVIOCGNAME`, `EVIOCGID`, `EVIOCGBIT`, `EVIOCGABS`) and
  `struct.unpack("llHHi")` (24 bytes on x86_64), all stdlib.

## 8. Detecting running emulators (S11)

The safety check in [09](09-storage-safety-sync.md) step 3. EmuDeck launches
Flatpaks with `flatpak run <app-id>` and AppImages directly
([07](07-launch-integration.md)).

**Flatpak** (from `flatpak/flatpak` source):

1. **cgroup (preferred).** Flatpak puts each instance in a systemd scope named
   `app-flatpak-<escaped app-id>-<instance>.scope` (`common/flatpak-run.c`).
   Scan `/proc/*/cgroup` for `app-flatpak-org.DolphinEmu.dolphin\x2demu-`.
   It's world-readable and needs no ptrace access. **[VERIFY]** the exact
   escaping of `-` in app IDs on device (systemd escapes `-` as `\x2d`).
2. **Instance dirs.** `$XDG_RUNTIME_DIR/.flatpak/<instance>/info` is a keyfile
   (`[Application] name=<app-id>`, the same content as `/.flatpak-info` inside
   the sandbox), and `bwrapinfo.json` holds `child-pid` (`common/flatpak-instance.c`,
   `flatpak_instance_get_info`, `get_child_pid`). An instance is live if
   `child-pid` exists in `/proc`. This is what `flatpak ps` reads.
3. **`/proc/<pid>/root/.flatpak-info`** is readable for same-uid processes.
   It gives the app ID of any sandboxed pid.
4. **Don't match on `/proc/<pid>/exe` alone.** Inside the sandbox the binary
   is `/app/bin/<name>`, and from the host the link shows a path that isn't
   reachable from our mount namespace **[VERIFY]** what `readlink` prints.
   `/proc/<pid>/comm` (15-char basename) is a weak hint only.

**AppImage** (type 2 runtime, `AppImage/type2-runtime` `src/runtime/runtime.c`):

- The runtime FUSE-mounts the image at `$TMPDIR/.mount_<first 6 chars of
  the file name><6 random chars>` (`build_mount_point`; `$TMPDIR` defaults to
  `/tmp`), and sets `APPIMAGE` (absolute path of the `.AppImage`, symlinks
  resolved), `APPDIR` (the mount point), `ARGV0` and `OWD` (runtime `setenv`
  calls; AppImage docs, *Environment variables*).
- Detection: `readlink /proc/<pid>/exe` starts with `/tmp/.mount_`, **and**
  `APPIMAGE` in `/proc/<pid>/environ` (same uid) matches the AppImage path the
  path provider resolved, e.g. `~/Applications/pcsx2-Qt.AppImage`.
  Fallback: `/proc/<pid>/cmdline` argv[0] equals the AppImage path. That's
  the runtime process itself, before the mount.
- With `--appimage-extract-and-run`, the mount path differs
  (`/tmp/appimage_extracted_*`). That's rare in EmuDeck. Match on `APPIMAGE`
  first.

**Native / other:** match `/proc/<pid>/exe` against the path provider's
binary path.

Reading `environ`, `exe` and `root` of another process needs
`PTRACE_MODE_READ` (same uid, not undumpable). That's true for EmuDeck
emulators running as `deck`. Root would only matter for other users'
processes, which we don't care about.

## 9. Store submission, review and releases

Process (database README, wiki *Submitting Plugins*, *Review and Testing*, PR
templates at `b36d85d`):

1. Public GitHub repo with `LICENSE` at the root. Based on the template?
   Then put our license **on top** and keep the template's BSD-3-Clause text
   below it, or the store won't distribute the plugin.
2. Fork `SteamDeckHomebrew/decky-plugin-database`, add a **git submodule**
   `plugins/map-helper` pinned to a commit (ours: on `decky-release`), and
   open a PR using the *Plugin addition* template. The checklist asks you to
   confirm authorship, honoured library licences, uniqueness vs existing
   plugins, backend type (Python only, no non-static binaries), and
   community testing (optional: test two other PRs).
3. Review: a submodule sanity check; npm deps and `remote_binary` usage;
   `lockfileVersion: 9.0`; a code read for remote code, external URLs and
   malicious or unintended behaviour; required configs in `defaults/`;
   unused `backend/`, `assets/`, `defaults/` removed.
4. PR builds go to the **testing store** (`testing.deckbrew.xyz`) with
   `-<sha7>` appended to the version (`build-plugins.yml`, "Append hash to
   plugin version").
5. A **third party must test** it. Python-backend + React plugins: latest
   **Stable or Beta** SteamOS. Custom backends or non-static binaries:
   **Preview**. We spawn the OS's own `/usr/bin/python3`, not a shipped
   binary, so we should fall under the Python category. **[VERIFY]** with
   reviewers at submission time, since it's an unusual pattern.
6. A Loader team member approves. On merge, the store CI builds with the
   Decky CLI (Docker), zips, and uploads `name`, `author`,
   `publish.description`/`tags`/`image` and the `package.json` version. PRs
   without testing progress are closed after about 2–3 weeks.
7. **Updates:** the same flow with the *Plugin update* template, bumping the
   submodule commit **and** `package.json` `version`.

Store policies that affect us:

- **No LLM-generated code.** The wiki says: "We do not accept any plugin that
  uses any LLM based code". The PR template has a checkbox: "Generative AI
  was NOT used to write a majority of the code I am submitting." The
  maintainer must be able to tick it truthfully. If not, distribute outside
  the store (GitHub Release zip, installed through Decky's "Manual plugin
  install" by URL) and say so in the README.
- Monetization: the core features have to be free (we have no paid features).
- PR templates warn that not using a template "may result in your PR being
  denied". Use them exactly.

How updates reach users: on each check, Decky fetches the store's version
list and offers an update when `compare(remote, installed, '>')` holds, with
both versions valid semver (`store.tsx` `checkForPluginUpdates`, using
`compare-versions`). The user taps Update, and the loader reinstalls (see the
§2 caveat about `_uninstall`).

### Versioning and release process

- **One version** for plugin and core: `package.json` `version` =
  `maphelper/VERSION` = git tag `vX.Y.Z` (no `v` in `package.json`). Plain
  `X.Y.Z` only. Store CI already appends `-<sha>` for test builds and `-N` for
  forced re-uploads, and `compare-versions` sorts those below the bare
  version.
- Rule file schema and data versions are independent (`schemaVersion` in
  files, migrations in core). A plugin update never needs a data rewrite to
  start.
- Release steps:
  1. CI on `main`: tests on Python 3.11/3.13/3.14, golden files, frontend
     typecheck/build.
  2. Tag `vX.Y.Z`. The release workflow renders `decky-release` (copies
     `core/maphelper` into `py_modules/`, writes `VERSION`, sets
     `package.json` version) and commits it.
  3. Build artifacts locally with the same Decky CLI version as the store
     (`0.0.7` in `build-plugins.yml`): `map-helper.zip` (manual install) and
     `map-helper-X.Y.Z.tar.gz` (CLI-only). Attach both to a GitHub Release
     with checksums.
  4. PR to `decky-plugin-database` bumping the submodule to that
     `decky-release` commit.

### Update strategy

- **Store update:** loader stops the plugin (`_unload`, `_uninstall`), deletes
  and re-extracts the plugin dir, then starts it. `_main` runs
  `self-install`, which atomically swaps `current`. Hooks keep using the old
  version until the swap, so no launch ever sees a half-installed tree.
- **After any update:** `_main` re-runs `hooks status` and queues a toast if
  hooks need repair (EmuDeck rewrites launchers; see [07](07-launch-integration.md)).
- **Rollback:** `map-helper self rollback` points `current` back at the
  previous version (we keep two).
- **CLI-only users:** re-run the new tarball's `install.sh`. There's no
  auto-update and no network access in core (that also keeps store review
  simple).

## 10. Security considerations

- **RPC surface.** Any code in Steam's CEF context that can talk to Decky's
  local WebSocket can call our backend methods. Treat arguments as untrusted:
  accept only IDs (rule id, emulator id, device id) and resolve paths
  ourselves inside known roots. No arbitrary path writes, no
  `shell=True`, no `eval`. Import/export accepts only paths from the Decky
  file picker, parsed as JSON and validated against the schema.
- **No root.** See §5. If that ever changes: `O_NOFOLLOW`, `fchown` to the
  user before `rename`, never `chown -R` a user-controlled tree, and a
  reviewed list of privileged operations.
- **Hook integrity.** `mh-run`, `~/.local/bin/*` and
  `~/.local/lib/map-helper/` are owned by `deck`, `0755`/`0644`, and never
  group- or world-writable. `self-install` refuses to write through symlinks
  it didn't create. `install.json` records a tree hash, and `doctor` reports
  mismatches.
- **Input privacy.** Capture opens **only the selected joystick-class device**
  (keyboards aren't readable as `deck` anyway, §7). It runs only while the
  capture UI is open, stops after 60 s of inactivity and when the route
  unmounts or the plugin unloads. Raw events are never logged or persisted:
  only the final binding is saved. `doctor` bundles contain no event data and
  redact MACs and serials ([09](09-storage-safety-sync.md#privacy)).
- **Process hygiene.** The worker gets a minimal environment and
  `/usr/bin/python3 -I`. It's killed in `_unload`. Every subprocess has a
  timeout.
- **No network.** Core and backend make no network calls. Community packs
  are local files. This also avoids the store's remote-code scrutiny.

## Open items for spikes

- S3: grab behaviour and ACLs per pad (§7 **[VERIFY]**s).
- S4: B/back consumption in a route ([08](08-ui-ux.md)).
- S11: Flatpak cgroup escaping and the `exe` readlink output (§8).
- S12: backend `Groups:` and environment. Confirm system Python is present on
  non-Deck SteamOS hardware.
- New: confirm `_uninstall` runs on store update, on a test plugin.

## Sources

Repos cloned read-only (`git clone --depth 1`) on 2026-10-22:

- Plugin template, `SteamDeckHomebrew/decky-plugin-template` @ `90d0780e882a17f5714fc6de044c645f22608290`: [`plugin.json`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/plugin.json), [`package.json`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/package.json), [`main.py`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/main.py), [`decky.pyi`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/decky.pyi), [`src/index.tsx`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/src/index.tsx), [`README.md`](https://github.com/SteamDeckHomebrew/decky-plugin-template/blob/90d0780e882a17f5714fc6de044c645f22608290/README.md) (Backend support, Distribution, licence note), `defaults/defaults.txt`
- Decky Loader, `SteamDeckHomebrew/decky-loader` @ `00cd202872b85868071b041c8f1b34e734147195` (v3.3.0, 2026-10-18):
  - [`backend/decky_loader/plugin/sandboxed_plugin.py`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/decky_loader/plugin/sandboxed_plugin.py): setuid/setgid, env vars, `py_modules`, lifecycle, method dispatch
  - [`backend/decky_loader/plugin/plugin.py`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/decky_loader/plugin/plugin.py): plugin.json fields, `stop(uninstall)`, 5 s SIGKILL
  - [`backend/decky_loader/browser.py`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/decky_loader/browser.py): `_install` uninstalls first, `uninstall_plugin` rmtree, root flag chown
  - [`backend/decky_loader/loader.py`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/decky_loader/loader.py): `debug` flag, `loader/call_plugin_method`
  - [`backend/decky_loader/localplatform/localplatformlinux.py`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/decky_loader/localplatform/localplatformlinux.py) (`setuid`, `setgid`, `run` env), [`localsocket.py`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/decky_loader/localplatform/localsocket.py)
  - [`backend/pyinstaller.spec`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/pyinstaller.spec), [`backend/pyproject.toml`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/backend/pyproject.toml), [`.github/workflows/build.yml`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/.github/workflows/build.yml) (Python 3.14.8); history: commits [`636b86cf`](https://github.com/SteamDeckHomebrew/decky-loader/commit/636b86cf) (3.11.7 → 3.14.8), [`e266258f`](https://github.com/SteamDeckHomebrew/decky-loader/commit/e266258f) (3.10.6 → 3.11.7)
  - [`dist/plugin_loader-release.service`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/dist/plugin_loader-release.service) (`User=root`)
  - [`frontend/src/plugin-loader.tsx`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/frontend/src/plugin-loader.tsx), [`router-hook.tsx`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/frontend/src/router-hook.tsx), [`store.tsx`](https://github.com/SteamDeckHomebrew/decky-loader/blob/00cd202872b85868071b041c8f1b34e734147195/frontend/src/store.tsx) (`checkForPluginUpdates`)
  - Releases: [v3.3.0](https://github.com/SteamDeckHomebrew/decky-loader/releases/tag/v3.3.0)
  - Issues: [#968 plugin backends lost `http.server` in v3.2.9](https://github.com/SteamDeckHomebrew/decky-loader/issues/968), [#975 backends SIGKILLed on stop](https://github.com/SteamDeckHomebrew/decky-loader/issues/975), [#30 external dependencies](https://github.com/SteamDeckHomebrew/decky-loader/issues/30)
- `@decky/api`, `SteamDeckHomebrew/loader-api` @ `d1b7f16070777a0ada939cbacd3606eeba0574f5` (1.1.3): [`src/index.ts`](https://github.com/SteamDeckHomebrew/loader-api/blob/d1b7f16070777a0ada939cbacd3606eeba0574f5/src/index.ts), [`src/types.ts`](https://github.com/SteamDeckHomebrew/loader-api/blob/d1b7f16070777a0ada939cbacd3606eeba0574f5/src/types.ts) (`ToastData`, `Plugin`)
- `@decky/ui`, `SteamDeckHomebrew/decky-frontend-lib` @ `10b929d2e92af179569fa1bb8f456cc5f57f28d5` (4.16.0): [`src/components/FooterLegend.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/components/FooterLegend.ts), [`src/components/Focusable.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/components/Focusable.ts), [`src/globals/steam-client/Input.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/globals/steam-client/Input.ts), [`GameSessions.ts`](https://github.com/SteamDeckHomebrew/decky-frontend-lib/blob/10b929d2e92af179569fa1bb8f456cc5f57f28d5/src/globals/steam-client/GameSessions.ts)
- Decky CLI, `SteamDeckHomebrew/cli` @ `6c32da7396942a2362f63a02bfa6c68242f0ab07`: [`src/cli/plugin/build.rs`](https://github.com/SteamDeckHomebrew/cli/blob/6c32da7396942a2362f63a02bfa6c68242f0ab07/src/cli/plugin/build.rs) (`copy_py_modules`, `zip_plugin`)
- Plugin database, `SteamDeckHomebrew/decky-plugin-database` @ `b36d85de49282ad0c7871250a732906f58b17ba6`: [`README.md`](https://github.com/SteamDeckHomebrew/decky-plugin-database/blob/b36d85de49282ad0c7871250a732906f58b17ba6/README.md), [`.github/PULL_REQUEST_TEMPLATE/plugin_addition.md`](https://github.com/SteamDeckHomebrew/decky-plugin-database/blob/b36d85de49282ad0c7871250a732906f58b17ba6/.github/PULL_REQUEST_TEMPLATE/plugin_addition.md), `plugin_update.md`, [`.github/workflows/build-plugins.yml`](https://github.com/SteamDeckHomebrew/decky-plugin-database/blob/b36d85de49282ad0c7871250a732906f58b17ba6/.github/workflows/build-plugins.yml)
- Decky wiki source, `SteamDeckHomebrew/wiki` @ `ec9d4cf8b07cdc7bc7706fd118d68a272f653cb4`: [`plugin-dev/submitting-plugins.md`](https://github.com/SteamDeckHomebrew/wiki/blob/ec9d4cf8b07cdc7bc7706fd118d68a272f653cb4/plugin-dev/submitting-plugins.md) (licence, LLM policy, no black boxes), [`plugin-dev/review-and-testing.md`](https://github.com/SteamDeckHomebrew/wiki/blob/ec9d4cf8b07cdc7bc7706fd118d68a272f653cb4/plugin-dev/review-and-testing.md), [`plugin-dev/env-vars.md`](https://github.com/SteamDeckHomebrew/wiki/blob/ec9d4cf8b07cdc7bc7706fd118d68a272f653cb4/plugin-dev/env-vars.md), [`plugin-dev/backend-frontend-communication.md`](https://github.com/SteamDeckHomebrew/wiki/blob/ec9d4cf8b07cdc7bc7706fd118d68a272f653cb4/plugin-dev/backend-frontend-communication.md), [`user-guide/root.md`](https://github.com/SteamDeckHomebrew/wiki/blob/ec9d4cf8b07cdc7bc7706fd118d68a272f653cb4/user-guide/root.md). Rendered at https://wiki.deckbrew.xyz/en/plugin-dev/submitting-plugins.
- Comparable store plugins (plugin.json flags / backend shape): [Controller Tools `main.py`](https://github.com/jfernandez/ControllerTools/blob/main/main.py) (non-root, subprocess backend), [SimpleDeckyTDP `plugin.json`](https://github.com/aarron-lee/SimpleDeckyTDP/blob/main/plugin.json) (root), [EmuDecky `plugin.json`](https://github.com/EmuDeck/EmuDecky/blob/main/plugin.json) (`_root`), [CSS Loader](https://github.com/DeckThemes/SDH-CssLoader/blob/main/plugin.json), [MicroSDeck](https://github.com/CEbbinghaus/MicroSDeck/blob/master/plugin.json), [Decky Recorder](https://github.com/safijari/decky-recorder-fork/blob/main/plugin.json), [steamdeck-input-disabler](https://github.com/BurritoSpray/steamdeck-input-disabler/blob/main/plugin.json) (root)
- SteamOS packages: Valve mirror https://steamdeck-packages.steamos.cloud/archlinux-mirror/ (`core-3.5`…`core-3.9/os/x86_64/` for `python-*.pkg.tar.zst`; `jupiter-3.8/os/x86_64/jupiter-3.8.db` → `jupiter-hw-support-3.8.20260807.1-1/desc` `%DEPENDS%`; `extra-3.8` for `python-evdev`, `python-hid`, `python-pyudev`)
- SteamOS release channel: [SteamOS 3.8.28 (Stable), 2026-09-24](https://store.steampowered.com/news/app/1675200/view/711161056325534552); SteamOS 3.9.4 Beta announcement (Steam Deck news, 2026-10)
- udev: [`ValveSoftware/steam-devices` `60-steam-input.rules` @ `22ec85e5`](https://github.com/ValveSoftware/steam-devices/blob/22ec85e5ff5ea2e15c56d71a41bcbef46356cd60/60-steam-input.rules); systemd @ `c1332f7c`: [`rules.d/70-uaccess.rules.in`](https://github.com/systemd/systemd/blob/c1332f7caa11f49a909e4c3322fb743e58003692/rules.d/70-uaccess.rules.in) (line 73, joysticks), [`rules.d/50-udev-default.rules.in`](https://github.com/systemd/systemd/blob/c1332f7caa11f49a909e4c3322fb743e58003692/rules.d/50-udev-default.rules.in) (`GROUP="input"`)
- PyInstaller: [Run-time information § LD_LIBRARY_PATH / LIBPATH considerations](https://pyinstaller.org/en/stable/runtime-information.html#ld-library-path-libpath-considerations)
- Flatpak @ `0a8083f1`: [`common/flatpak-run.c`](https://github.com/flatpak/flatpak/blob/0a8083f10691cf5b196a8efc3f76d10a19461fc9/common/flatpak-run.c) (scope name `app-flatpak-%s-%s.scope`, `/.flatpak-info`, `bwrapinfo.json`), [`common/flatpak-instance.c`](https://github.com/flatpak/flatpak/blob/0a8083f10691cf5b196a8efc3f76d10a19461fc9/common/flatpak-instance.c) (`info`, `child-pid`, `$XDG_RUNTIME_DIR/.flatpak`); [`flatpak ps` reference](https://docs.flatpak.org/en/latest/flatpak-command-reference.html)
- AppImage: [`AppImage/type2-runtime` `src/runtime/runtime.c` @ `fedfad51`](https://github.com/AppImage/type2-runtime/blob/fedfad51acc2860b2916a1eef32ba4a500ff31ef/src/runtime/runtime.c) (`build_mount_point`, `setenv("APPIMAGE"…)`); [AppImage docs § Environment variables](https://docs.appimage.org/packaging-guide/environment-variables.html)
- Linux: [proc_pid_environ(5)](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html), [proc_pid_exe(5)](https://man7.org/linux/man-pages/man5/proc_pid_exe.5.html) (ptrace access mode checks)
