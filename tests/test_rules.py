"""map-helper rules: the edits behind the plugin's "Change button", "Back to default", resets and rules list."""

import json
import os
import shutil
import unittest
from pathlib import Path

from tests.helpers import REPO
from tests.test_show import DEVICES, FIXTURES, OCARINA, Base, row, run_cli
from maphelper import rules, show
from maphelper.store import load_sources

LAYOUTS = "10-any.n64.layouts.json"
PAKS = "11-any.n64.stick-paks.json"


class RulesBase(Base):
    """The owner's Deck: N64 layouts and paks parked in rules-off/, rules/ empty, Ocarina launched last."""

    def setUp(self):
        super().setUp()
        self.on, self.off = self.tmp / "rules", self.tmp / "rules-off"
        self.off.mkdir()
        for name in (LAYOUTS, PAKS):
            shutil.copy(REPO / "examples" / name, self.off)
        launch = {"mode": "es-de", "emulator": "retroarch", "core": "mupen64plus_next", "system": "n64",
                  "game": OCARINA, "ms": 0, "outcome": "no-changes", "detail": ""}
        show.write_last(self.state, show.assemble(launch, {}))

    def rules(self, *argv, code=0) -> dict:
        action, extra = argv[0], []
        if action in ("set", "unset", "edit"):
            extra = [*self.probe(), "--state-dir", str(self.state),
                     "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt")]
        got, out = run_cli(["rules", *argv, "--rules-dir", str(self.on), "--off-dir", str(self.off), "--json", *extra])
        self.assertEqual(got, code, out)
        return json.loads(out)

    def edit(self, ops, *argv, code=0) -> dict:
        return self.rules("edit", "--ops", json.dumps(ops), *argv, code=code)

    def files(self) -> dict:
        return {str(p.relative_to(self.tmp)): p.read_text(encoding="utf-8")
                for p in sorted(self.tmp.glob("rules*/**/*.json"))}

    def loaded(self) -> dict:
        """What mh-run would load: rule id -> enabled."""
        return {r.id: r.enabled for r in load_sources([(self.on, "user")]).rules}

    def map_of(self, player=3) -> dict:
        """input -> labels it drives, for one player of a fresh show with the current rules."""
        code, out = run_cli(["show", "--emulator", "retroarch", "--core", "mupen64plus_next", "--system", "n64",
                             "--game", OCARINA, "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt"),
                             "--rules", str(self.on), *self.probe(), "--state-dir", str(self.state), "--json"])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        return {r["input"]: [d["label"] for d in r["drives"]] for r in doc["players"][player - 1]["inputs"]}


SYSTEM_ANY = {"controller": {"level": "any"}, "content": {"level": "system", "system": "n64"}}


def put(target, physical, **where):
    return {"op": "set", "target": f"n64.standard.{target}", "source": {"input": physical}, **where}


class ListTest(RulesBase):
    def test_parked_rules_are_listed_off(self):
        listed = {r["id"]: r for r in self.rules("list")["rules"]}
        self.assertEqual(len(listed), 8)
        self.assertFalse(any(r["on"] for r in listed.values()))
        self.assertTrue(all(r["parked"] for r in listed.values()))
        layout = listed["user.any.n64.layout-live-faces"]
        self.assertEqual(layout["scope"], "all Nintendo 64 games, any pad")
        self.assertEqual([(b["label"], b["input"]) for b in layout["bindings"]], [("C▼", "face_east"), ("C◀", "face_north")])
        self.assertEqual(listed["user.any.n64.perfect-dark.memory-pak"]["scope"], "only Perfect Dark (USA) (Rev 1), any pad")
        self.assertEqual(listed["user.any.n64.stick-rumble"]["options"], 2)

    def test_an_invalid_file_is_reported_and_left_alone(self):
        self.on.mkdir()
        (self.on / "broken.json").write_text('{"id": "x"}', encoding="utf-8")
        out = self.rules("list")
        self.assertEqual([p["file"] for p in out["problems"]], ["broken.json"])
        self.assertEqual((self.on / "broken.json").read_text(encoding="utf-8"), '{"id": "x"}')

    def test_targets(self):
        out = self.rules("targets", "--system", "n64")["targets"]
        self.assertEqual(out[7], {"target": "n64.standard.c_down", "label": "C▼", "kind": "button"})
        self.assertEqual(out[-1]["kind"], "axis")


class OnOffTest(RulesBase):
    def test_turning_on_a_parked_rule_moves_its_file_and_keeps_the_others_off(self):
        out = self.rules("enable", "user.any.n64.layout-live-faces")
        self.assertEqual(out["warnings"], [])
        self.assertFalse((self.off / LAYOUTS).exists())
        self.assertEqual(self.loaded(), {"user.any.n64.layout-live-faces": True, "user.any.n64.layout-face-c": False,
                                         "user.any.n64.layout-independent-c": False})
        self.assertEqual(self.map_of()["face_east"], ["C▼"])
        # The bundle keeps its notes and $schema: only enabled changed.
        doc = json.loads((self.on / LAYOUTS).read_text(encoding="utf-8"))
        self.assertIn("C-button chord", doc["rules"][0]["notes"])

    def test_two_layouts_on_at_once_warn(self):
        self.rules("enable", "user.any.n64.layout-live-faces")
        out = self.rules("enable", "user.any.n64.layout-face-c")
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("N64 layout 1", out["warnings"][0])
        listed = {r["id"]: r for r in self.rules("list")["rules"]}
        self.assertTrue(listed["user.any.n64.layout-face-c"]["clashes"])

    def test_off_then_on_again(self):
        self.rules("enable", "user.any.n64.stick-rumble")
        self.rules("disable", "user.any.n64.stick-rumble")
        self.assertFalse(self.loaded()["user.any.n64.stick-rumble"])
        self.rules("enable", "user.any.n64.stick-rumble")
        self.assertTrue(self.loaded()["user.any.n64.stick-rumble"])

    def test_delete(self):
        self.rules("delete", "user.any.n64.layout-face-c")
        ids = [r["id"] for r in self.rules("list")["rules"]]
        self.assertNotIn("user.any.n64.layout-face-c", ids)
        self.assertEqual(len(ids), 7)
        self.rules("delete", "user.any.n64.layout-live-faces", "user.any.n64.layout-independent-c")
        self.assertFalse((self.off / LAYOUTS).exists())      # the last rule in a file takes the file with it

    def test_reset_turns_off_and_enable_undoes_it(self):
        self.rules("enable", "user.any.n64.layout-live-faces", "user.any.n64.stick-rumble",
                   "user.any.n64.perfect-dark.memory-pak")
        game = self.rules("reset", "--system", "n64", "--game", "Perfect Dark (USA) (Rev 1)")
        self.assertEqual(game["rules"], ["user.any.n64.perfect-dark.memory-pak"])
        dry = self.rules("reset", "--system", "n64", "--dry-run")
        self.assertEqual(dry["labels"][0], "N64 layout 1: the core's layout, with the dead face buttons on C-down and C-left")
        self.assertTrue(self.loaded()["user.any.n64.layout-live-faces"])
        out = self.rules("reset", "--system", "n64")
        self.assertEqual(sorted(out["rules"]), ["user.any.n64.layout-live-faces", "user.any.n64.stick-rumble"])
        self.assertFalse(any(self.loaded().values()))
        self.rules("enable", *out["rules"])
        self.assertTrue(self.loaded()["user.any.n64.layout-live-faces"])


class EditTest(RulesBase):
    def test_change_button_for_all_games_any_pad(self):
        before = self.files()
        out = self.edit([put("c_down", "face_north", scope=SYSTEM_ANY)])
        self.assertEqual(out["rules"], ["edit.any.n64.all"])
        rule = json.loads((self.on / "edit.any.n64.all.json").read_text(encoding="utf-8"))
        self.assertEqual(rule["label"], rules.EDIT_LABEL)
        self.assertEqual(rule["bindings"], {"n64.standard.c_down": {"input": "face_north"}})
        # Every pad's △/X/Y now gives C▼ (four players; each change listed once per player).
        self.assertEqual({(c["player"], c["input"], tuple(c["after"])) for c in out["changes"]},
                         {(n, "face_north", ("C▼",)) for n in (1, 2, 3, 4)})
        self.assertEqual(self.map_of()["face_north"], ["C▼"])
        self.assertIsNone(out["preview_error"])
        # Undo takes the binding out, and the empty edit rule goes with it.
        undone = self.edit(out["undo"])
        self.assertEqual({(c["input"], tuple(c["after"])) for c in undone["changes"]}, {("face_north", ())})
        self.assertEqual(self.files(), before)

    def test_a_dry_run_changes_nothing_on_disk(self):
        before = self.files()
        out = self.edit([put("c_down", "face_north", scope=SYSTEM_ANY)], "--dry-run")
        self.assertTrue(out["dry_run"])
        self.assertEqual(len(out["changes"]), 4)
        self.assertEqual(self.files(), before)
        self.assertFalse(self.on.exists())

    def test_a_swap_is_one_edit(self):
        self.rules("enable", "user.any.n64.layout-live-faces")
        # Layout 1 has C▼ on ○. Swap C▼ (○) with A (✕) for this game only.
        game = {"controller": {"level": "any"}, "content": {"level": "game", "system": "n64", "game_id": OCARINA}}
        out = self.edit([put("c_down", "face_south", scope=game), put("a", "face_east", scope=game)])
        rule_id = out["rules"][0]
        self.assertRegex(rule_id, r"^edit\.any\.n64\.game-legend-of-zelda-the-ocarina-of-time-usa-[0-9a-f]{6}$")
        dualsense = self.map_of()
        self.assertEqual((dualsense["face_south"], dualsense["face_east"]), (["C▼"], ["A"]))
        listed = {r["id"]: r for r in self.rules("list")["rules"]}
        self.assertEqual(listed[rule_id]["scope"], f"only {OCARINA}, any pad")
        self.edit(out["undo"])
        self.assertEqual(self.map_of()["face_east"], ["C▼"])
        self.assertFalse((self.on / f"{rule_id}.json").exists())

    def test_a_rule_with_the_same_scope_is_changed_in_place(self):
        self.rules("enable", "user.any.n64.layout-live-faces")
        out = self.edit([put("c_down", "face_west", scope=SYSTEM_ANY)])
        self.assertEqual(out["rules"], ["user.any.n64.layout-live-faces"])
        self.assertFalse((self.on / "edit.any.n64.all.json").exists())
        self.assertEqual(self.map_of()["face_west"][-1], "C▼")
        self.assertEqual(out["undo"], [{"op": "set", "target": "n64.standard.c_down", "source": {"input": "face_east"},
                                        "rule": "user.any.n64.layout-live-faces"}])
        # A target that rule doesn't set goes into the scope's edit rule.
        out = self.edit([put("z", "r1", scope=SYSTEM_ANY)])
        self.assertEqual(out["rules"], ["edit.any.n64.all"])

    def test_back_to_default_and_undo(self):
        self.rules("enable", "user.any.n64.layout-live-faces")
        out = self.edit([{"op": "unset", "target": "n64.standard.c_down", "rule": "user.any.n64.layout-live-faces"}])
        self.assertEqual({(c["input"], tuple(c["before"]), tuple(c["after"])) for c in out["changes"]},
                         {("face_east", ("C▼",), ())})
        self.assertEqual(self.map_of()["face_east"], [])
        doc = json.loads((self.on / LAYOUTS).read_text(encoding="utf-8"))["rules"][0]
        self.assertEqual(doc["bindings"], {"n64.standard.c_left": {"input": "face_north"}})
        self.edit(out["undo"])
        self.assertEqual(self.map_of()["face_east"], ["C▼"])

    def test_one_pad_names_the_player_and_never_shows_the_device(self):
        one = {"controller": {"level": "device", "player": 3, "model": "sony.dualsense"},
               "content": {"level": "system", "system": "n64"}}
        code, text = run_cli(["rules", "edit", "--ops", json.dumps([put("z", "r1", scope=one)]), "--json",
                              "--rules-dir", str(self.on), "--off-dir", str(self.off), *self.probe(),
                              "--state-dir", str(self.state), "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt")])
        self.assertEqual(code, 0, text)
        out = json.loads(text)
        self.assertEqual(out["rules"], ["edit.pad-1.n64.all"])
        self.assertEqual({c["player"] for c in out["changes"]}, {3})        # only the DualSense
        self.assert_no_device_ids(text)
        self.assert_no_device_ids(json.dumps(self.rules("list")))
        rule = json.loads((self.on / "edit.pad-1.n64.all.json").read_text(encoding="utf-8"))
        self.assertEqual(rule["applies_to"]["controller"]["level"], "device")
        self.assertTrue(rule["applies_to"]["controller"]["value"])
        # The same pad again reuses its rule; undoing keeps the (now empty) rule, whose undo can't name the device.
        again = self.edit([put("l", "r2", scope=one)])
        self.assertEqual(again["rules"], ["edit.pad-1.n64.all"])
        self.edit(again["undo"])
        self.edit(out["undo"])
        self.assertTrue((self.on / "edit.pad-1.n64.all.json").exists())

    def test_one_pad_refuses_a_different_controller(self):
        wrong = {"controller": {"level": "device", "player": 3, "model": "nintendo.switch-pro"},
                 "content": {"level": "system", "system": "n64"}}
        out = self.edit([put("z", "r1", scope=wrong)], code=2)
        self.assertIn("different controller", out["error"])
        self.assertFalse(self.on.exists())

    def test_family_scope(self):
        family = {"controller": {"level": "family", "value": "sony.dualsense"},
                  "content": {"level": "system", "system": "n64"}}
        out = self.edit([put("z", "r1", scope=family)])
        self.assertEqual(out["rules"], ["edit.family-sony-dualsense.n64.all"])
        self.assertEqual({c["player"] for c in out["changes"]}, {3})

    def test_set_and_unset_from_the_command_line(self):
        code, text = run_cli(["rules", "set", "--target", "n64.standard.c_down", "--input", "face_north",
                              "--rules-dir", str(self.on), "--off-dir", str(self.off), *self.probe(),
                              "--state-dir", str(self.state), "--config-root", str(FIXTURES / "retroarch" / "dualsense-bt")])
        self.assertEqual(code, 0)
        self.assertIn("changed edit.any.n64.all", text)
        self.assertIn("player 3 △: - -> C▼", text)
        self.rules("unset", "--rule", "edit.any.n64.all", "--target", "n64.standard.c_down")
        self.assertFalse((self.on / "edit.any.n64.all.json").exists())

    def test_without_a_launch_the_edit_is_made_without_a_preview(self):
        (self.state / show.LAST).unlink()
        out = self.edit([put("c_down", "face_north", scope=SYSTEM_ANY)])
        self.assertIsNone(out["changes"])
        self.assertIn("no game has been launched", out["preview_error"])
        self.assertTrue((self.on / "edit.any.n64.all.json").exists())


class RefuseTest(RulesBase):
    def refused(self, ops, words):
        before = self.files()
        out = self.edit(ops, code=2)
        self.assertIn(words, out["error"])
        self.assertEqual(self.files(), before)

    def test_bad_ops(self):
        self.refused([put("c_dwn", "face_north", scope=SYSTEM_ANY)], "unknown console input")
        self.refused([put("c_down", "face_northish", scope=SYSTEM_ANY)], "physical input")
        self.refused([put("c_down", "face_north")], "either a rule or a scope")
        self.refused([put("c_down", "face_north", scope={"controller": {"level": "any"},
                                                          "content": {"level": "system", "system": "gc"}})],
                     "this system (n64)")
        self.refused([put("c_down", "face_north", rule="../../evil")], "bad rule id")
        self.refused([put("c_down", "face_north", scope={"controller": {"level": "device", "value": "mac:x"},
                                                          "content": SYSTEM_ANY["content"]})],
                     "names the player")
        self.refused([{"op": "unset", "target": "n64.standard.z", "rule": "user.any.n64.layout-face-c"}],
                     "doesn't set")
        self.refused([], "non-empty")

    def test_never_writes_through_a_symlink_or_outside_the_folders(self):
        self.on.mkdir()
        outside = self.tmp / "outside.json"
        outside.write_text(json.dumps({"schema_version": 1, "id": "edit.any.n64.all", "applies_to": SYSTEM_ANY}),
                           encoding="utf-8")
        os.symlink(outside, self.on / "edit.any.n64.all.json")
        out = self.edit([put("c_down", "face_north", scope=SYSTEM_ANY)], code=2)
        self.assertIn("not a plain .json rule file", out["error"])
        self.assertNotIn("bindings", json.loads(outside.read_text(encoding="utf-8")))
        book = rules.Book(self.on, self.off)
        with self.assertRaises(rules.RuleError):
            book._check(self.tmp / "elsewhere" / "x.json")

    def test_an_invalid_result_is_not_written(self):
        self.rules("enable", "user.any.n64.layout-live-faces")
        before = self.files()
        book = rules.Book(self.on, self.off)
        entry = book.get("user.any.n64.layout-live-faces")
        entry.doc["applies_to"]["content"]["level"] = "everywhere"
        with self.assertRaises(rules.RuleError):
            book.save(entry.path)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
