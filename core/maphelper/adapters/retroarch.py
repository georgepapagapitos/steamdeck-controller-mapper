"""RetroArch adapter: per-player pad remaps in a core's own .rmp (prototype). See docs/adapters/retroarch.md.

All RetroArch facts come from data/adapters/retroarch/ (retropad.json, hotkeys.json and one descriptor per core).
Hotkeys go into retroarch.cfg, and only when some rule sets one; so does each assigned player's joypad port
(input_playerN_joypad_index). Core options a descriptor maps (its `options`) go into the one options file
RetroArch loads for the launch (options_target).
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from .. import DATA as _DATA
from ..formats.ini import IniDocument
from ..resolve import Resolution
from ..store import load_json
from ..writer import Patch
from .dolphin import Rendered

DATA = _DATA / "adapters" / "retroarch"
REMAP_DIR = "config/remaps"   # input_remapping_directory's default under the config root; EmuDeck keeps it
OPTIONS_DIR = "config"        # RetroArch's config directory (rgui_config_directory; EmuDeck's is the root's config/)
SUFFIXES = ("_btn", "_axis")
_PORT_LINE = re.compile(r"^\s*input_player\d+_joypad_index\s*=", re.MULTILINE)
_REMAP_KEY = re.compile(r"^input_player\d+_(btn|stk)_")


class RetroArchAdapter:
    id = "retroarch"

    def __init__(self, retropad: Optional[dict] = None, cores: Optional[dict] = None, hotkeys: Optional[dict] = None):
        self.pad = retropad or load_json(DATA / "retropad.json")
        self.hotkeys = hotkeys or load_json(DATA / "hotkeys.json")
        self.cores = cores or {f.stem: load_json(f) for f in sorted((DATA / "cores").glob("*.json"))}
        self.ids = {**self.pad["retropad_ids"], **self.pad["analog_half_axis_ids"]}
        self.sdl_order = self.pad["joypad_ports"]["sdl_order"]

    # -- cores -----------------------------------------------------------------

    def core_for(self, system: str, core: Optional[str] = None) -> dict:
        """The descriptor for --core (file id or library name), or the only core that runs this system."""
        if core:
            for cid, desc in self.cores.items():
                if core in (cid, desc["core"]):
                    return desc
            raise ValueError(f"unknown RetroArch core {core!r}; known: {', '.join(sorted(self.cores))}")
        matches = [cid for cid, desc in self.cores.items() if system in desc["systems"]]
        if len(matches) != 1:
            raise ValueError(f"{system}: {'no RetroArch core' if not matches else 'several cores'} "
                             f"({', '.join(matches) or 'none'}); pass --core")
        return self.cores[matches[0]]

    @staticmethod
    def remap_file(desc: dict) -> str:
        """The core-level remap: loaded when no game or content-dir remap exists (config_load_remap)."""
        return f"{REMAP_DIR}/{desc['core']}/{desc['core']}.rmp"

    def remap_target(self, config_root: Optional[Path], desc: dict, game: Optional[str], folder: Optional[str],
                     game_scoped: bool, exists: Optional[Callable[[str], bool]] = None) -> tuple[str, Optional[str]]:
        """(the remap file to write, the file to seed it from when it's new, or None).

        RetroArch loads the first that exists of the game's, the content folder's and the core's remap, and resets
        every remap before applying it (config_load_remap, docs/adapters/retroarch.md "Load precedence"). So a
        binding from a game rule goes into the game's .rmp, which must then carry everything else too: it starts as
        a copy of the file RetroArch would load instead. Without game rules, the folder's .rmp if there is one,
        else the core's. exists: whether a file is there without map-helper (baseline.exists), so a game .rmp
        map-helper made for rules that are gone doesn't count, and is deleted instead."""
        exists = exists or (lambda rel: config_root is not None and (Path(config_root) / rel).is_file())
        fallback = self.remap_file(desc)
        if folder and exists(f"{REMAP_DIR}/{desc['core']}/{folder}.rmp"):
            fallback = f"{REMAP_DIR}/{desc['core']}/{folder}.rmp"
        if game:
            mine = f"{REMAP_DIR}/{desc['core']}/{game}.rmp"
            if exists(mine):
                return mine, None
            if game_scoped:
                return mine, fallback if exists(fallback) else None
        return fallback, None

    @staticmethod
    def options_file(desc: dict, name: str) -> str:
        """config/<library_name>/<name>.opt: name is the game id (game options), the ROM's folder name (folder
        options) or library_name itself (core options). validate_per_core_options, runloop.c L1083-1114 @ v1.22.2."""
        return f"{OPTIONS_DIR}/{desc['core']}/{name}.opt"

    def managed_keys(self, desc: dict, patches: list = ()) -> dict:
        """patches: the rendered ones; an options file manages exactly the option keys written to it."""
        hk = self.hotkeys
        bases = [hk["enable"], *hk["targets"].values()]
        remap_keys = {"keys": ["input_player[1-9]_btn_*", "input_player[1-9]_stk_*"]}
        managed = {self.remap_file(desc): remap_keys,
                   hk["file"]: {"keys": [f"input_{b}{s}" for b in bases for s in SUFFIXES]
                                + ["input_player[1-9]_joypad_index", "input_player1[0-6]_joypad_index"]}}
        for p in patches:
            if p.file.endswith(".opt"):
                managed.setdefault(p.file, {"keys": []})["keys"].append(p.key)
            elif p.file.endswith(".rmp") and p.file.startswith(f"{REMAP_DIR}/{desc['core']}/"):
                managed[p.file] = remap_keys             # the game's or folder's remap this launch writes
        return managed

    def options_target(self, config_root: Optional[Path], desc: dict, game: Optional[str], folder: Optional[str],
                       game_specific: bool = True, game_scoped: bool = False,
                       exists: Optional[Callable[[str], bool]] = None) -> tuple[str, Optional[str]]:
        """(the options file to write, the file to seed it from when it's new, or None).

        RetroArch loads exactly one file, with no layering (runloop_init_core_options_path, runloop.c L1147-1236
        @ v1.22.2): with game_specific_options on, the game's .opt if it exists, else the folder's; otherwise the
        core's. Keys the file lacks take the core's defaults. So a game-scoped option goes into the game's .opt,
        created as a copy of the file RetroArch would load instead, which keeps every other option as it was."""
        exists = exists or (lambda rel: config_root is not None and (Path(config_root) / rel).is_file())
        fallback = self.options_file(desc, desc["core"])
        if game_specific and folder and exists(self.options_file(desc, folder)):
            fallback = self.options_file(desc, folder)
        if game_specific and game:
            mine = self.options_file(desc, game)
            if exists(mine):
                return mine, None
            if game_scoped:
                return mine, fallback if exists(fallback) else None
        return fallback, None

    # -- render ----------------------------------------------------------------

    def render(self, players: dict[int, Resolution], desc: dict,
               current: Optional[Callable[[str, Optional[str], str], Optional[str]]] = None,
               ports: Optional[dict[int, int]] = None, config_root: Optional[Path] = None,
               game: Optional[str] = None, folder: Optional[str] = None) -> Rendered:
        """players: RetroArch user number -> resolution. current(file, section, key) reads the live value.
        ports: user number -> the joypad port (SDL index) of that user's pad, written as input_playerN_joypad_index.
        config_root, game (the game id) and folder (the ROM's folder name) pick the core options file."""
        current = current or (lambda *_: None)
        exists = getattr(current, "exists", None)       # baseline.Baseline: the files as they'd be without us
        game_scoped = any(choice.content == "game" and target in desc["targets"]
                          for resolution in players.values() for target, choice in resolution.bindings.items())
        file, seed = self.remap_target(config_root, desc, game, folder, game_scoped, exists)
        self.remap_rel = file                           # describe and check read the same file
        out = Rendered()
        # What this launch answers for: a rule that's gone is reverted in these, and a remap or options file
        # map-helper made that no rule needs now is deleted; another game's files are left to that game.
        names = [desc["core"], *(n for n in (folder, game) if n)]
        out.scope = {self.hotkeys["file"], *(f"{REMAP_DIR}/{desc['core']}/{n}.rmp" for n in names),
                     *(self.options_file(desc, n) for n in names)}
        if seed:
            out.seeds[file] = seed
        for user, port in sorted((ports or {}).items()):
            out.patches.append(Patch(self.hotkeys["file"], None, self.pad["joypad_ports"]["key"].format(N=user), f'"{port}"'))
        for user, resolution in sorted(players.items()):
            remap = self._remap(user, resolution, desc, out)
            if not remap:
                continue
            # Remaps aren't swaps: a source keeps driving its live target unless remapped, so any source still
            # pointed at a target another source now claims must let go, or both would press it.
            claimed = set(remap.values())
            for name, own_id in self.pad["retropad_ids"].items():
                if name in remap:
                    continue
                live = current(file, None, self._key(user, name))
                target = own_id if live is None else int(live.strip('"'))
                if target in claimed:
                    remap[name] = self.pad["unmapped_value"]
            for name, target in remap.items():
                out.patches.append(Patch(file, None, self._key(user, name), f'"{target}"'))
        if 1 in players:
            self._render_hotkeys(players[1], current, out)
        self._render_options(players, desc, current, config_root, game, folder, out)
        return out

    def _remap(self, user: int, resolution: Resolution, desc: dict, out: Rendered) -> dict:
        """RetroPad source name -> RetroPad id the core receives, for the bindings rules set."""
        remap = {}
        for target, choice in resolution.bindings.items():
            core_input = desc["targets"].get(target)
            if core_input is None:
                if target.startswith("hotkey."):
                    continue
                out.warnings.append(f"retroarch: {desc['core']} has no input for {target}")
                continue
            source = choice.value
            if "input" not in source:
                out.warnings.append(f"retroarch: {target}: chords can't be remapped in RetroArch")
                continue
            physical = self.pad["physical_to_retropad"].get(source["input"])
            if physical not in self.ids or core_input not in self.ids:
                # guide, paddles, gyro... have no RetroPad id; full axes (LEFT_X) aren't remapped one-to-one
                out.warnings.append(f"retroarch: {target}: {source['input']} can't drive {core_input} in a remap")
                continue
            remap[physical] = self.ids[core_input]
        return remap

    # -- hotkeys (retroarch.cfg) -------------------------------------------------

    def _render_hotkeys(self, resolution: Resolution, current: Callable, out: Rendered) -> None:
        """Player 1's hotkey rules -> input_enable_hotkey + input_<action> in retroarch.cfg, in the indices of the
        active joypad driver. RetroArch has one enable input for all hotkeys, so each rule must be enable + one."""
        hk, cfg = self.hotkeys, self.hotkeys["file"]
        chords, unbound = {}, []
        for target, choice in sorted(resolution.bindings.items()):
            if not target.startswith("hotkey."):
                continue
            base = hk["targets"].get(target)
            chord = choice.value.get("chord") or []
            if base is None:
                out.warnings.append(f"retroarch: no hotkey for {target}")
            elif choice.value.get("input") == "none":
                unbound.append(base)
            elif len(chord) != 2:
                out.warnings.append(f"retroarch: {target}: a RetroArch hotkey is the enable button plus one more, "
                                    f"not {'+'.join(chord) or choice.value.get('input')}")
            else:
                chords[target] = chord
        if not chords and not unbound:
            return
        live = lambda key: (current(cfg, None, key) or "").strip('"')
        driver = live(hk["driver_key"])
        indices = hk["drivers"].get(driver)
        if indices is None:
            out.warnings.append(f"retroarch: {hk['driver_key']} is {driver or 'unset'!r}; map-helper only knows the "
                                f"button numbers for {', '.join(hk['drivers'])}, so hotkeys were not written")
            return

        def bind(name: str) -> Optional[tuple]:
            if name in indices["buttons"]:
                return "_btn", str(indices["buttons"][name])
            if name in indices["axes"]:
                return "_axis", indices["axes"][name]
            return None

        binds = {}                                   # RetroArch base -> canonical physical input
        if chords:
            # The enable input is the one most chords share; on a tie, the one already live.
            counts = Counter(i for chord in chords.values() for i in chord)
            live_enable = {(s, live(f"input_{hk['enable']}{s}")) for s in SUFFIXES}
            enable = max(sorted(counts), key=lambda i: (counts[i], bind(i) in live_enable))
            if bind(enable) is None:
                out.warnings.append(f"retroarch: the hotkey enable button {enable} has no {driver} index on the "
                                    f"Steam virtual pad; hotkeys not written")
                return
            binds[hk["enable"]] = enable
            for target, chord in chords.items():
                action = next((i for i in chord if i != enable), None)
                if enable not in chord or action is None:
                    out.warnings.append(f"retroarch: {target}: all hotkeys share one enable button ({enable}); "
                                        f"{'+'.join(chord)} is not {enable} plus another button")
                elif bind(action) is None:
                    out.warnings.append(f"retroarch: {target}: {action} has no {driver} index on the Steam "
                                        f"virtual pad")
                else:
                    binds[hk["targets"][target]] = action
            if len(binds) == 1:                      # no action left to enable
                del binds[hk["enable"]]
            elif bind(enable) not in live_enable:
                out.warnings.append(f"retroarch: the hotkey enable button is now {enable}; every RetroArch hotkey "
                                    f"moves with it, including the ones no rule sets")

        written = {}                                 # (suffix, value) -> base, for every input we bind
        for base, name in binds.items():
            suffix, value = bind(name)
            for s in SUFFIXES:
                out.patches.append(Patch(cfg, None, f"input_{base}{s}", f'"{value}"' if s == suffix else '"nul"'))
            if (suffix, value) in written:
                out.warnings.append(f"retroarch: input_{base} and input_{written[suffix, value]} are on the same "
                                    f"input; both fire")
            written[(suffix, value)] = base
        for base in unbound:
            out.patches += [Patch(cfg, None, f"input_{base}{s}", '"nul"') for s in SUFFIXES]
        self._warn_quit_combo(binds, unbound, live, out)
        # A hotkey still on an input one of ours now uses would fire with it. Managed ones let go, others are flagged.
        managed = set(hk["targets"].values())
        for base in hk["meta_bases"]:
            if base in binds or base in unbound or base == hk["enable"]:
                continue
            for s in SUFFIXES:
                other = written.get((s, live(f"input_{base}{s}")))
                if other is None:
                    continue
                if base in managed:
                    out.patches.append(Patch(cfg, None, f"input_{base}{s}", '"nul"'))
                    out.warnings.append(f"retroarch: unbound input_{base}{s}, which was on the same input as "
                                        f"input_{other}")
                else:
                    out.warnings.append(f"retroarch: input_{base}{s} is on the same input as input_{other}; "
                                        f"both fire")

    def _warn_quit_combo(self, binds: dict, unbound: list, live: Callable, out: Rendered) -> None:
        """input_quit_gamepad_combo quits on its own, whatever hotkey.exit says. We leave it alone, but say so."""
        combo, base = self.hotkeys["quit_combo"], self.hotkeys["targets"]["hotkey.exit"]
        if base not in binds and base not in unbound:
            return
        try:
            index = int(live(combo["key"]) or 0)
        except ValueError:
            return
        if not 0 < index < len(combo["combos"]):
            return
        name = combo["combos"][index]
        if base in binds and set(name.split("+")) == {binds[self.hotkeys["enable"]].title(), binds[base].title()}:
            return                                   # the rule puts exit where the combo already is
        out.warnings.append(f"retroarch: {combo['key']} = \"{index}\": {name} still quits RetroArch, "
                            f"wherever hotkey.exit is")

    # -- core options (config/<core>/*.opt) ---------------------------------------

    def _render_options(self, players: dict[int, Resolution], desc: dict, current: Callable,
                        config_root: Optional[Path], game: Optional[str], folder: Optional[str],
                        out: Rendered) -> None:
        """The descriptor's `options`: a global one from player 1's resolution (like hotkeys), a per-player one
        (`{N}` in the key) from player N's. A player whose rules don't set it leaves that key alone."""
        values = {}                                  # core option key -> (value, Choice)
        for option, spec in desc.get("options", {}).items():
            for user in range(1, spec["players"] + 1) if spec.get("per_player") else (1,):
                choice = players[user].options.get(option) if user in players else None
                value = None if choice is None else self._option_value(option, spec, choice.value, out)
                if value is not None:
                    values[spec["key"].format(N=user)] = (value, choice)
        if not values:
            return
        setting = lambda key, default: (current(self.hotkeys["file"], None, key) or default).strip('"')
        # Defaults: DEFAULT_GLOBAL_CORE_OPTIONS false, DEFAULT_GAME_SPECIFIC_OPTIONS true (config.def.h L910-914).
        if setting("global_core_options", "false") == "true":
            out.warnings.append("retroarch: global_core_options is on, so every core shares "
                                "retroarch-core-options.cfg; map-helper doesn't write it, and core options were not "
                                "written")
            return
        game_specific = setting("game_specific_options", "true") != "false"
        scoped = sorted(k for k, (_, choice) in values.items() if choice.content == "game")
        if scoped and not game_specific:
            # The game's .opt would be ignored, and the core's is shared by every game: leave the game's values out.
            out.warnings.append(f"retroarch: game_specific_options is off, so RetroArch ignores game options files; "
                                f"{', '.join(scoped)} from game rules not written")
            values = {k: v for k, v in values.items() if k not in scoped}
        rel, seed = self.options_target(config_root, desc, game, folder, game_specific,
                                        game_scoped=bool(scoped) and game_specific,
                                        exists=getattr(current, "exists", None))
        if seed:
            out.seeds[rel] = seed
        elif config_root is not None and not (Path(config_root) / rel).is_file() \
                and (Path(config_root) / "retroarch-core-options.cfg").is_file():
            # With no core .opt yet, RetroArch takes the initial values from retroarch-core-options.cfg (src_path,
            # runloop.c L1188-1230 @ v1.22.2); the file we create replaces that source.
            out.warnings.append(f"retroarch: {rel} doesn't exist yet; map-helper creates it with only its own "
                                f"options, so this core's other options in retroarch-core-options.cfg stop applying")
        for key, (value, _) in sorted(values.items()):
            out.patches.append(Patch(rel, None, key, f'"{value}"'))

    @staticmethod
    def _option_value(option: str, spec: dict, value, out: Rendered) -> Optional[str]:
        """A canonical value as one the core lists. RetroArch drops a value that isn't listed and uses the default
        (core_option_manager.c L1031-1053 @ v1.22.2), so a percent snaps to the nearest listed one."""
        if "percent_values" in spec:
            allowed, percent = spec["percent_values"], round(value * 100, 6)
            nearest = min(allowed, key=lambda v: (abs(v - percent), v))
            if not allowed[0] <= percent <= allowed[-1]:
                out.warnings.append(f"retroarch: {option} {value} is outside {spec['key']}'s range "
                                    f"({allowed[0]}-{allowed[-1]}%); wrote {nearest}")
            return str(nearest)
        if value not in spec["values"]:
            out.warnings.append(f"retroarch: {spec['key']} has no {value!r} (only {', '.join(spec['values'])})")
            return None
        return value

    # -- show ------------------------------------------------------------------

    def describe(self, user: int, after: Callable, desc: dict, config_root: Optional[Path] = None,
                 game: Optional[str] = None, folder: Optional[str] = None, system: Optional[str] = None):
        """What user's pad drives once the patches are written (after: as current, after the write). Each physical
        input sends its RetroPad id unless the remap moves it (an absent key is identity, -1 unmapped); the core
        reads the ids its descriptor's targets name. Player 1 also gets the hotkey enable button noted. A core that
        runs several systems (Flycast: Dreamcast, Naomi, Atomiswave) lists targets for each; only system's count."""
        from ..show import Described
        out, file = Described(port=user), getattr(self, "remap_rel", None) or self.remap_file(desc)
        names = {v: k for k, v in self.ids.items()}
        default = ("emulator", f"{desc['core']} default", False)
        hold = desc.get("c_button_chord", {}).get("hold")
        for physical, source in self.pad["physical_to_retropad"].items():
            if source not in self.ids:
                continue                             # full axes: their halves are listed
            key = self._key(user, source)
            raw = after(file, None, key)
            core_input = names.get(self.ids[source] if raw is None else int(raw.strip('"')))
            src = default if raw is None else ("emulator", f"remap {Path(file).name}", after.patched(file, None, key))
            for target, wanted in desc["targets"].items():
                if system and not target.startswith(f"{system}."):
                    continue
                if core_input and wanted in (core_input, core_input.rstrip("+-")):
                    out.drives.append((physical, target, src))
            if hold and core_input == hold:
                out.notes[physical] = (f"{desc['core']}'s C-button modifier: hold it and the face buttons give "
                                       f"C buttons", default, "Hold for C buttons")
        if user == 1:
            self._describe_enable(after, out)
        self._describe_options(user, after, desc, config_root, game, folder, out)
        return out

    def _describe_enable(self, after: Callable, out) -> None:
        hk, cfg = self.hotkeys, self.hotkeys["file"]
        indices = hk["drivers"].get((after(cfg, None, hk["driver_key"]) or "").strip('"'))
        if indices is None:
            return
        for suffix, table in (("_btn", indices["buttons"]), ("_axis", indices["axes"])):
            key = f"input_{hk['enable']}{suffix}"
            value = (after(cfg, None, key) or "").strip('"')
            physical = next((p for p, v in table.items() if str(v) == value), None)
            if physical is None:
                continue
            if after.patched(cfg, None, key):
                src = ("emulator", cfg, True)        # a hotkey rule moved it
            elif all((after(cfg, None, k) or "").strip('"') == v for k, v in hk["emudeck_enable"].items()
                     if not k.startswith("_")):
                src = ("emudeck", "EmuDeck's RetroArch hotkey button", False)
            else:
                src = ("emulator", cfg, False)
            text, short = "RetroArch's hotkey button (hold it with another button)", "Hotkey button"
            if physical in out.notes:
                text, short = f"{text}; {out.notes[physical][0]}", f"{short}; {out.notes[physical][2].lower()}"
            out.notes[physical] = (text, src, short)

    def _describe_options(self, user: int, after: Callable, desc: dict, config_root: Optional[Path],
                          game: Optional[str], folder: Optional[str], out) -> None:
        """The descriptor's options as the .opt RetroArch loads after the write has them: the file this run writes,
        else the one options_target picks."""
        if not desc.get("options"):
            return
        written = sorted(f for f in after.files if f.endswith(".opt"))
        if written:
            rel = written[0]
        else:
            game_specific = (after(self.hotkeys["file"], None, "game_specific_options") or "").strip('"') != "false"
            rel, _ = self.options_target(config_root, desc, game, folder, game_specific,
                                         exists=getattr(getattr(after, "current", None), "exists", None))
        for option, spec in desc["options"].items():
            if spec.get("per_player") and user > spec["players"]:
                continue
            key = spec["key"].format(N=user)
            raw = after(rel, None, key)
            if raw is None:
                raw = spec["default"][user - 1] if isinstance(spec["default"], list) else spec["default"]
                src = ("emulator", f"{desc['core']} default", False)
            else:
                raw = raw.strip('"')
                src = ("emulator", Path(rel).name, after.patched(rel, None, key))
            value = int(raw) / 100 if "percent_values" in spec and raw.isdigit() else raw
            out.options.append((option, value, src, user if spec.get("per_player") else 1))

    @staticmethod
    def _key(user: int, name: str) -> str:
        """B -> input_player1_btn_b, LEFT_X+ -> input_player1_stk_l_x+ (input_remapping_save_file)."""
        if "_" in name and name[-1] in "+-":
            side, axis = name[:-1].split("_")
            return f"input_player{user}_stk_{side[0].lower()}_{axis.lower()}{name[-1]}"
        return f"input_player{user}_btn_{name.lower()}"

    # -- checks ----------------------------------------------------------------

    def check(self, config_root: Path, desc: dict,
              current: Callable[[str, Optional[str], str], Optional[str]], ports: bool = False,
              game: Optional[str] = None, folder: Optional[str] = None) -> list[str]:
        """Things that make RetroArch ignore the core-level remap we write (and, with ports, the joypad ports), and
        what the options file RetroArch loads for this launch (game, folder: as for render) says."""
        warnings = self._check_ports(config_root, desc, current) if ports else []
        warnings += self._check_options(config_root, desc, current, game, folder)
        for key, why in (("auto_remaps_enable", "remap files aren't loaded at all"),
                         ("input_remap_binds_enable", "remaps are ignored")):
            if (current("retroarch.cfg", None, key) or "").strip('"') == "false":
                warnings.append(f"retroarch: {key} is false in retroarch.cfg, so {why}")
        if (current("retroarch.cfg", None, "input_remap_sort_by_controller_enable") or "").strip('"') == "true":
            warnings.append("retroarch: input_remap_sort_by_controller_enable is on; remaps are looked up per "
                            "controller name, so the core-level file we write isn't used")
        folder = Path(config_root) / REMAP_DIR / desc["core"]
        mine = Path(getattr(self, "remap_rel", None) or self.remap_file(desc)).name
        for shadow in sorted(folder.glob("*.rmp")) if folder.is_dir() else []:
            if shadow.name != mine:
                warnings.append(f"retroarch: {shadow.relative_to(config_root)} is a game or folder remap; when it "
                                f"matches, RetroArch loads it instead of {mine} (no layering)")
        return warnings

    def _check_options(self, config_root: Path, desc: dict, current: Callable, game: Optional[str],
                       folder: Optional[str]) -> list[str]:
        if (current(self.hotkeys["file"], None, "global_core_options") or "").strip('"') == "true":
            return []                                # render says so when an option is set
        game_specific = (current(self.hotkeys["file"], None, "game_specific_options") or "").strip('"') != "false"
        rel, _ = self.options_target(config_root, desc, game, folder, game_specific,
                                     exists=getattr(current, "exists", None))
        warnings = []
        if desc.get("options") and rel == self.options_file(desc, folder or ""):
            warnings.append(f"retroarch: {rel} is a folder options file; RetroArch loads it instead of "
                            f"{desc['core']}.opt (no layering), so core options go there")
        for variant in desc.get("core_option_variants", {}):
            key, _, value = variant.partition("=")
            if (current(rel, None, key) or "").strip('"') == value:
                warnings.append(f"retroarch: {rel} sets {key} = \"{value}\"; map-helper's {desc['core']} remaps "
                                f"assume the core's default layout, so buttons land elsewhere")
        return warnings

    def _check_ports(self, config_root: Path, desc: dict,
                     current: Callable[[str, Optional[str], str], Optional[str]]) -> list[str]:
        warnings, cfg = [], self.hotkeys["file"]
        driver = (current(cfg, None, "input_joypad_driver") or "").strip('"')
        if driver != "sdl2":
            warnings.append(f"retroarch: input_joypad_driver is {driver or 'unset'}, not sdl2; joypad ports are worked "
                            f"out in SDL's order, so players may land on the wrong pads")
        if (current(cfg, None, "input_assign_ports_on_button_press") or "").strip('"') == "true":
            warnings.append("retroarch: input_assign_ports_on_button_press is on; RetroArch hands out ports as pads "
                            "press a button, so the joypad ports we write don't hold")
        for user in range(1, 17):
            if (current(cfg, None, f"input_player{user}_device_reservation_type") or "0").strip('"') != "0":
                warnings.append(f"retroarch: player {user} has a reserved device; RetroArch moves players to their "
                                f"reserved pads on connect, over the joypad ports we write")
                break
        folder = Path(config_root) / "config" / desc["core"]
        for override in sorted(folder.glob("*.cfg")) if folder.is_dir() else []:
            if _PORT_LINE.search(override.read_text(encoding="utf-8", errors="replace")):
                warnings.append(f"retroarch: {override.relative_to(config_root)} sets joypad ports; an override "
                                f"beats retroarch.cfg, so its players keep the pads it names")
        return warnings


def saved_on_exit(config_root: Path, rel: str, written: dict) -> bool:
    """Is the remap map-helper created, last written with `written` ((section, key) -> value), now only RetroArch's
    own save of it? Then it's still ours: apply keeps it `created` and restore deletes it.

    RetroArch saves the loaded remap when content closes or it quits, and only when remap_save_on_exit is on
    (input_remapping_deinit, input/input_driver.c L16905-16919, called from runloop.c L5675 and retroarch.c L10550;
    default true, config.def.h L736). input_remapping_save_file (configuration.c L10496-10699) writes a new file from
    memory: input_libretro_device_pN for every port below input_max_users (L10657), the remap keys that aren't
    identity (identity ones are left out, unmapped ones are -1 or left out, L10589-10600, L10628-10639) and the turbo
    settings. All at RetroArch eb7335f. So its save of our file has the device line, and every remap key in it is one
    we wrote, with our value; some of ours may be gone (seen on a Deck: player 2's lines, docs/13). EmuDeck's ABXY
    toggle renames its own <core>.rmp.disabled over the file instead (emuDeckRetroArch.sh @ dddb302 L363-374): four
    input_player1_btn_* lines and no device line (tests/fixtures/retroarch). A Quick Menu edit saved on quit puts a
    value of the user's in, which makes the file theirs, as does a save made by hand with remap_save_on_exit off.

    A core options file (.opt) has its own test, options_flushed."""
    if rel.endswith(".opt"):
        return options_flushed(config_root, rel, written)
    root = Path(config_root)
    cfg = root / "retroarch.cfg"
    settings = IniDocument.parse(cfg.read_text(encoding="utf-8", errors="replace")).index() if cfg.is_file() else {}
    if settings.get((None, "remap_save_on_exit"), "true").strip('"') == "false":
        return False
    try:
        saved = IniDocument.parse((root / rel).read_text(encoding="utf-8")).index()
    except (OSError, UnicodeDecodeError):
        return False
    if (None, "input_libretro_device_p1") not in saved:
        return False
    value = lambda v: v.strip().strip('"')
    return all(key in written and value(written[key]) == value(v)
               for key, v in saved.items() if key[0] is None and _REMAP_KEY.match(key[1]))


def options_flushed(config_root: Path, rel: str, written: dict) -> bool:
    """Is the options file map-helper created, last written with `written`, now only RetroArch's flush of it?

    When content closes, runloop_deinit_core_options (runloop.c L1033-1080 @ v1.22.2) reads the options file it
    loaded, sets every option of the core in it (core_option_manager_flush, core_option_manager.c L1890-1903) and
    writes it back sorted as `key = "value"` lines, keeping keys it doesn't know, and only if a value changed
    (config_file_write, libretro-common/file/config_file.c L1401-1468). So its flush keeps every option we wrote
    with our value; a Quick Menu change to one of ours makes the file the user's."""
    try:
        saved = IniDocument.parse((Path(config_root) / rel).read_text(encoding="utf-8")).index()
    except (OSError, UnicodeDecodeError):
        return False
    value = lambda v: v.strip().strip('"')
    return all(key in saved and value(saved[key]) == value(v) for key, v in written.items())
