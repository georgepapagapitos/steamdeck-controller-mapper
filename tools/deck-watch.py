"""Runs on the Deck (tools/deck.sh watch): a timeline of what decides player 1 at a launch, to line up with Steam's
console_log ("Seating controller N in slot M", "Controller slots reset") and mh-run's launch.log.

Records, with local times to the millisecond:
  press   a button press (EV_KEY down) on any gamepad node: a Steam virtual pad by its slot ("virtual pad 0"), a
          physical pad by name and VID:PID. Tells "Steam re-fed virtual pad 0 from the launching pad" from "SDL
          ordered the pads differently" (docs/13 S1).
  slots   every rewrite of Steam's virtualgamepadinfo.txt, as the slot -> pad name order.
  proc    an emulator, ES-DE or mh-run starting or exiting.

Never prints uniq, phys, handles or serials. Reading /dev/input/event* as deck works through the seat ACL. Stop it by
the PID in its pid file, never pkill -f (that matches the ssh session's own command line).
"""

import argparse
import os
import re
import select
import struct
import time
from pathlib import Path

EVENT = struct.Struct("llHHi")       # struct input_event on 64-bit Linux: timeval, type, code, value
EV_KEY = 1
PROCS = re.compile(r"retroarch|dolphin-emu|pcsx2|duckstation|es-de|mh_entry\.py|mh-run")
SLOTS = Path.home() / ".local/share/Steam/config/virtualgamepadinfo.txt"


def now() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) + f".{int(t % 1 * 1000):03d}"


def gamepads() -> dict:
    """event node path -> label, for every node with a joystick handler (no uniq/phys)."""
    out = {}
    for block in Path("/proc/bus/input/devices").read_text(encoding="utf-8").split("\n\n"):
        name = re.search(r'N: Name="(.*)"', block)
        ids = re.search(r"Vendor=(\w+) Product=(\w+)", block)
        handlers = re.search(r"H: Handlers=(.*)", block)
        if not (name and ids and handlers) or not re.search(r"\bjs\d+", handlers.group(1)):
            continue
        event = re.search(r"\b(event\d+)\b", handlers.group(1))
        if not event:
            continue
        virtual = re.search(r"pad (\d+)$", name.group(1)) if ids.groups() == ("28de", "11ff") else None
        label = f"virtual pad {virtual.group(1)}" if virtual else f"{name.group(1)} {ids.group(1)}:{ids.group(2)}"
        out[f"/dev/input/{event.group(1)}"] = f"{label} ({event.group(1)})"
    return out


def slot_order() -> str:
    try:
        text = SLOTS.read_text(encoding="utf-8")
    except OSError as e:
        return f"unreadable ({e.strerror})"
    names = re.findall(r"\[slot (\d+)\]|^name=(.*)$", text, re.M)
    out, slot = [], None
    for number, name in names:
        if number:
            slot = number
        elif slot is not None:
            out.append(f"{slot}={name.strip()}")
            slot = None
    return ", ".join(out)


def processes() -> dict:
    out = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        found = PROCS.search(cmd)
        if found:
            out[int(proc.name)] = found.group(0)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=1800)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pid-file", type=Path, required=True)
    args = p.parse_args()
    args.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    log = open(args.out, "a", encoding="utf-8", buffering=1)

    def say(kind, text):
        log.write(f"{now()} {kind:5} {text}\n")

    fds, labels, denied = {}, {}, {}
    slots_mtime, procs, last_scan = None, processes(), 0.0
    say("start", f"slots: {slot_order()}; running: {', '.join(sorted(set(procs.values()))) or 'none'}")
    end = time.monotonic() + args.seconds
    while time.monotonic() < end:
        if time.monotonic() - last_scan > 1:
            last_scan = time.monotonic()
            pads = gamepads()
            for path in set(fds) - set(pads):                       # node went away
                os.close(fds.pop(path))
                say("node", f"gone {labels.pop(path)}")
            for path, label in pads.items():
                if (path not in fds or labels[path] != label) and denied.get(path) != label:
                    if path in fds:
                        os.close(fds.pop(path))
                    try:
                        fds[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                        labels[path] = label
                        say("node", f"open {label}")
                    except OSError as e:
                        denied[path] = label                    # say it once (motion-sensor nodes aren't in the ACL)
                        say("node", f"can't open {label}: {e.strerror}")
            current = processes()
            for pid in current.keys() - procs.keys():
                say("proc", f"start {current[pid]} pid={pid}")
            for pid in procs.keys() - current.keys():
                say("proc", f"exit {procs[pid]} pid={pid}")
            procs = current
        try:
            mtime = SLOTS.stat().st_mtime
        except OSError:
            mtime = None
        if mtime != slots_mtime:
            if slots_mtime is not None:
                say("slots", slot_order())
            slots_mtime = mtime
        ready, _, _ = select.select(list(fds.values()), [], [], 0.05)
        for fd in ready:
            path = next(p for p, f in fds.items() if f == fd)
            try:
                data = os.read(fd, EVENT.size * 64)
            except OSError:
                continue
            for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, kind, code, value = EVENT.unpack_from(data, i)
                if kind == EV_KEY and value == 1:
                    say("press", f"{labels[path]} key {code}")
    say("stop", "time limit")


if __name__ == "__main__":
    main()
