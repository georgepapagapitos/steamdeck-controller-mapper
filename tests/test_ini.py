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


if __name__ == "__main__":
    unittest.main()
