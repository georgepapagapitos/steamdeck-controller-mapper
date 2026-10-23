import contextlib
import hashlib
import io
import json
import os
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.helpers import REPO
from maphelper import cli, doctor
from maphelper.formats import vdf

RA_REAL = REPO / "tests" / "fixtures" / "retroarch" / "dualsense-bt"   # the owner's Deck, captured
GOLDEN = REPO / "tests" / "golden" / "doctor" / "retroarch-dualsense-bt.txt"
SNES9X = "config/remaps/Snes9x"

# Made-up shortcuts. Ids are built the way Steam-ROM-Manager builds them (crc32(exe + name) | 0x80000000).
ESDE = {"AppName": "ES-DE", "Exe": '"/home/deck/Applications/ES-DE.AppImage"', "StartDir": '"/home/deck/Applications/"'}
SRM_DOLPHIN = {"AppName": "Super Mario Sunshine", "Exe": '"/home/deck/Emulation/tools/launchers/dolphin-emu.sh"',
               "LaunchOptions": '-b -e "/run/media/sd/Emulation/roms/gc/Sunshine.rvz"'}
BROWSER = {"AppName": "Web Browser", "Exe": "flatpak", "LaunchOptions": "run org.mozilla.firefox"}


def shortcut_id(entry: dict) -> int:
    return zlib.crc32((entry["Exe"] + entry["AppName"]).encode("utf-8")) | 0x80000000


def binary_vdf(tree: dict) -> bytes:
    """Encode the way Steam writes shortcuts.vdf: 0x00 map, 0x01 string, 0x02 int32, 0x08 end of map."""
    out = b""
    for key, value in tree.items():
        name = key.encode("utf-8") + b"\x00"
        if isinstance(value, dict):
            out += b"\x00" + name + binary_vdf(value)
        elif isinstance(value, int):
            out += b"\x02" + name + struct.pack("<i", value)
        else:
            out += b"\x01" + name + value.encode("utf-8") + b"\x00"
    return out + b"\x08"


def signed(n: int) -> int:
    return n - (1 << 32) if n >= 1 << 31 else n


def tree_digest(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class VdfTest(unittest.TestCase):
    def test_text(self):
        tree = vdf.parse_text('// comment\n"Root"\n{\n\t"apps"\n\t{\n\t\t"10"\t\t{ "Key" "a \\"q\\" b" }\n\t}\n'
                              '\tbare value\n}\n')
        self.assertEqual(vdf.lookup(tree, "root", "APPS", "10", "key"), 'a "q" b')
        self.assertEqual(vdf.lookup(tree, "Root", "bare"), "value")
        self.assertIsNone(vdf.lookup(tree, "Root", "missing", "x"))

    def test_text_unbalanced(self):
        with self.assertRaises(vdf.VdfError):
            vdf.parse_text('"a" { "b" "c"')

    def test_binary(self):
        data = b"\x00shortcuts\x00" + binary_vdf({"0": {"appid": signed(shortcut_id(ESDE)), **ESDE,
                                                        "tags": {}}}) + b"\x08"
        tree = vdf.parse_binary(data)
        self.assertEqual(vdf.lookup(tree, "shortcuts", "0", "AppName"), "ES-DE")
        self.assertEqual(vdf.lookup(tree, "shortcuts", "0", "appid") & 0xFFFFFFFF, shortcut_id(ESDE))


class SteamInputTest(unittest.TestCase):
    def setUp(self):
        self.steam = Path(tempfile.mkdtemp()) / "Steam"
        self.config = self.steam / "userdata" / "11111111" / "config"
        self.config.mkdir(parents=True)

    def write(self, shortcuts: list[dict], apps: dict[str, str]):
        entries = {str(i): {"appid": signed(shortcut_id(sc)), **sc} for i, sc in enumerate(shortcuts)}
        (self.config / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00" + binary_vdf(entries) + b"\x08")
        body = "".join(f'\t\t\t"{k}"\n\t\t\t{{\n\t\t\t\t"UseSteamControllerConfig"\t\t"{v}"\n\t\t\t}}\n'
                       for k, v in apps.items())
        (self.config / "localconfig.vdf").write_text(
            f'"UserLocalConfigStore"\n{{\n\t"apps"\n\t{{\n{body}\t}}\n}}\n', encoding="utf-8")

    def findings(self):
        return [(f.severity, f.message) for f in doctor.check_steam_input(self.steam)]

    def test_disabled_on_esde_is_an_error(self):
        self.write([ESDE, BROWSER], {str(shortcut_id(ESDE)): "0", str(shortcut_id(BROWSER)): "0"})
        found = self.findings()
        self.assertEqual(len(found), 1, found)   # the browser's override isn't map-helper's business
        self.assertEqual(found[0][0], "error")
        self.assertIn('"ES-DE"', found[0][1])

    def test_srm_launcher_shortcut(self):
        self.write([SRM_DOLPHIN], {str(shortcut_id(SRM_DOLPHIN)): "0"})
        self.assertEqual([s for s, _ in self.findings()], ["error"])

    def test_signed_key_is_ignored_by_steam(self):
        # Older SRM versions keyed the app by the signed id; current Steam reads only the unsigned one (SRM#891).
        self.write([SRM_DOLPHIN], {str(signed(shortcut_id(SRM_DOLPHIN))): "0"})
        self.assertEqual([s for s, _ in self.findings()], ["info"])

    def test_default_and_forced_on_are_fine(self):
        self.write([ESDE, SRM_DOLPHIN], {str(shortcut_id(ESDE)): "1", str(shortcut_id(SRM_DOLPHIN)): "2"})
        self.assertEqual(self.findings(), [])

    def test_unknown_shortcut_id_is_a_warning(self):
        self.write([], {str(shortcut_id(ESDE)): "0", "620": "0"})   # 620 is a Steam game: ignored
        self.assertEqual([s for s, _ in self.findings()], ["warning"])

    def test_no_steam(self):
        self.assertEqual([f.severity for f in doctor.check_steam_input(self.steam.parent / "nope")], ["info"])


class AutoMapTest(unittest.TestCase):
    def check(self, text):
        path = Path(tempfile.mkdtemp()) / "settings.sh"
        path.write_text(text, encoding="utf-8")
        return [f.severity for f in doctor.check_emudeck_automap(path, doctor.read_emudeck_settings(path))]

    def test_values(self):
        self.assertEqual(self.check("autoMapDolphin=true\n"), ["error"])
        self.assertEqual(self.check("autoMapDolphin=null\n"), ["error"])   # jq's output for a missing key
        self.assertEqual(self.check("autoMapDolphin=false\n"), [])
        self.assertEqual(self.check('autoMapDolphin="false"\n'), [])
        self.assertEqual(self.check("controllerLayout=baxy\n"), ["info"])
        # Cemu and the Switch emulators aren't managed: their AutoMap is only info.
        self.assertEqual(self.check("autoMapDolphin=false\nautoMapCemu=true\nautoMapSwitch=false\n"), ["info"])


class RetroArchTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "retroarch"
        shutil.copytree(RA_REAL, self.root)
        self.cfg = self.root / "retroarch.cfg"

    def set_cfg(self, key, value, path=None):
        path = path or self.cfg
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines = [ln for ln in lines if not ln.startswith(f"{key} =")] + [f'{key} = "{value}"']
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def findings(self, layout=None):
        return [(f.severity, f.check) for f in doctor.check_retroarch(self.root, layout)
                if f.check != "emudeck-layout" or f.severity != "info"]

    def test_real_capture_golden(self):
        out = doctor.render(doctor.check_retroarch(RA_REAL))
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(out, encoding="utf-8")
        self.assertEqual(out, GOLDEN.read_text(encoding="utf-8"))

    def test_remaps_switched_off(self):
        self.set_cfg("auto_remaps_enable", "false")
        self.set_cfg("input_remap_binds_enable", "false")
        self.assertEqual(self.findings(), [("error", "retroarch-remaps")] * 2)

    def test_sort_by_controller(self):
        self.set_cfg("input_remap_sort_by_controller_enable", "true")
        self.assertEqual(self.findings(), [("error", "retroarch-remaps")])

    def test_override_switches_remaps_off(self):
        self.set_cfg("input_remap_binds_enable", "false", self.root / "config" / "Snes9x" / "snes.cfg")
        found = [f for f in doctor.check_retroarch(self.root) if f.check == "retroarch-remaps"]
        self.assertEqual([f.severity for f in found], ["error"])
        self.assertIn("config/Snes9x/snes.cfg", found[0].message)

    def test_override_ignored_when_overrides_are_off(self):
        self.set_cfg("input_remap_binds_enable", "false", self.root / "config" / "Snes9x" / "snes.cfg")
        self.set_cfg("auto_overrides_enable", "false")
        self.assertEqual(self.findings(), [])

    def test_autoconfig_off_and_user_binds(self):
        self.set_cfg("input_autodetect_enable", "false")
        self.set_cfg("input_player1_a_btn", "3")
        self.set_cfg("input_player2_l2_axis", "+4")
        self.assertEqual(self.findings(),
                         [("error", "retroarch-autoconfig")] + [("warning", "retroarch-autoconfig")] * 2)

    def test_game_remap_shadows_core_remap(self):
        (self.root / SNES9X / "Super Metroid (USA).rmp").write_text('input_player1_btn_b = "8"\n', encoding="utf-8")
        (self.root / SNES9X / "snes.rmp").write_text('input_player1_btn_b = "8"\n', encoding="utf-8")
        self.assertEqual(self.findings(), [("warning", "retroarch-shadow")] * 2)

    def test_core_remap_next_to_emudeck_disabled(self):
        (self.root / SNES9X / "Snes9x.rmp").write_text('input_player1_btn_b = "8"\n', encoding="utf-8")
        self.assertEqual(self.findings(), [("warning", "emudeck-layout")])
        (self.root / SNES9X / "Snes9x.rmp.disabled").unlink()
        found = doctor.check_retroarch(self.root, "abxy")
        self.assertIn("likely EmuDeck's own", [f for f in found if f.severity == "warning"][0].message)

    def test_remap_save_on_exit_with_managed_remaps(self):
        rmp = f"{SNES9X}/Snes9x.rmp"
        found = [(f.severity, f.check) for f in doctor.check_retroarch(self.root, managed=[rmp])]
        self.assertEqual(found.count(("warning", "retroarch-remap-save")), 1)  # on in the capture
        self.set_cfg("remap_save_on_exit", "false")
        self.assertNotIn("retroarch-remap-save", [f.check for f in doctor.check_retroarch(self.root, managed=[rmp])])

    def test_remap_save_on_exit_reads_the_manifest(self):
        home = self.root.parent / "home"
        state = home / ".local/state/map-helper"
        state.mkdir(parents=True)
        checks = lambda: [f.check for f in doctor.run(home / "Steam", self.root, home / "settings.sh", home)]
        self.assertNotIn("retroarch-remap-save", checks())          # map-helper hasn't written a remap
        (state / "touched.json").write_text(json.dumps({"retroarch": {"config_root": str(self.root), "files": {
            f"{SNES9X}/Snes9x.rmp": {"created": True, "hash": None}}}}), encoding="utf-8")
        self.assertIn("retroarch-remap-save", checks())

    def test_remap_dir_outside_root(self):
        self.set_cfg("input_remapping_directory", "/elsewhere/remaps")
        self.assertEqual([(f.severity, f.check) for f in doctor.check_retroarch(self.root)],
                         [("info", "retroarch-remaps")])


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["doctor", *args])
        return code, out.getvalue()

    def test_exit_code_and_read_only(self):
        tmp = Path(tempfile.mkdtemp())
        ra = tmp / "retroarch"
        shutil.copytree(RA_REAL, ra)
        settings = tmp / "settings.sh"
        settings.write_text("autoMapDolphin=false\ncontrollerLayout=baxy\n", encoding="utf-8")
        before = tree_digest(tmp)
        code, out = self.run_cli("--steam-root", str(tmp / "Steam"), "--retroarch-root", str(ra),
                                 "--emudeck-settings", str(settings))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.endswith("No problems found.\n"), out)
        self.assertEqual(tree_digest(tmp), before)

        settings.write_text("autoMapDolphin=true\n", encoding="utf-8")
        before = tree_digest(tmp)
        code, out = self.run_cli("--steam-root", str(tmp / "Steam"), "--retroarch-root", str(ra),
                                 "--emudeck-settings", str(settings), "--json")
        self.assertEqual(code, 1)
        self.assertIn('"severity": "error"', out)
        self.assertEqual(tree_digest(tmp), before)


if __name__ == "__main__":
    unittest.main()
