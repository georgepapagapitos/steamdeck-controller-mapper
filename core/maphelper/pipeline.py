"""The apply pipeline that `map-helper apply` and mh-run share: probe → players → resolve → render → write.

It never prints. Progress lines go to a `log` callback (the CLI prints them to stderr; mh-run keeps them for its
log), and the result comes back with the warnings, for the caller to show. See docs/02 "Data flow: apply at launch".

Each emulator is one EMULATORS entry: how to build its adapter, where EmuDeck keeps its config, and how to render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import resolve as resolver
from .devices import ControllerDB
from .model import Target
from .store import load_json, load_layouts, load_sources
from .writer import ApplyResult, apply_patches

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
HOME = Path.home()


class ApplyError(Exception):
    """The request can't be carried out (unreadable devices, no core for the system); nothing was written."""


@dataclass
class Request:
    emulator: str
    system: str
    config_root: Path
    rules: list                              # user rule directories (shipped defaults are always loaded)
    core: Optional[str] = None               # RetroArch only
    game: Optional[str] = None
    players: Optional[list] = None           # MODEL[@DEVICE_ID] per player; None: probe the connected pads
    probe_args: object = None                # the add_probe_arguments() namespace, when players is None
    write: bool = False
    state_dir: Optional[Path] = None


@dataclass
class Outcome:
    result: ApplyResult
    warnings: list = field(default_factory=list)
    players: int = 0
    order: list = field(default_factory=list)    # each player's model id, for mh-run's log (no device ids)


@dataclass
class Rendering:
    rendered: object
    managed: dict
    checks: list = field(default_factory=list)


def _render_retroarch(adapter, req: Request, players: dict, assigned: dict, joysticks: list,
                      current: Callable) -> Rendering:
    try:
        core = adapter.core_for(req.system, req.core)
    except ValueError as e:
        raise ApplyError(str(e)) from None
    ports = {n: j.index for n, j in assigned.items()}
    return Rendering(adapter.render(players, core, current=current, ports=ports), adapter.managed_keys(core),
                     adapter.check(req.config_root, core, current, ports=bool(ports)))


def _render_by_device(adapter, req: Request, players: dict, assigned: dict, joysticks: list,
                      current: Callable) -> Rendering:
    """Dolphin and PCSX2: one device string per player (adapter.device_ref) and render(players, system, ...)."""
    devices = {n: adapter.device_ref(j, joysticks) for n, j in assigned.items()}
    return Rendering(adapter.render(players, req.system, current=current, devices=devices), adapter.managed_keys)


def _dolphin():
    from .adapters.dolphin import DolphinAdapter
    return DolphinAdapter()


def _pcsx2():
    from .adapters.pcsx2 import PCSX2Adapter
    return PCSX2Adapter()


def _retroarch():
    from .adapters.retroarch import RetroArchAdapter
    return RetroArchAdapter()


@dataclass(frozen=True)
class Emulator:
    adapter: Callable                         # () -> adapter
    render: Callable                          # (adapter, req, players, assigned, joysticks, current) -> Rendering
    config_root: Path                         # where EmuDeck's install keeps the config (docs/adapters/<id>.md)


EMULATORS = {
    "dolphin": Emulator(_dolphin, _render_by_device,
                        HOME / ".var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu"),   # Flatpak
    "pcsx2": Emulator(_pcsx2, _render_by_device, HOME / ".config/PCSX2"),                    # AppImage
    "retroarch": Emulator(_retroarch, _render_retroarch,
                          HOME / ".var/app/org.libretro.RetroArch/config/retroarch"),         # Flatpak
}


def run(req: Request, log: Callable[[str], None], gate: Optional[Callable[[], bool]] = None,
        adapter=None) -> Outcome:
    """gate: passed to the writer; called once the changed files are staged, False writes nothing."""
    from .cli import Probe
    emulator = EMULATORS[req.emulator]
    adapter = adapter or emulator.adapter()
    db = ControllerDB(load_json(DATA / "controllers.json"))
    report = load_sources([(DATA / "defaults", "shipped")] + [(d, "user") for d in req.rules])
    for path, problem in report.problems:
        log(f"warning: {path}: {problem}")
    layouts = load_layouts(DATA / "layouts")
    target = Target(system=req.system, emulator=req.emulator, game_id=req.game)

    players, assigned, joysticks, models = {}, {}, [], []
    if req.players:
        for n, spec in enumerate(req.players, start=1):
            model, _, device_id = spec.partition("@")
            controller = db.classify((device_id,) if device_id else (), claimed_model=model)
            players[n] = resolver.set_by_rules(resolver.resolve(report.rules, controller, target, layouts))
            models.append(controller.model or "unknown")
    else:
        # No --player: the pads connected now, in Steam's order (docs/04 §5.1 steam-order), each player also pointed
        # at its own pad in the emulator's numbering (§5.2).
        try:
            probe = Probe(req.probe_args, db)
        except OSError as e:
            raise ApplyError(f"can't read the connected devices ({e}); pass --player or --proc-file") from None
        log(probe.describe())
        joysticks, order = probe.players(adapter.sdl_order)
        for n, joystick in enumerate(order, start=1):
            device_id, vid_pid, name = probe.identity(joystick)
            controller = db.classify((device_id,) if device_id else (), vid_pid, name)
            if db.is_ambiguous(controller.model) or controller.model is None:
                log(f"warning: player {n} ({name}) needs a model claim; resolving it as {controller.model or 'unknown'}"
                    f" (style {controller.style})")
            players[n] = resolver.set_by_rules(resolver.resolve(report.rules, controller, target, layouts))
            models.append(controller.model or "unknown")
            assigned[n] = joystick
            slot = f"steam slot {joystick.slot.slot}" if joystick.slot else "not behind Steam"
            log(f"player {n}: {name} ({slot}) -> {joystick.device.name} ({' '.join(joystick.device.handlers)}), "
                f"SDL index {joystick.index}")
        if not order:
            log("warning: no controllers found; nothing to assign")

    rendering = emulator.render(adapter, req, players, assigned, joysticks, _reader(Path(req.config_root)))
    result = apply_patches(req.config_root, rendering.rendered.patches, rendering.managed, state_dir=req.state_dir,
                           dry_run=not req.write, emulator=req.emulator, gate=gate)
    warnings = [w for p in players.values() for w in p.warnings] + rendering.rendered.warnings + rendering.checks
    return Outcome(result, warnings, len(players), models)


def _reader(config_root: Path) -> Callable[[str, Optional[str], str], Optional[str]]:
    """current(file, section, key): the value on disk now. Each file is parsed once; adapters ask for hundreds of
    keys (RetroArch's hotkeys), and re-parsing retroarch.cfg for each took most of a second."""
    from .formats.ini import IniDocument
    cache = {}

    def current(file, section, key):
        if file not in cache:
            path = config_root / file
            cache[file] = IniDocument.parse(path.read_text(encoding="utf-8")).index() if path.exists() else {}
        return cache[file].get((section, key))
    return current
