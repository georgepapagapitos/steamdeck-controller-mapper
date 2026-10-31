"""Every RetroArch core descriptor (data/adapters/retroarch/cores) names its targets as the layouts do. A target
spelled differently from its layout (genesis.3button.a for genesis.three_button.a) is never matched by a rule and
is left out of the button map; that hid every Genesis button until 2026-10-31."""

import json
import unittest

from tests.helpers import REPO

# Inputs a core has that its console's layout doesn't list (they show in the map under their own name, and no rule
# can set them): turbo buttons, the DS microphone, extra arcade buttons, the Saturn 3D pad's mode switch, Wii tilt.
EXTRAS = {"turbo_a", "turbo_b", "turbo_l", "turbo_r", "microphone", "button9", "coin", "mode", "tilt_x", "tilt_y",
          "pressure"}
# Controller types a core offers that no layout has yet.
EXTRA_PADS = {"arcade.sf6", "wii.classic_pro", "wii.wiimote_sideways"}


def layout_names() -> dict:
    out = {}
    for path in (REPO / "data" / "layouts").glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for pad, spec in doc["controllers"].items():
            names = set()
            for key in ("buttons", "dpad", "axes", "analog"):
                value = spec.get(key, [])
                names |= set(value if isinstance(value, list) else value)
            out[f"{doc['system']}.{pad}"] = names
    return out


class CoreDescriptorTest(unittest.TestCase):
    def test_targets_match_the_layouts(self):
        layouts = layout_names()
        systems = {k.split(".")[0] for k in layouts}
        for path in sorted((REPO / "data" / "adapters" / "retroarch" / "cores").glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for target in doc["targets"]:
                system, pad, name = target.split(".")
                if system not in systems:
                    continue                                   # a console with no layout yet (Game Gear, Sega CD...)
                with self.subTest(core=path.stem, target=target):
                    key = f"{system}.{pad}"
                    if key in EXTRA_PADS:
                        continue
                    self.assertIn(key, layouts, f"{path.name}: no layout controller {key}")
                    self.assertTrue(name in layouts[key] or name in EXTRAS, f"{path.name}: {target} isn't in the layout")


    def test_standalone_tables_match_the_layouts(self):
        layouts = layout_names()
        for name in ("dolphin", "pcsx2", "duckstation"):
            doc = json.loads((REPO / "data" / "adapters" / f"{name}.json").read_text(encoding="utf-8"))
            for target in doc.get("targets", {}):
                if target.startswith(("hotkey.", "_")):
                    continue
                system, pad, input_name = target.split(".")
                with self.subTest(table=name, target=target):
                    self.assertIn(f"{system}.{pad}", layouts)
                    self.assertTrue(input_name in layouts[f"{system}.{pad}"] or input_name in EXTRAS)


if __name__ == "__main__":
    unittest.main()
