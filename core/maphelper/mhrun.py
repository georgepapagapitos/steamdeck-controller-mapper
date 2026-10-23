"""mh-run: apply the mappings for the pads connected now, right before an emulator starts. See docs/07 "mh-run
behaviour" and ADR-001.

    mh-run --emulator <id> [--system S] [--core C] [--game G] -- <command...>    wrap: apply, then exec the command
    mh-run --hook --emulator <id> --rom <path> [--system S] [--core C]          hook: apply, exit 0
    mh-run --hook --es-de <rom> <game name> <system> <full system name>        ES-DE's game-start event

It fails open, always: whatever goes wrong (an exception, a missing config, a bad rule, a held lock, a slow probe) is
logged to $STATE/logs/launch.log and the command still runs unchanged. Nothing is printed: in wrap mode the emulator
inherits stdout and stderr.

Time budget (BUDGET_MS from the start of main): a SIGALRM watchdog interrupts whatever is running when it runs out,
and the deadline is checked again between steps. The writer stages every changed file complete before renaming any
(writer.apply_patches' gate), and the gate is the last place the budget can stop us: past it nothing is written,
before it only temp files exist (and are removed). After the gate the watchdog is off and only the renames are left,
so a cut-off never leaves a half-written file or a half-applied set.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import signal
import threading
import time
from pathlib import Path
from typing import Callable, Optional

HOME = Path.home()
STATE = HOME / ".local" / "state" / "map-helper"
USER_RULES = HOME / ".local" / "share" / "map-helper" / "rules"    # $DATA/rules (docs/09)
BUDGET_MS = 500
LOG_MAX = 256 * 1024          # launch.log rolls over to launch.log.1 past this


class BudgetExceeded(Exception):
    pass


class Skip(Exception):
    """Nothing to apply (not an error): no config yet, an unknown core, the lock is held..."""


class Budget:
    def __init__(self, start: float, ms: int, clock: Callable[[], float]):
        self.deadline, self.clock = start + ms / 1000, clock
        self._old = None

    def check(self, step: str) -> None:
        if self.clock() >= self.deadline:
            raise BudgetExceeded(f"over {BUDGET_MS} ms budget at {step}")

    def arm(self) -> None:
        if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
            return                                          # Windows (dev only): the deadline checks still apply

        def fire(signum, frame):
            raise BudgetExceeded("watchdog: over the time budget" if signum == signal.SIGALRM
                                 else "stopped by the shim's timeout backstop")
        self._old = signal.signal(signal.SIGALRM, fire)
        signal.signal(signal.SIGTERM, fire)         # the shim's backstop: before the gate it aborts like the watchdog
        signal.setitimer(signal.ITIMER_REAL, max(self.deadline - self.clock(), 0.001))

    def disarm(self) -> None:
        if self._old is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._old)
            self._old = None

    def gate(self) -> bool:
        """The writer's gate: watchdog off, then one last look at the clock. True: commit."""
        self.disarm()
        go = self.clock() < self.deadline
        if go and threading.current_thread() is threading.main_thread():
            # Past the gate only renames are left; let them finish rather than leave the set half applied. The shim's
            # SIGKILL comes later (timeout -k) and only for a real hang.
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        return go


class _Parser(argparse.ArgumentParser):
    def error(self, message):                               # never print usage into the emulator's stderr
        raise ValueError(f"bad arguments: {message}")


def _parser():
    from .cli import add_probe_arguments
    from .pipeline import EMULATORS
    p = _Parser(prog="mh-run", add_help=False)
    p.add_argument("--emulator", choices=sorted(EMULATORS))
    p.add_argument("--system")
    p.add_argument("--core")
    p.add_argument("--game")
    p.add_argument("--rom")
    p.add_argument("--hook", action="store_true")
    p.add_argument("--no-exec", action="store_true", help="the shim execs the command itself")
    p.add_argument("--config-root", type=Path)
    p.add_argument("--rules", type=Path, action="append")
    p.add_argument("--state-dir", type=Path, default=STATE)
    p.add_argument("--es-de-root", type=Path)
    add_probe_arguments(p)
    return p


def split(argv: list[str]) -> tuple[list[str], list[str], Optional[list[str]]]:
    """(our options, the command after --, ES-DE's four args after --es-de)."""
    if "--" in argv:
        i = argv.index("--")
        own, command = argv[:i], argv[i + 1:]
    else:
        own, command = list(argv), []
    esde = None
    if "--es-de" in own:
        i = own.index("--es-de")
        own, esde = own[:i], own[i + 1:]
    return own, command, esde


def main(argv: list[str], exec_fn: Callable = os.execvp, clock: Callable[[], float] = time.monotonic,
         budget_ms: int = BUDGET_MS) -> int:
    start = clock()
    own, command, esde = split(list(argv))
    hook = "--hook" in own or esde is not None
    entry = {"mode": "es-de" if esde is not None else "hook" if hook else "wrap"}
    # Found before parsing, so even bad arguments get logged where the caller asked.
    state_dir = Path(own[own.index("--state-dir") + 1]) if "--state-dir" in own[:-1] else STATE
    budget = Budget(start, budget_ms, clock)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            args = _parser().parse_args(own)
            state_dir = args.state_dir
            budget.arm()
            prepare(args, command, esde, budget, entry)
    except Skip as e:
        entry["skipped"] = str(e)
    except BaseException as e:                              # fail open: KeyboardInterrupt and SystemExit included
        entry["error"] = f"{type(e).__name__}: {e}"
    finally:
        budget.disarm()
    entry["ms"] = round((clock() - start) * 1000)
    try:
        write_log(state_dir, entry)
    except BaseException:
        pass
    if hook or "--no-exec" in own or not command:
        return 0
    try:
        exec_fn(command[0], command)                        # unchanged; replaces this process when it's os.execvp
    except OSError as e:
        with contextlib.suppress(BaseException):
            write_log(state_dir, {"mode": "exec", "error": f"{command[0]}: {e}"})
        return 127
    return 0


def prepare(args, command: list[str], esde: Optional[list[str]], budget: Budget, entry: dict) -> None:
    from . import pipeline
    from .launch import PARSERS, LaunchInfo, dolphin_disc, retroarch_game_id

    if esde is not None:
        from . import esde as frontend
        rom, _name, system = (esde + ["", "", ""])[:3]
        found = frontend.launch(rom, system, args.es_de_root or frontend.ROOT)
        if found is None:
            raise Skip(f"es-de system {system!r}: no command map-helper knows")
        entry.update(emulator=found.emulator, label=found.label)
        if found.emulator is None:
            raise Skip(f"es-de runs {found.label!r} for {system}, not an emulator map-helper manages")
        emulator = found.emulator
        info = LaunchInfo(rom=found.rom, core_file=found.core_file, system=found.system)
        if emulator == "dolphin":
            disc, info.game = dolphin_disc(found.rom)
            info.system = disc or info.system
        elif emulator == "retroarch":
            info.game = retroarch_game_id(str(found.rom))
    else:
        if not args.emulator:
            raise ValueError("no --emulator")
        emulator = args.emulator
        entry["emulator"] = emulator
        info = PARSERS[emulator](command) if command else LaunchInfo()
        if args.rom:
            info = PARSERS[emulator]([emulator, args.rom]) if emulator != "dolphin" else \
                PARSERS[emulator]([emulator, "-e", args.rom])
    budget.check("parsing the launch")

    adapter = pipeline.EMULATORS[emulator].adapter()
    system = args.system or info.system
    core = args.core
    if emulator == "retroarch":
        core = core or _core_id(adapter, info.core_file)
        if core is None:
            raise Skip(f"no core descriptor for {info.core_file or 'an unknown core'}")
        systems = adapter.core_for("", core)["systems"]
        if system not in systems:
            if len(systems) != 1:
                raise Skip(f"can't tell which of {', '.join(systems)} {core} runs here; pass --system")
            system = systems[0]
    if not system:
        raise Skip("can't tell the system from the command; pass --system")
    entry.update(system=system, core=core, game=args.game or info.game)

    root = args.config_root or pipeline.EMULATORS[emulator].config_root
    if not root.is_dir():
        raise Skip(f"no config at {root} (has the emulator run once?)")
    with lock(Path(args.state_dir) / "locks" / f"{emulator}.lock"):
        budget.check("taking the lock")
        req = pipeline.Request(emulator, system, root, args.rules or [USER_RULES], core=core,
                               game=args.game or info.game, probe_args=args, write=True, state_dir=args.state_dir)
        outcome = pipeline.run(req, log=lambda line: None, gate=budget.gate, adapter=adapter)
    if outcome.result.aborted:
        raise BudgetExceeded("over the time budget before writing; nothing written")
    entry.update(players=outcome.players, changed=outcome.result.changed_files)


def _core_id(adapter, core_file: Optional[str]) -> Optional[str]:
    for cid, desc in adapter.cores.items():
        if core_file in desc["core_files"]:
            return cid
    return None


@contextlib.contextmanager
def lock(path: Path):
    """The advisory lock from docs/02 "Process model". A held lock means another launch is applying: skip."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:                                 # Windows (dev only)
            import msvcrt
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Skip("another launch holds the lock") from None
        except OSError:
            raise Skip("another launch holds the lock") from None
        yield
    finally:
        os.close(fd)


def write_log(state_dir: Path, entry: dict) -> None:
    """One line per launch in $STATE/logs/launch.log; past LOG_MAX it moves to launch.log.1 (one kept)."""
    log = Path(state_dir) / "logs" / "launch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.is_file() and log.stat().st_size > LOG_MAX:
        os.replace(log, log.with_name("launch.log.1"))
    fields = [time.strftime("%Y-%m-%dT%H:%M:%S"), entry.get("mode", "?")]
    for key in ("emulator", "system", "core", "game", "label", "players"):
        if entry.get(key) not in (None, ""):
            fields.append(f"{key}={entry[key]}")
    if "error" in entry:
        outcome = f"error: {entry['error']}"
    elif "skipped" in entry:
        outcome = f"skipped: {entry['skipped']}"
    elif "changed" in entry:
        outcome = f"changed: {', '.join(entry['changed'])}" if entry["changed"] else "no changes"
    else:
        outcome = ""
    if "ms" in entry:
        fields.append(f"ms={entry['ms']}")
    line = " ".join(fields) + (f" {outcome}" if outcome else "")
    with open(log, "a", encoding="utf-8") as f:
        f.write(line.replace("\n", " ") + "\n")
