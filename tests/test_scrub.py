import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO

spec = importlib.util.spec_from_file_location("deck_scrub", REPO / "tools" / "deck-scrub.py")
deck_scrub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deck_scrub)

MAC = "a0:b1:c2:d3:e4:f5"     # made up: never put a real device id in a test
STALE = "e4:17:d8:aa:bb:cc"        # only in a kept slot's handle
SERIAL = "0123456789ABCDE"
PROC = f"""I: Bus=0005 Vendor=054c Product=0ce6 Version=8100
U: Uniq={MAC}
H: Handlers=event20 js1

I: Bus=0003 Vendor=2dc8 Product=310b Version=0001
U: Uniq={SERIAL}

I: Bus=0003 Vendor=1234 Product=5678 Version=0001
U: Uniq=1
H: Handlers=event9 js1
"""
VGI = f"[slot 1]\nhandle=0x000d{MAC.replace(':', '')}\n[slot 2]\nhandle=0x0000{STALE.replace(':', '')}\n" \
      "[slot 3]\nhandle=0x12dc8310b1234567\n"
TSV = f"event20\tDualSense\t{MAC}\t\t054c:0ce6\nevent9\tOdd\t1\t\t1234:5678\n"
CFG = 'cheevos_password = "hunter2"\ninput_player1_btn_a = "0"\nnetplay_password =\nnetplay_port = "55435"\n'


class ScrubTest(unittest.TestCase):
    def capture(self, root: Path):
        (root / "devices").mkdir(parents=True)
        (root / "devices" / "proc-bus-input-devices").write_text(PROC, encoding="utf-8")
        (root / "devices" / "virtualgamepadinfo.txt").write_text(VGI, encoding="utf-8")
        (root / "devices" / "sys-class-input.tsv").write_text(TSV, encoding="utf-8")
        (root / "retroarch.cfg").write_text(CFG, encoding="utf-8")

    def scrub(self, rekey=False, salt=b"s" * 32):
        tmp = Path(tempfile.mkdtemp())
        self.capture(tmp / "c")
        (tmp / "salt").write_bytes(salt)
        if rekey:  # what the first, unsalted captures looked like
            legacy = lambda b: b[:6] + hashlib.sha1(b.encode()).hexdigest()[:6]
            for f in (tmp / "c").rglob("*"):
                if f.is_file():
                    s = f.read_text(encoding="utf-8")
                    for mac in (MAC, STALE):
                        bare = mac.replace(":", "")
                        s = s.replace(mac, ":".join(legacy(bare)[i:i + 2] for i in range(0, 12, 2)))
                        s = s.replace(bare, legacy(bare))
                    s = s.replace(SERIAL, hashlib.sha1(SERIAL.encode()).hexdigest()[:len(SERIAL)].upper())
                    f.write_text(s, encoding="utf-8")
        self.assertEqual(deck_scrub.main(tmp / "c", tmp / "salt", rekey), 0)
        return {f.name: f.read_text(encoding="utf-8") for f in (tmp / "c").rglob("*") if f.is_file()}

    def test_no_original_survives(self):
        out = "".join(self.scrub().values()).lower()
        for original in (MAC, MAC.replace(":", ""), STALE.replace(":", ""), SERIAL.lower(), "hunter2"):
            self.assertNotIn(original, out)

    def test_shape_is_kept(self):
        out = self.scrub()
        self.assertRegex(out["proc-bus-input-devices"], r"U: Uniq=a0:b1:c2(:[0-9a-f]{2}){3}\n")
        self.assertRegex(out["proc-bus-input-devices"], r"U: Uniq=[0-9A-F]{15}\n")
        self.assertIn("handle=0x12dc8310b1234567", out["virtualgamepadinfo.txt"])  # wired: no MAC inside
        self.assertIn('input_player1_btn_a = "0"', out["retroarch.cfg"])

    def test_short_serial_replaced_only_in_its_field(self):
        out = self.scrub()
        self.assertNotIn("U: Uniq=1\n", out["proc-bus-input-devices"])
        self.assertNotIn("\tOdd\t1\t", out["sys-class-input.tsv"])
        self.assertIn("Vendor=1234 Product=5678 Version=0001", out["proc-bus-input-devices"])

    def test_one_pad_one_fake_across_files(self):
        out = self.scrub()
        fake = out["sys-class-input.tsv"].split("\t")[2]
        self.assertIn(fake, out["proc-bus-input-devices"])
        self.assertIn("0x000d" + fake.replace(":", ""), out["virtualgamepadinfo.txt"])

    def test_blanking_never_touches_the_next_line(self):
        # An empty value once let the pattern run past the newline and wipe the following setting.
        cfg = self.scrub()["retroarch.cfg"]
        self.assertIn('netplay_port = "55435"\n', cfg)
        self.assertEqual(cfg.count("\n"), CFG.count("\n"))

    def test_scrubbing_twice_changes_nothing_but_fakes(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "c").mkdir()
        (tmp / "c" / "retroarch.cfg").write_text(CFG, encoding="utf-8")
        (tmp / "salt").write_bytes(b"s" * 32)
        deck_scrub.main(tmp / "c", tmp / "salt", False)
        once = (tmp / "c" / "retroarch.cfg").read_text(encoding="utf-8")
        deck_scrub.main(tmp / "c", tmp / "salt", False)
        self.assertEqual((tmp / "c" / "retroarch.cfg").read_text(encoding="utf-8"), once)

    def test_salt_changes_every_fake(self):
        self.assertNotEqual(self.scrub(salt=b"a" * 32), self.scrub(salt=b"b" * 32))

    def test_rekey_matches_a_fresh_scrub(self):
        self.assertEqual(self.scrub(rekey=True), self.scrub())


if __name__ == "__main__":
    unittest.main()
