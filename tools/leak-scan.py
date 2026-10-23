#!/usr/bin/env python3
"""Runs on the Deck: does the patch text on stdin contain one of this Deck's real device ids? `tools/deck.sh
leak-check` pipes in what a push would publish (`git log -p`) before anything goes to the public repo.

It compares against: evdev `uniq` values (/proc/bus/input/devices: Bluetooth MACs, USB serials), USB serials in
sysfs, Steam's virtual pad handles (virtualgamepadinfo.txt), paired Bluetooth devices (`bluetoothctl devices`, so
a pad that isn't connected now still counts) and network interface MACs. Each is matched case-insensitively with
and without separators; handles also as decimal. It prints only counts and file names, never a value.
"""

import re
import subprocess
import sys
from pathlib import Path

MAC = r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}"


def secrets() -> dict:
    """value -> where it came from (a category, not the value)."""
    found = {}
    proc = Path("/proc/bus/input/devices").read_text(encoding="utf-8", errors="replace")
    for value in re.findall(r"^U: Uniq=(.+)$", proc, re.M):
        found[value.strip()] = "evdev uniq"
    for serial in Path("/sys/bus/usb/devices").glob("*/serial"):
        try:
            found[serial.read_text(encoding="utf-8", errors="replace").strip()] = "usb serial"
        except OSError:
            pass
    info = Path.home() / ".local/share/Steam/config/virtualgamepadinfo.txt"
    if info.is_file():
        for handle in re.findall(r"^handle=0x([0-9a-fA-F]+)$", info.read_text(encoding="utf-8"), re.M):
            found[handle] = "steam handle"
            found[str(int(handle, 16))] = "steam handle"
    try:
        paired = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True, timeout=5).stdout
        for mac in re.findall(MAC, paired):
            found[mac] = "paired bluetooth device"
    except (OSError, subprocess.SubprocessError):
        pass
    for address in Path("/sys/class/net").glob("*/address"):
        mac = address.read_text(encoding="utf-8").strip()
        if mac != "00:00:00:00:00:00":
            found[mac] = "network interface"
    return {k: v for k, v in found.items() if len(k.strip("0")) >= 6}


def forms(value: str) -> set:
    v = value.lower()
    out = {v, v.lstrip("0")}
    if re.fullmatch(MAC, value):
        bare = v.replace(":", "")
        out |= {bare, v.replace(":", "-"), v.replace(":", "_")}
    return {f for f in out if len(f) >= 6}


def main() -> int:
    patch = sys.stdin.read().lower()
    values = secrets()
    hits = {}
    current = "(commit message)"
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("commit "):
            current = "(commit message)"
        for value, kind in values.items():
            if any(f in line for f in forms(value)):
                hits.setdefault(current, set()).add(kind)
    if hits:
        print(f"LEAK: {sum(len(k) for k in hits.values())} hit(s) of this Deck's ids in what would be pushed:")
        for name, kinds in sorted(hits.items()):
            print(f"  {name}: {', '.join(sorted(kinds))}")
        return 1
    print(f"clean: none of this Deck's {len(values)} device ids is in {len(patch.splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
