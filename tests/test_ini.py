import unittest

from tests.helpers import REPO
from maphelper.formats.ini import IniDocument

SAMPLE = """; comment kept
[GCPad1]
Device = SDL/0/Steam Virtual Gamepad
Buttons/A = `Button S`
Buttons/B = `Button W`

[GCPad2]
Device = SDL/1/Steam Virtual Gamepad
"""


class IniTest(unittest.TestCase):
    def test_round_trip_sample(self):
        self.assertEqual(IniDocument.parse(SAMPLE).serialize(), SAMPLE)

    def test_round_trip_crlf_and_no_trailing_newline(self):
        text = "[A]\r\nx = 1\r\ny=2"
        self.assertEqual(IniDocument.parse(text).serialize(), text)

    def test_round_trip_fixtures(self):
        fixtures = REPO / "tests" / "fixtures"
        for path in sorted(fixtures.rglob("*.ini")) if fixtures.exists() else []:
            with self.subTest(path=str(path.relative_to(fixtures))):
                text = path.read_text(encoding="utf-8", errors="surrogateescape")
                self.assertEqual(IniDocument.parse(text).serialize(), text)

    def test_get_and_items(self):
        doc = IniDocument.parse(SAMPLE)
        self.assertEqual(doc.get("GCPad1", "Buttons/A"), "`Button S`")
        self.assertIsNone(doc.get("GCPad1", "Buttons/Z"))
        self.assertEqual(doc.sections(), ["GCPad1", "GCPad2"])
        self.assertEqual(dict(doc.items("GCPad2")), {"Device": "SDL/1/Steam Virtual Gamepad"})

    def test_set_existing_changes_only_that_line(self):
        doc = IniDocument.parse(SAMPLE)
        doc.set("GCPad1", "Buttons/A", "`Button E`")
        self.assertEqual(doc.serialize(), SAMPLE.replace("Buttons/A = `Button S`", "Buttons/A = `Button E`"))

    def test_set_new_key_goes_at_end_of_section_before_blank_line(self):
        doc = IniDocument.parse(SAMPLE)
        doc.set("GCPad1", "Buttons/Z", "`Shoulder R`")
        self.assertIn("Buttons/B = `Button W`\nButtons/Z = `Shoulder R`\n\n[GCPad2]", doc.serialize())

    def test_set_new_section_appends(self):
        doc = IniDocument.parse(SAMPLE)
        doc.set("GCPad3", "Device", "SDL/2/Steam Virtual Gamepad")
        self.assertTrue(doc.serialize().endswith("\n[GCPad3]\nDevice = SDL/2/Steam Virtual Gamepad\n"))

    def test_remove(self):
        doc = IniDocument.parse(SAMPLE)
        self.assertTrue(doc.remove("GCPad1", "Buttons/B"))
        self.assertNotIn("Buttons/B", doc.serialize())
        self.assertFalse(doc.remove("GCPad1", "Buttons/B"))

    def test_same_key_in_other_section_untouched(self):
        doc = IniDocument.parse(SAMPLE)
        doc.set("GCPad2", "Device", "SDL/0/PS4 Controller")
        self.assertIn("[GCPad1]\nDevice = SDL/0/Steam Virtual Gamepad", doc.serialize())

    def test_only_real_line_breaks_split_lines(self):
        # str.splitlines() would cut these values in two and write them back as two lines.
        text = "[A]\nName = a\x0cb\nOther = c d\nKey = 1\n"
        doc = IniDocument.parse(text)
        self.assertEqual(doc.serialize(), text)
        self.assertEqual(doc.get("A", "Name"), "a\x0cb")
        doc.set("A", "Key", "2")
        self.assertEqual(doc.serialize(), text.replace("Key = 1", "Key = 2"))

    def test_each_line_keeps_its_own_ending(self):
        text = "[A]\r\nX = 1\nY = 2\r\n"
        doc = IniDocument.parse(text)
        self.assertEqual(doc.serialize(), text)
        doc.set("A", "Y", "3")
        self.assertEqual(doc.serialize(), "[A]\r\nX = 1\nY = 3\r\n")

    def test_no_final_break_is_kept(self):
        doc = IniDocument.parse("[A]\nX = 1")
        doc.set("A", "Y", "2")
        self.assertEqual(doc.serialize(), "[A]\nX = 1\nY = 2")
        doc.remove("A", "Y")
        self.assertEqual(doc.serialize(), "[A]\nX = 1")
        empty = IniDocument.parse("")
        empty.set("B", "Z", "9")
        self.assertEqual(empty.serialize(), "[B]\nZ = 9\n")


class WriterGuardTest(unittest.TestCase):
    def test_refuses_an_edit_that_strays_outside_managed_keys(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from maphelper.writer import Patch, apply_patches

        root = Path(tempfile.mkdtemp())
        (root / "GCPadNew.ini").write_text(SAMPLE, encoding="utf-8")
        managed = {"GCPadNew.ini": {"sections": "GCPad{n}", "keys": ["Buttons/*"]}}
        patch = Patch("GCPadNew.ini", "GCPad1", "Buttons/A", "`Button E`")
        real_set = IniDocument.set

        def buggy_set(doc, section, key, value):  # an editor bug that also rewrites an unrelated line
            real_set(doc, section, key, value)
            doc.lines[0] = "; comment changed"

        with mock.patch.object(IniDocument, "set", buggy_set):
            with self.assertRaises(RuntimeError):
                apply_patches(root, [patch], managed)
        self.assertEqual((root / "GCPadNew.ini").read_text(encoding="utf-8"), SAMPLE)
        self.assertEqual(apply_patches(root, [patch], managed).changed_files, ["GCPadNew.ini"])


if __name__ == "__main__":
    unittest.main()
