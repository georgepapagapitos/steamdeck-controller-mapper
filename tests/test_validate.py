import json
import unittest

from tests.helpers import REPO
from maphelper.validate import validate_rule


def base(**overrides):
    doc = {
        "schema_version": 1,
        "id": "user.test",
        "applies_to": {"controller": {"level": "any"}, "content": {"level": "system", "system": "gc"}},
        "bindings": {"gc.standard.a": {"input": "face_south"}},
    }
    doc.update(overrides)
    return doc


class ValidateTest(unittest.TestCase):
    def test_examples_are_valid(self):
        for path in sorted((REPO / "examples").glob("*.json")):
            with self.subTest(path=path.name):
                self.assertEqual(validate_rule(json.loads(path.read_text())), [])

    def test_minimal_rule_is_valid(self):
        self.assertEqual(validate_rule(base()), [])

    def test_rejects_bad_cases(self):
        cases = {
            "unknown input": base(bindings={"gc.standard.a": {"input": "face_up"}}),
            "value with any": base(applies_to={"controller": {"level": "any", "value": "x"},
                                               "content": {"level": "global"}}),
            "missing value": base(applies_to={"controller": {"level": "family"},
                                              "content": {"level": "global"}}),
            "game without id": base(applies_to={"controller": {"level": "any"},
                                                "content": {"level": "game", "system": "gc"}}),
            "bad key": base(bindings={"a": {"input": "face_south"}}),
            "short chord": base(bindings={"hotkey.menu": {"chord": ["select"]}}),
            "bad id": base(id="User Rule"),
            "unknown top-level key": base(colour="blue"),
        }
        for name, doc in cases.items():
            with self.subTest(name):
                self.assertNotEqual(validate_rule(doc), [])


if __name__ == "__main__":
    unittest.main()
