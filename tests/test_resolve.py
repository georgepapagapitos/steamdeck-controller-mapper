import unittest

from tests.helpers import REPO
from maphelper.devices import ControllerDB
from maphelper.model import ContentScope, Controller, ControllerScope, Rule, Target
from maphelper.resolve import explain, resolve
from maphelper.store import load_json, load_layouts, load_rules

LAYOUTS = load_layouts(REPO / "data" / "layouts")
BLUE_DS4 = Controller(
    device_ids=("mac:aa:bb:cc:dd:ee:ff",), model="sony.ds4.v2", family="sony.dualshock4",
    brand="sony", style="playstation",
    capabilities=frozenset({"gyro", "accel", "touchpad", "touchpad_click", "rumble"}))


def rule(id, ctrl=("any", None), content=("system", "gc"), source="user", bindings=None, **kw):
    level, value = ctrl
    c_level, c_value = content
    content_scope = {
        "global": ContentScope("global"),
        "system": ContentScope("system", system=c_value),
        "game": ContentScope("game", system="gc", game_id=c_value),
        "emulator": ContentScope("emulator", emulator=c_value),
    }[c_level]
    return Rule(id=id, controller=ControllerScope(level, value), content=content_scope,
                source=source, bindings=bindings or {}, **kw)


class WorkedExampleTest(unittest.TestCase):
    """The worked resolution in examples/README.md."""

    def setUp(self):
        self.rules = load_rules(REPO / "examples", "user").rules
        self.result = resolve(self.rules, BLUE_DS4, Target("gc", "dolphin", "GALE01"), LAYOUTS)

    def winner(self, key):
        return self.result.bindings[key].rule_id

    def test_matching_rules(self):
        self.assertEqual(sorted(self.result.matched_rules), [
            "user.any.gc.gale01", "user.any.global.hotkeys",
            "user.device-blue-ds4.global.deadzone", "user.family-ds4.gc"])

    def test_family_rule_sets_a(self):
        self.assertEqual(self.winner("gc.standard.a"), "user.family-ds4.gc")

    def test_game_rule_beats_family_rule(self):
        z = self.result.bindings["gc.standard.z"]
        self.assertEqual(z.rule_id, "user.any.gc.gale01")
        self.assertEqual(z.value, {"input": "l1"})
        self.assertEqual(z.shadowed, ["user.family-ds4.gc"])

    def test_options_and_hotkeys(self):
        self.assertEqual(self.result.options["deadzones.ls"].rule_id, "user.device-blue-ds4.global.deadzone")
        self.assertEqual(self.result.options["rumble.enabled"].value, True)
        self.assertEqual(self.winner("hotkey.menu"), "user.any.global.hotkeys")

    def test_wii_rule_does_not_leak_into_gc(self):
        self.assertFalse(any(k.startswith("wii.") for k in self.result.bindings))

    def test_explain_mentions_winners(self):
        text = explain(self.result)
        self.assertIn("user.any.gc.gale01", text)
        self.assertIn("shadows: user.family-ds4.gc", text)


class PrecedenceTest(unittest.TestCase):
    def resolve(self, rules, controller=BLUE_DS4, target=Target("gc", "dolphin")):
        return resolve(rules, controller, target, LAYOUTS)

    def test_user_beats_shipped_regardless_of_scope(self):
        rules = [rule("shipped.model", ("model", "sony.ds4.v2"), source="shipped",
                      bindings={"gc.standard.a": {"input": "face_east"}}),
                 rule("user.any", bindings={"gc.standard.a": {"input": "face_south"}})]
        self.assertEqual(self.resolve(rules).bindings["gc.standard.a"].rule_id, "user.any")

    def test_more_specific_controller_wins_at_same_content_scope(self):
        rules = [rule("user.style", ("style", "playstation"), bindings={"gc.standard.a": {"input": "face_east"}}),
                 rule("user.family", ("family", "sony.dualshock4"), bindings={"gc.standard.a": {"input": "face_south"}}),
                 rule("user.brand", ("brand", "sony"), bindings={"gc.standard.a": {"input": "face_west"}})]
        self.assertEqual(self.resolve(rules).bindings["gc.standard.a"].rule_id, "user.family")

    def test_explicit_priority_beats_game_scope(self):
        rules = [rule("user.game", content=("game", "GALE01"), bindings={"gc.standard.z": {"input": "l1"}}),
                 rule("user.family", ("family", "sony.dualshock4"), explicit_priority=1,
                      bindings={"gc.standard.z": {"input": "r1"}})]
        result = self.resolve(rules, target=Target("gc", "dolphin", "GALE01"))
        self.assertEqual(result.bindings["gc.standard.z"].rule_id, "user.family")

    def test_merge_is_per_key(self):
        rules = [rule("user.family", ("family", "sony.dualshock4"), bindings={
                     "gc.standard.a": {"input": "face_south"}, "gc.standard.b": {"input": "face_west"}}),
                 rule("user.device", ("device", "mac:aa:bb:cc:dd:ee:ff"), bindings={
                     "gc.standard.b": {"input": "face_east"}})]
        result = self.resolve(rules)
        self.assertEqual(result.bindings["gc.standard.a"].rule_id, "user.family")
        self.assertEqual(result.bindings["gc.standard.b"].rule_id, "user.device")

    def test_meta_binding_expands_and_loses_to_direct_binding(self):
        rules = [rule("user.meta", content=("system", "gc"), bindings={"meta.confirm": {"input": "face_east"},
                                                                     "meta.cancel": {"input": "face_south"}}),
                 rule("user.direct", content=("system", "gc"), bindings={"gc.standard.b": {"input": "face_west"}})]
        result = self.resolve(rules)
        self.assertEqual(result.bindings["gc.standard.a"].via_meta, "meta.confirm")
        self.assertEqual(result.bindings["gc.standard.b"].rule_id, "user.direct")

    def test_brand_rule_needs_a_claim_for_impersonating_pads(self):
        db = ControllerDB(load_json(REPO / "data" / "controllers.json"))
        rules = [rule("user.8bitdo", ("brand", "8bitdo"), bindings={"gc.standard.a": {"input": "face_east"}})]
        unclaimed = db.classify(("usb:1",), "045e:028e", "Xbox 360 Controller")
        self.assertEqual(self.resolve(rules, unclaimed).bindings, {})
        claimed = db.classify(("usb:1",), "045e:028e", claimed_model="8bitdo.pro2.dinput")
        self.assertIn("gc.standard.a", self.resolve(rules, claimed).bindings)

    def test_missing_capability_skips_rule_with_warning(self):
        no_gyro = Controller(device_ids=("x",), family="8bitdo.sn30pro", brand="8bitdo", style="nintendo")
        rules = [rule("user.gyro", requires=("gyro",), bindings={"gc.standard.a": {"input": "face_south"}}),
                 rule("user.paddle", bindings={"gc.standard.z": {"input": "paddle1"}})]
        result = self.resolve(rules, no_gyro)
        self.assertEqual(result.bindings, {})
        self.assertEqual(len(result.warnings), 2)

    def test_duplicate_source_warning(self):
        rules = [rule("user.dup", bindings={"gc.standard.a": {"input": "face_south"},
                                            "gc.standard.b": {"input": "face_south"}})]
        self.assertTrue(any("face_south" in w for w in self.resolve(rules).warnings))

    def test_allowed_shared_source_has_no_warning(self):
        rules = [rule("user.trig", bindings={"gc.standard.l_digital": {"input": "l2"},
                                             "gc.standard.l_analog": {"input": "l2"}})]
        self.assertEqual(self.resolve(rules).warnings, [])

    def test_disabled_rule_is_ignored(self):
        rules = [rule("user.off", enabled=False, bindings={"gc.standard.a": {"input": "face_east"}})]
        self.assertEqual(self.resolve(rules).bindings, {})

    def test_deterministic_regardless_of_rule_order(self):
        rules = [rule(f"user.r{i}", bindings={"gc.standard.a": {"input": "face_south"}}) for i in range(5)]
        a = self.resolve(rules).bindings["gc.standard.a"].rule_id
        b = self.resolve(list(reversed(rules))).bindings["gc.standard.a"].rule_id
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
