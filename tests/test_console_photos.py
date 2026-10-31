"""The console controller photos the plugin ships (decky/assets/consoles): every one free to ship, its JSON
matching its image, and every traced spot naming a real input of its layout, inside the picture."""

import json
import struct
import unittest

from tests.helpers import REPO

FOLDER = REPO / "decky" / "assets" / "consoles"
LICENCES = {"Public domain", "CC0"}


def image_size(path) -> tuple:
    """(width, height) of a PNG or JPEG, read from its header (stdlib only, so it runs on the Mac and Windows)."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):   # a start-of-frame segment
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width, height
            i += 2 + length
    raise ValueError(f"not a PNG or JPEG: {path.name}")


def layout_inputs(system: str, controller: str) -> set:
    """Every input name a layout's controller has (buttons, d-pad, axes), plus the d-pad as a whole."""
    pad = json.loads((REPO / "data" / "layouts" / f"{system}.json").read_text(encoding="utf-8"))["controllers"][controller]
    names = {"dpad", "up", "down", "left", "right"}
    for key in ("buttons", "dpad", "axes", "analog"):
        value = pad.get(key, [])
        names |= set(value if isinstance(value, list) else value.keys())
    return names


class ConsolePhotosTest(unittest.TestCase):
    def photos(self):
        found = sorted(FOLDER.glob("*.json"))
        self.assertGreaterEqual(len(found), 30)
        for path in found:
            yield path, json.loads(path.read_text(encoding="utf-8"))

    def test_free_to_ship_with_a_named_source(self):
        for path, doc in self.photos():
            with self.subTest(path.name):
                self.assertIn(doc["source"]["license"], LICENCES)
                self.assertTrue(doc["source"]["url"].startswith("https://commons.wikimedia.org/wiki/File:"))
                self.assertTrue(doc["source"]["author"])

    def test_json_matches_its_image(self):
        for path, doc in self.photos():
            with self.subTest(path.name):
                image = FOLDER / doc["file"]
                self.assertTrue(image.is_file())
                self.assertEqual(image_size(image), (doc["width"], doc["height"]))
                self.assertEqual(path.stem, doc["id"])
                self.assertIn(doc["id"], (doc["system"], f"{doc['system']}-{doc['controller']}"))

    def test_spots_name_real_inputs_inside_the_picture(self):
        for path, doc in self.photos():
            names = layout_inputs(doc["system"], doc["controller"])
            sticks = {n[:-2] for n in names if n.endswith(("_x", "_y"))}   # a stick's spot may be named for it
            with self.subTest(path.name):
                for key, spot in doc["spots"].items():
                    self.assertIn(len(spot), (3, 4, 5), key)
                    self.assertTrue(0 <= spot[0] <= doc["width"] and 0 <= spot[1] <= doc["height"], key)
                    self.assertTrue(key in names or key in sticks or key in ("lstick", "rstick", "stick"), key)
                hidden = doc.get("hidden", [])
                self.assertFalse(set(hidden) & set(doc["spots"]))
                for key, x in (doc.get("edge") or {}).items():
                    self.assertIn(key, hidden)
                    self.assertTrue(0 <= x <= 1)


if __name__ == "__main__":
    unittest.main()
