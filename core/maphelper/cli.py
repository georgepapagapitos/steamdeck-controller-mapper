"""`map-helper` command line. Prototype subset of docs/08 "CLI parity"."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import resolve as resolver
from .devices import (ControllerDB, is_gamepad, parse_ignore_devices, parse_proc_input_devices,
                      parse_virtual_gamepad_info, stable_id, steam_slots)
from .model import Target
from .store import load_json, load_layouts, load_sources
from .validate import validate_rule

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="map-helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate rule files")
    p.add_argument("paths", nargs="+", type=Path)

    p = sub.add_parser("devices", help="list connected controllers")
    p.add_argument("--proc-file", type=Path, default=Path("/proc/bus/input/devices"),
                   help="read a saved copy instead of the live file")
    # Steam sets the env var only inside a game's environment; outside one (a shell, ssh) the file is still there.
    p.add_argument("--virtual-info", type=Path,
                   default=os.environ.get("SteamVirtualGamepadInfo",
                                          Path.home() / ".local/share/Steam/config/virtualgamepadinfo.txt"),
                   help="Steam's virtual gamepad info file (default: $SteamVirtualGamepadInfo, else Steam's config dir)")
    p.add_argument("--ignore-devices", default=os.environ.get("SDL_GAMECONTROLLER_IGNORE_DEVICES", ""),
                   help="pads behind Steam Input (default: $SDL_GAMECONTROLLER_IGNORE_DEVICES)")
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
    p.add_argument("--emulator", required=True, choices=["dolphin"])
    p.add_argument("--system", required=True)
    p.add_argument("--game")
    p.add_argument("--config-root", type=Path, required=True, help="the emulator's config directory")
    p.add_argument("--player", action="append", required=True, metavar="MODEL[@DEVICE_ID]",
                   help="controller model per player, in order (repeatable), e.g. sony.ds4.v2@mac:aa:bb:..")
    p.add_argument("--rules", type=Path, action="append", help="user rule directory (default: examples/)")
    p.add_argument("--write", action="store_true", help="write the files (default: print the diff only)")
    p.add_argument("--state-dir", type=Path, default=Path.home() / ".local" / "state" / "map-helper",
                   help="where pristine backups go")

    args = parser.parse_args(argv)
    return {"validate": cmd_validate, "devices": cmd_devices, "explain": cmd_explain,
            "apply": cmd_apply}[args.command](args)


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
    devices = parse_proc_input_devices(args.proc_file.read_text(encoding="utf-8"))
    slots = []
    if args.virtual_info and Path(args.virtual_info).is_file():
        info = parse_virtual_gamepad_info(Path(args.virtual_info).read_text(encoding="utf-8"))
        for s in steam_slots(devices, info):
            slots.append({"slot": s.slot, "physical_vid_pid": s.vid_pid, "physical_id": s.device_id,
                          "type": s.type, "name": s.name,
                          "physical_model": db.model_for(s.vid_pid),
                          "virtual_node": s.virtual.handlers if s.virtual else None})
    # A pad with a live Steam slot is behind Steam. Steam's ignore list can't say that: it names every pad type Steam
    # supports, connected or not (793 entries on a Deck, tests/fixtures/devices/game-steam-input-on), so it's only a
    # fallback when there's no slot file.
    live = {s["physical_vid_pid"] for s in slots if s["virtual_node"]}
    behind_steam = live if slots else parse_ignore_devices(args.ignore_devices)
    slot_of = {s["physical_id"]: s["slot"] for s in slots if s["physical_id"]}
    # A wired X-input pad's handle holds no MAC; fall back to VID:PID when only one live slot and one pad have it.
    pads = [d for d in devices if is_gamepad(d) and not db.is_virtual(d.vid_pid)]
    for s in slots:
        same = [d for d in pads if d.vid_pid == s["physical_vid_pid"]]
        live = [t for t in slots if t["virtual_node"] and t["physical_vid_pid"] == s["physical_vid_pid"]]
        if not s["physical_id"] and s["virtual_node"] and len(same) == 1 and len(live) == 1:
            slot_of.setdefault(stable_id(same[0]), s["slot"])
    rows = []
    for dev in devices:
        if not is_gamepad(dev) or db.is_virtual(dev.vid_pid):
            continue
        ctrl = db.classify((stable_id(dev),), dev.vid_pid, dev.name)
        rows.append({
            "name": dev.name, "vid_pid": dev.vid_pid, "id": stable_id(dev),
            "mode": "passthrough" if dev.vid_pid in behind_steam else "native",
            "steam_slot": slot_of.get(stable_id(dev)),
            "model": ctrl.model, "family": ctrl.family, "brand": ctrl.brand, "style": ctrl.style,
            "needs_claim": db.is_ambiguous(ctrl.model) or ctrl.model is None,
        })
    if args.json:
        print(json.dumps({"controllers": rows, "steam_slots": slots}, indent=2))
        return 0
    if not rows:
        print("No external controllers connected. (The Deck's own controls appear only as a Steam slot below.)")
    for r in rows:
        tag = " [needs claim]" if r["needs_claim"] else ""
        slot = f" steam_slot={r['steam_slot']}" if r["steam_slot"] is not None else ""
        print(f"{r['vid_pid']}  {r['name']:<40} model={r['model']} style={r['style']} mode={r['mode']}{slot}{tag}")
    for s in slots:
        node = " ".join(s["virtual_node"]) if s["virtual_node"] else "not connected (Steam keeps the slot)"
        print(f"steam slot {s['slot']}: {s['name']} ({s['physical_vid_pid']}, model={s['physical_model']}) -> {node}")
    return 0


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
    from .adapters.dolphin import DolphinAdapter
    from .formats.ini import IniDocument
    from .writer import apply_patches

    db = ControllerDB(load_json(DATA / "controllers.json"))
    report = load_sources([(DATA / "defaults", "shipped")] + [(d, "user") for d in (args.rules or [REPO / "examples"])])
    for path, problem in report.problems:
        print(f"warning: {path}: {problem}", file=sys.stderr)
    layouts = load_layouts(DATA / "layouts")
    target = Target(system=args.system, emulator=args.emulator, game_id=args.game)

    players = {}
    for n, spec in enumerate(args.player, start=1):
        model, _, device_id = spec.partition("@")
        controller = db.classify((device_id,) if device_id else (), claimed_model=model)
        players[n] = resolver.resolve(report.rules, controller, target, layouts)

    def current(file, section, key):
        path = args.config_root / file
        return IniDocument.parse(path.read_text(encoding="utf-8")).get(section, key) if path.exists() else None

    adapter = DolphinAdapter()
    rendered = adapter.render(players, args.system, current=current)
    result = apply_patches(args.config_root, rendered.patches, adapter.managed_keys,
                           state_dir=args.state_dir, dry_run=not args.write)
    for warning in [w for p in players.values() for w in p.warnings] + rendered.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for patch in result.rejected:
        print(f"rejected (not a managed key): {patch}", file=sys.stderr)
    print(result.diff or "No changes.", end="" if result.diff else "\n")
    if args.write and result.changed_files:
        print(f"wrote: {', '.join(result.changed_files)}", file=sys.stderr)
    return 0
