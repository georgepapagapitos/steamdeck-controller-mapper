"""`map-helper` command line. Prototype subset of docs/08 "CLI parity"."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import resolve as resolver
from .devices import (STEAM_VIRTUAL_PAD, ControllerDB, is_gamepad, parse_ignore_devices, parse_proc_input_devices,
                      parse_virtual_gamepad_info, physical_ids, sdl_joysticks, stable_id, steam_slots, with_usb_serials,
                      POLICY_EXTERNAL_FIRST, POLICY_STEAM_ORDER, docked, parse_drm_status,
                      player_order, read_drm_status)
from .model import Target
from .store import load_json, load_layouts, load_sources
from .validate import validate_rule

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"


def main(argv: list[str] | None = None) -> int:
    from .pipeline import EMULATORS
    parser = argparse.ArgumentParser(prog="map-helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate rule files")
    p.add_argument("paths", nargs="+", type=Path)

    p = sub.add_parser("devices", help="list connected controllers")
    add_probe_arguments(p)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("explain", help="show which rule sets each binding")
    p.add_argument("--system", required=True)
    p.add_argument("--emulator")
    p.add_argument("--game")
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--model", help="controller model id from data/controllers.json")
    who.add_argument("--vid-pid", help="e.g. 054c:09cc")
    p.add_argument("--device-id", action="append", default=[], help="stable device id (repeatable)")
    p.add_argument("--name", default="", help="device name, used for style inference")
    p.add_argument("--rules", type=Path, action="append",
                   help="user rule directory (repeatable); default: examples/")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("apply", help="resolve and write an emulator's input config (dry run by default)")
    p.add_argument("--emulator", required=True, choices=sorted(EMULATORS))
    p.add_argument("--core", help="RetroArch core (descriptor id or library name); needed when several run the system")
    p.add_argument("--system", required=True)
    p.add_argument("--game")
    p.add_argument("--config-root", type=Path, required=True, help="the emulator's config directory")
    p.add_argument("--player", action="append", metavar="MODEL[@DEVICE_ID]",
                   help="controller model per player, in order (repeatable), e.g. sony.ds4.v2@mac:aa:bb:..; "
                        "default: the connected pads in Steam's order, each also set as that player's device")
    add_probe_arguments(p)
    p.add_argument("--rules", type=Path, action="append", help="user rule directory (default: examples/)")
    p.add_argument("--write", action="store_true", help="write the files (default: print the diff only)")
    p.add_argument("--state-dir", type=Path, default=Path.home() / ".local" / "state" / "map-helper",
                   help="where pristine backups go")

    p = sub.add_parser("backup", help="save the current state of every file map-helper has written")
    p.add_argument("--name", help="backup name (default: the time, e.g. 20261022-153000)")
    p.add_argument("--list", action="store_true", help="list the backups instead")
    p.add_argument("--state-dir", type=Path, default=Path.home() / ".local" / "state" / "map-helper")

    p = sub.add_parser("restore", help="put the files map-helper wrote back to pristine, or to a backup")
    p.add_argument("--emulator", choices=sorted(EMULATORS),
                   help="only this emulator's files (default: all)")
    p.add_argument("--from", dest="source", metavar="BACKUP", help="a backup name (default: pristine)")
    p.add_argument("--dry-run", action="store_true", help="list what would happen; change nothing")
    p.add_argument("--force", action="store_true", help="also restore files someone else changed since")
    p.add_argument("--state-dir", type=Path, default=Path.home() / ".local" / "state" / "map-helper")

    from . import doctor
    p = sub.add_parser("doctor", help="report settings that silently defeat map-helper's mappings (read-only)")
    p.add_argument("--steam-root", type=Path, default=doctor.STEAM_ROOT, help="Steam's install (has userdata/)")
    p.add_argument("--retroarch-root", type=Path, default=doctor.RETROARCH_ROOT, help="RetroArch's config directory")
    p.add_argument("--emudeck-settings", type=Path, default=doctor.EMUDECK_SETTINGS, help="EmuDeck's settings.sh")
    p.add_argument("--home", type=Path, default=Path.home(),
                   help="where to look for mh-run's shim, SRM's parsers and ES-DE (default: your home)")
    p.add_argument("--json", action="store_true")

    for name, text in (("setup", "put mh-run in front of launches: the shim, SRM's parsers, ES-DE's game-start "
                                 "script (dry run by default)"),
                       ("uninstall", "undo exactly what setup changed (dry run by default)")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--write", action="store_true", help="make the changes (default: list them only)")
        p.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
        p.add_argument("--state-dir", type=Path, help="where setup records what it changed "
                                                      "(default: ~/.local/state/map-helper)")
        if name == "setup":
            p.add_argument("--entry", type=Path, help="the mh_entry.py the shim runs "
                                                      "(default: ~/.local/lib/map-helper/current/mh_entry.py)")
            p.add_argument("--python", default="/usr/bin/python3", help="the Python the shim runs it with")

    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["mh-run"]:                     # the launch wrapper takes its own arguments (see mhrun.py)
        from .mhrun import main as mh_run
        return mh_run(argv[1:])
    args = parser.parse_args(argv)
    return {"validate": cmd_validate, "devices": cmd_devices, "explain": cmd_explain,
            "apply": cmd_apply, "backup": cmd_backup, "restore": cmd_restore,
            "doctor": cmd_doctor, "setup": cmd_setup, "uninstall": cmd_setup}[args.command](args)


def add_probe_arguments(p) -> None:
    p.add_argument("--proc-file", type=Path, default=Path("/proc/bus/input/devices"),
                   help="read a saved copy instead of the live file")
    p.add_argument("--sys-root", type=Path, default=Path("/sys"), help="where sysfs is (USB serials are read there)")
    # Steam sets the env var only inside a game's environment; outside one (a shell, ssh) the file is still there.
    p.add_argument("--virtual-info", type=Path,
                   default=os.environ.get("SteamVirtualGamepadInfo",
                                          Path.home() / ".local/share/Steam/config/virtualgamepadinfo.txt"),
                   help="Steam's virtual gamepad info file (default: $SteamVirtualGamepadInfo, else Steam's config dir)")
    p.add_argument("--ignore-devices", default=os.environ.get("SDL_GAMECONTROLLER_IGNORE_DEVICES", ""),
                   help="pads behind Steam Input (default: $SDL_GAMECONTROLLER_IGNORE_DEVICES)")
    p.add_argument("--policy", choices=["auto", POLICY_STEAM_ORDER, POLICY_EXTERNAL_FIRST], default="auto",
                   help="player order; auto: external-first when docked, else steam-order (docs/04 5.1)")
    p.add_argument("--drm-status", type=Path, help="saved DRM connector states (a capture's drm-status.txt) "
                                                   "instead of <sys-root>/class/drm")


class Probe:
    """What's connected: evdev devices, Steam's slots, and which physical pads are behind Steam."""

    def __init__(self, args, db: ControllerDB):
        self.devices = with_usb_serials(parse_proc_input_devices(args.proc_file.read_text(encoding="utf-8")),
                                        args.sys_root)
        self.slots = []
        if args.virtual_info and Path(args.virtual_info).is_file():
            info = parse_virtual_gamepad_info(Path(args.virtual_info).read_text(encoding="utf-8"))
            self.slots = steam_slots(self.devices, info)
        # A pad with a live Steam slot is behind Steam. Steam's ignore list can't say that: it names every pad type
        # Steam supports, connected or not (793 entries on a Deck, tests/fixtures/devices/game-steam-input-on), so
        # it's only a fallback when there's no slot file.
        live = {s.vid_pid for s in self.slots if s.virtual}
        self.behind_steam = live if self.slots else parse_ignore_devices(args.ignore_devices)
        self.pads = [d for d in self.devices if is_gamepad(d) and not db.is_virtual(d.vid_pid)]
        self.ids = physical_ids(self.slots, self.pads)   # Steam slot -> physical pad's stable id
        self.policy, self.policy_reason = self._policy(args)

    def _policy(self, args) -> tuple:
        if args.policy != "auto":
            return args.policy, "chosen with --policy"
        drm = (parse_drm_status(args.drm_status.read_text(encoding="utf-8")) if args.drm_status
               else read_drm_status(args.sys_root))
        is_docked, why = docked(drm)
        if is_docked is None:
            return POLICY_STEAM_ORDER, f"can't tell docked from handheld ({why}), so Steam's order"
        return (POLICY_EXTERNAL_FIRST, f"docked: {why}") if is_docked else (POLICY_STEAM_ORDER, f"handheld: {why}")

    def describe(self) -> str:
        return f"policy: {self.policy} ({self.policy_reason})"

    def players(self, order: str) -> list:
        """Joysticks in an emulator's SDL order (see devices.sdl_joysticks), and the players under the policy."""
        joysticks = sdl_joysticks(self.devices, self.slots, self.behind_steam, order)
        return joysticks, player_order(joysticks, self.policy)

    def identity(self, joystick) -> tuple:
        """(stable id or None, VID:PID, name) of the physical pad behind a joystick."""
        if joystick.slot:
            return self.ids.get(joystick.slot.slot), joystick.slot.vid_pid, joystick.slot.name
        if joystick.device.vid_pid == STEAM_VIRTUAL_PAD:
            return None, "", joystick.device.name     # a virtual pad with no slot entry: nothing says what's behind
        return stable_id(joystick.device), joystick.device.vid_pid, joystick.device.name


def emulator_ports(probe: Probe) -> dict:
    """virtual or native evdev node -> {"player", "retroarch_port", "dolphin_device"}."""
    from .adapters.dolphin import DolphinAdapter
    from .adapters.retroarch import RetroArchAdapter
    out = {}
    _, players = probe.players(RetroArchAdapter().sdl_order)
    for n, j in enumerate(players, start=1):
        out[j.device] = {"player": n, "retroarch_port": j.index}
    dolphin = DolphinAdapter()
    joysticks, _ = probe.players(dolphin.sdl_order)
    for j in joysticks:
        out.setdefault(j.device, {})["dolphin_device"] = dolphin.device_ref(j, joysticks)
    return out


def cmd_validate(args) -> int:
    failed = 0
    for path in args.paths:
        files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            docs = doc["rules"] if isinstance(doc, dict) and isinstance(doc.get("rules"), list) else [doc]
            errors = [e for d in docs for e in validate_rule(d)]
            print(f"{'ok  ' if not errors else 'FAIL'} {f}")
            for e in errors:
                print(f"     {e}")
            failed += bool(errors)
    return 1 if failed else 0


def cmd_devices(args) -> int:
    db = ControllerDB(load_json(DATA / "controllers.json"))
    probe = Probe(args, db)
    ports = emulator_ports(probe)
    slots = []
    for s in probe.slots:
        slots.append({"slot": s.slot, "physical_vid_pid": s.vid_pid, "physical_id": s.device_id,
                      "type": s.type, "name": s.name,
                      "physical_model": db.model_for(s.vid_pid),
                      "virtual_node": s.virtual.handlers if s.virtual else None,
                      **(ports.get(s.virtual, {}) if s.virtual else {})})
    slot_of = {}   # physical pad id -> its Steam slot; a live slot beats a stale one Steam kept for the same pad
    live = {s.slot for s in probe.slots if s.virtual}
    for slot, pad_id in sorted(probe.ids.items(), key=lambda item: item[0] in live):
        slot_of[pad_id] = slot
    rows = []
    for dev in probe.pads:
        ctrl = db.classify((stable_id(dev),), dev.vid_pid, dev.name)
        rows.append({
            "name": dev.name, "vid_pid": dev.vid_pid, "id": stable_id(dev),
            "mode": "passthrough" if dev.vid_pid in probe.behind_steam else "native",
            "steam_slot": slot_of.get(stable_id(dev)),
            "model": ctrl.model, "family": ctrl.family, "brand": ctrl.brand, "style": ctrl.style,
            "needs_claim": db.is_ambiguous(ctrl.model) or ctrl.model is None,
            **ports.get(dev, {}),
        })
    if args.json:
        print(json.dumps({"controllers": rows, "steam_slots": slots,
                          "policy": {"name": probe.policy, "reason": probe.policy_reason}}, indent=2))
        return 0
    print(probe.describe())
    if not rows:
        print("No external controllers connected. (The Deck's own controls appear only as a Steam slot below.)")
    for r in rows:
        tag = " [needs claim]" if r["needs_claim"] else ""
        slot = f" steam_slot={r['steam_slot']}" if r["steam_slot"] is not None else ""
        print(f"{r['vid_pid']}  {r['name']:<40} model={r['model']} style={r['style']} mode={r['mode']}{slot}{tag}"
              f"{_ports_text(r)}")
    for s in slots:
        node = " ".join(s["virtual_node"]) if s["virtual_node"] else "not connected (Steam keeps the slot)"
        print(f"steam slot {s['slot']}: {s['name']} ({s['physical_vid_pid']}, model={s['physical_model']}) -> {node}"
              f"{_ports_text(s)}")
    return 0


def _ports_text(row: dict) -> str:
    """Where a pad lands in each emulator (only rows the emulators can see have these)."""
    if "player" not in row:
        return ""
    return (f"\n    player {row['player']}: retroarch port {row['retroarch_port']}, "
            f"dolphin {row.get('dolphin_device')}")


def cmd_explain(args) -> int:
    db = ControllerDB(load_json(DATA / "controllers.json"))
    if args.model:
        controller = db.classify(tuple(args.device_id), name=args.name, claimed_model=args.model)
    else:
        controller = db.classify(tuple(args.device_id), args.vid_pid, args.name)
    sources = [(DATA / "defaults", "shipped")] + [(d, "user") for d in (args.rules or [REPO / "examples"])]
    report = load_sources(sources)
    for path, problem in report.problems:
        print(f"warning: {path}: {problem}", file=sys.stderr)

    target = Target(system=args.system, emulator=args.emulator, game_id=args.game)
    result = resolver.resolve(report.rules, controller, target, load_layouts(DATA / "layouts"))
    if args.json:
        print(json.dumps({
            "controller": {"model": controller.model, "family": controller.family,
                           "brand": controller.brand, "style": controller.style},
            "bindings": {k: vars(c) for k, c in result.bindings.items()},
            "options": {k: vars(c) for k, c in result.options.items()},
            "warnings": result.warnings,
        }, indent=2))
    else:
        print(f"Controller: model={controller.model} family={controller.family} "
              f"brand={controller.brand} style={controller.style}")
        print(f"Target: system={target.system} emulator={target.emulator} game={target.game_id}\n")
        print(resolver.explain(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())


def cmd_apply(args) -> int:
    from . import pipeline
    req = pipeline.Request(args.emulator, args.system, args.config_root, args.rules or [REPO / "examples"],
                           core=args.core, game=args.game, players=args.player, probe_args=args,
                           write=args.write, state_dir=args.state_dir)
    try:
        outcome = pipeline.run(req, log=lambda line: print(line, file=sys.stderr))
    except pipeline.ApplyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    result = outcome.result
    for warning in outcome.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for patch in result.rejected:
        print(f"rejected (not a managed key): {patch}", file=sys.stderr)
    print(result.diff or "No changes.", end="" if result.diff else "\n")
    if args.write and result.changed_files:
        print(f"wrote: {', '.join(result.changed_files)}", file=sys.stderr)
    return 0


def cmd_backup(args) -> int:
    from . import restore
    if args.list:
        names = restore.list_backups(args.state_dir)
        print("\n".join(names) if names else "No backups.")
        return 0
    try:
        name, count = restore.backup(args.state_dir, args.name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"backup {name}: {count} file(s)" if count else
          f"backup {name}: map-helper hasn't written any file yet, so it's empty")
    return 0


def cmd_restore(args) -> int:
    from . import restore
    try:
        actions = restore.plan(args.state_dir, args.emulator, args.source, args.force)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not actions:
        print("Nothing to restore: map-helper hasn't written any file" + (f" for {args.emulator}." if args.emulator
                                                                           else "."))
        return 0
    if not args.dry_run:
        restore.run(args.state_dir, actions)
    verb = {"write": "would restore" if args.dry_run else "restored",
            "delete": "would delete" if args.dry_run else "deleted", "skip": "skipped", "ok": "unchanged"}
    for a in actions:
        print(f"{verb[a.kind]:<14} {a.emulator}: {a.rel} ({a.reason})")
    return 1 if any(a.kind == "skip" for a in actions) else 0
def cmd_doctor(args) -> int:
    from . import doctor
    findings = doctor.run(args.steam_root, args.retroarch_root, args.emudeck_settings, home=args.home)
    if args.json:
        print(json.dumps({"findings": [vars(f) for f in findings]}, indent=2))
    else:
        print(doctor.render(findings), end="")
    return 1 if any(f.severity == "error" for f in findings) else 0


def cmd_setup(args) -> int:
    from . import setup
    places = setup.Places(home=args.home, state_dir=args.state_dir, entry=getattr(args, "entry", None),
                          python=getattr(args, "python", "/usr/bin/python3"))
    report = (setup.setup if args.command == "setup" else setup.uninstall)(places, write=args.write)
    print(setup.render(report), end="")
    if not args.write and any(c.action in ("install", "update", "remove") for c in report.changes):
        print("Dry run: nothing changed. Add --write to make these changes.")
    return 1 if report.refused else 0
