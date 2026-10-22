"""RetroArch adapter: per-player pad remaps in a core's own .rmp (prototype). See docs/adapters/retroarch.md.

All RetroArch facts come from data/adapters/retroarch/ (retropad.json and one descriptor per core). Hotkeys in
retroarch.cfg are not rendered yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..resolve import Resolution
from ..store import load_json
from ..writer import Patch
from .dolphin import Rendered

DATA = Path(__file__).resolve().parents[3] / "data" / "adapters" / "retroarch"
REMAP_DIR = "config/remaps"   # input_remapping_directory's default under the config root; EmuDeck keeps it


class RetroArchAdapter:
    id = "retroarch"

    def __init__(self, retropad: Optional[dict] = None, cores: Optional[dict] = None):
        self.pad = retropad or load_json(DATA / "retropad.json")
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
        return {self.remap_file(desc): {"keys": ["input_player[1-9]_btn_*", "input_player[1-9]_stk_*"]}}

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
