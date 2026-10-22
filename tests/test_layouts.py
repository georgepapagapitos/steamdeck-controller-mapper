import unittest

from tests.helpers import REPO
from maphelper.model import PHYSICAL_INPUTS
from maphelper.store import load_layouts

LAYOUTS = load_layouts(REPO / "data" / "layouts")


class LayoutsTest(unittest.TestCase):
    def test_every_layout_is_consistent(self):
        self.assertGreaterEqual(len(LAYOUTS), 28)
        for system, layout in LAYOUTS.items():
            with self.subTest(system=system):
                self.assertEqual(layout["schema_version"], 1)
                controllers = layout["controllers"]
                self.assertIn(layout["default_controller"], controllers)
                for ctype, inputs in layout["positional_default"].items():
                    self.assertIn(ctype, controllers)
                    declared = {i for group in ("buttons", "dpad", "analog")
                                for i in controllers[ctype].get(group, [])}
                    self.assertLessEqual(set(inputs), declared, f"{ctype}: undeclared inputs")
                    self.assertLessEqual(set(inputs.values()), PHYSICAL_INPUTS, f"{ctype}: unknown physical inputs")
                for alias, target in layout.get("meta", {}).items():
                    ctype, name = target.split(".", 1)
                    declared = {i for group in ("buttons", "dpad", "analog")
                                for i in controllers[ctype].get(group, [])}
                    self.assertIn(name, declared, f"meta.{alias}")


if __name__ == "__main__":
    unittest.main()
