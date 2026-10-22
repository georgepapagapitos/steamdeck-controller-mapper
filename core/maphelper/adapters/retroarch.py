"""RetroArch adapter: per-player pad remaps in a core's own .rmp (prototype). See docs/adapters/retroarch.md.

All RetroArch facts come from data/adapters/retroarch/ (retropad.json, hotkeys.json and one descriptor per core).
Hotkeys go into retroarch.cfg, and only when some rule sets one.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from ..resolve import Resolution
from ..store import load_json
from ..writer import Patch
from .dolphin import Rendered

DATA = Path(__file__).resolve().parents[3] / "data" / "adapters" / "retroarch"
REMAP_DIR = "config/remaps"   # input_remapping_directory's default under the config root; EmuDeck keeps it
SUFFIXES = ("_btn", "_axis")


class RetroArchAdapter:
    id = "retroarch"

    def __init__(self, retropad: Optional[dict] = None, cores: Optional[dict] = None, hotkeys: Optional[dict] = None):
        self.pad = retropad or load_json(DATA / "retropad.json")
        self.hotkeys = hotkeys or load_json(DATA / "hotkeys.json")
        self.cores = cores or {f.stem: load_json(f) for f in sorted((DATA / "cores").glob("*.json"))}
        self.ids = {**self.pad["retropad_ids"], **self.pad["analog_half_axis_ids"]}

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

    def managed_keys(self, desc: dict) -> dict:
        hk = self.hotkeys
        bases = [hk["enable"], *hk["targets"].values()]
        return {self.remap_file(desc): {"keys": ["input_player[1-9]_btn_*", "input_player[1-9]_stk_*"]},
                hk["file"]: {"keys": [f"input_{b}{s}" for b in bases for s in SUFFIXES]}}

    # -- render ----------------------------------------------------------------

    def render(self, players: dict[int, Resolution], desc: dict,
               current: Optional[Callable[[str, Optional[str], str], Optional[str]]] = None) -> Rendered:
        """players: RetroArch user number -> resolution. current(file, section, key) reads the live value."""
        current = current or (lambda *_: None)
        out, file = Rendered(), self.remap_file(desc)
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

    @staticmethod
    def _key(user: int, name: str) -> str:
        """B -> input_player1_btn_b, LEFT_X+ -> input_player1_stk_l_x+ (input_remapping_save_file)."""
        if "_" in name and name[-1] in "+-":
            side, axis = name[:-1].split("_")
            return f"input_player{user}_stk_{side[0].lower()}_{axis.lower()}{name[-1]}"
        return f"input_player{user}_btn_{name.lower()}"

    # -- checks ----------------------------------------------------------------

    def check(self, config_root: Path, desc: dict,
              current: Callable[[str, Optional[str], str], Optional[str]]) -> list[str]:
        """Things that make RetroArch ignore the core-level remap we write."""
        warnings = []
        for key, why in (("auto_remaps_enable", "remap files aren't loaded at all"),
                         ("input_remap_binds_enable", "remaps are ignored")):
            if (current("retroarch.cfg", None, key) or "").strip('"') == "false":
                warnings.append(f"retroarch: {key} is false in retroarch.cfg, so {why}")
        if (current("retroarch.cfg", None, "input_remap_sort_by_controller_enable") or "").strip('"') == "true":
            warnings.append("retroarch: input_remap_sort_by_controller_enable is on; remaps are looked up per "
                            "controller name, so the core-level file we write isn't used")
        folder = Path(config_root) / REMAP_DIR / desc["core"]
        mine = Path(self.remap_file(desc)).name
        for shadow in sorted(folder.glob("*.rmp")) if folder.is_dir() else []:
            if shadow.name != mine:
                warnings.append(f"retroarch: {shadow.relative_to(config_root)} is a game or folder remap; when it "
                                f"matches, RetroArch loads it instead of {mine} (no layering)")
        return warnings
