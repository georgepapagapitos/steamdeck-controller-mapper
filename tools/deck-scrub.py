"""Scrub a capture on the Deck before it leaves: replace MACs and USB serials with salted lookalikes, blank credentials.

    python3 -I deck-scrub.py DIR SALT_FILE           scrub a fresh capture in place
    python3 -I deck-scrub.py DIR SALT_FILE --rekey   convert a capture scrubbed before the salt existed

The salt is created once on the Deck and never leaves it, so a fake can't be reversed by trying every value (a MAC
with its vendor half kept has only 2^24 candidates), yet one pad keeps one fake in every capture. A fake MAC keeps the
real vendor half (brand detection uses the OUI); a fake serial keeps the real length and case.

Fakes are salted digests of the unsalted digest the first captures used, so --rekey can bring those captures in line
with new ones without the real values. Exits non-zero, and the caller sends nothing, if any original survives.
"""

import hashlib
import hmac
import os
import pathlib
import re
import secrets
import sys

MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
# Steam's slot handle is a small prefix plus the pad's MAC (also for a slot it keeps after the pad disconnects, when
# the MAC appears nowhere else). Wired X-input handles start 0x1<VID><PID> and hold no MAC.
HANDLE = re.compile(r"^handle=0x00[0-9A-Fa-f]{2}([0-9A-Fa-f]{12})$", re.M)
UNIQ = re.compile(r"^U: Uniq=(.*)$", re.M)
SETTING = re.compile(r"^([ \t]*([\w.]+)[ \t]*=[ \t]*)(.*)$", re.M)
CREDENTIAL_WORDS = {"password", "passwd", "token", "secret", "username", "nickname", "cookie", "credential",
                    "credentials", "auth"}
URL_USERINFO = re.compile(r"(?<=://)[^/@\s\"']+@")


def is_analytics_id(m: re.Match) -> bool:
    return m[2] == "ID" and re.fullmatch(r"[0-9a-f]{32}", m[3].strip()) is not None


def is_credential(key: str) -> bool:
    """A whole word of the key names a credential: twitch_stream_key, webdav_password and ApiToken yes;
    mgba_audio_low_pass_filter, vibrate_on_keypress and netplay_show_passworded no."""
    words = [w.lower() for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", key)]
    joined = "".join(words)
    return bool(CREDENTIAL_WORDS & set(words)) or joined.endswith(("streamkey", "apikey"))


def main(root: pathlib.Path, salt_file: pathlib.Path, rekey: bool) -> int:
    if not salt_file.exists():
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(salt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, secrets.token_bytes(32))
        os.close(fd)
    salt = salt_file.read_bytes()

    def digest(value: str) -> str:
        return hmac.new(salt, value.encode(), hashlib.sha256).hexdigest()

    def fake_mac(bare: str) -> str:  # bare: 12 lower-case hex digits
        inner = bare if rekey else bare[:6] + hashlib.sha1(bare.encode()).hexdigest()[:6]
        return bare[:6] + digest(inner)[:6]

    def fake_serial(serial: str) -> str:
        cased = (lambda h: h.upper() if serial.isupper() else h)
        inner = serial if rekey else cased(hashlib.sha1(serial.encode()).hexdigest()[:len(serial)])
        out = digest(inner) * 2
        # A short serial's fake can equal the original by chance (1 in 16 for one character); slide until it doesn't.
        return next(cased(out[i:i + len(serial)]) for i in range(64) if out[i:i + len(serial)] != serial.lower())

    files = {}
    for f in root.rglob("*"):
        if f.is_file():
            try:
                files[f] = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:  # can't be scrubbed as text, so it doesn't leave the Deck
                print(f"scrub: dropped {f.relative_to(root)} (not UTF-8 text)", file=sys.stderr)
                f.unlink()

    macs = {m.lower().replace(":", "") for s in files.values() for m in MAC.findall(s)}
    macs |= {h.lower() for s in files.values() for h in HANDLE.findall(s)}
    uniqs = [u.strip() for s in files.values() for u in UNIQ.findall(s)]
    uniqs += [row.split("\t")[2].strip() for f, s in files.items() if f.name == "sys-class-input.tsv"
              for row in s.splitlines() if row.count("\t") >= 4]
    serials = {u for u in uniqs if u and set(u) != {"0"} and not MAC.fullmatch(u)}

    # Every original, in every form it takes, mapped to its fake. One pass, longest first, so no replacement can
    # clip another original before that one is replaced.
    swap = {}
    for bare in macs:
        new = fake_mac(bare)
        swap[bare] = new
        swap[":".join(re.findall("..", bare))] = ":".join(re.findall("..", new))
    serial_fake = {u: fake_serial(u) for u in serials}
    for serial in serials:
        if len(serial) >= 6:  # a short one (say "1") would hit unrelated text; it's replaced in its field below
            swap[serial.lower()] = serial_fake[serial]
    pattern = re.compile("|".join(map(re.escape, sorted(swap, key=len, reverse=True))), re.I) if swap else None

    def field(value: str) -> str:
        return serial_fake.get(value.strip(), value)

    for f, s in files.items():
        s = UNIQ.sub(lambda m: "U: Uniq=" + field(m[1]), s)
        if f.name == "sys-class-input.tsv":
            rows = [r.split("\t") for r in s.splitlines()]
            s = "".join("\t".join(r[:2] + [field(r[2])] + r[3:] if len(r) >= 5 else r) + "\n" for r in rows)
        if pattern:
            s = pattern.sub(lambda m: swap[m[0].lower()], s)
        # Blank credentials, keeping the key (the quotes go too), and Dolphin.ini's per-install [Analytics] ID.
        s = SETTING.sub(lambda m: m[1] if is_credential(m[2]) or is_analytics_id(m) else m[0], s)
        files[f] = URL_USERINFO.sub("", s)

    survivors = [f for f, s in files.items() for original in swap if original in s.lower()]
    survivors += [f for f, s in files.items() for u in serials
                  if re.search(r"^U: Uniq=" + re.escape(u) + "$", s, re.M) or "\t" + u + "\t" in s]
    survivors += [f for f, s in files.items() if URL_USERINFO.search(s)
                  or any((is_credential(m[2]) and m[3].strip()) or is_analytics_id(m) for m in SETTING.finditer(s))]
    if survivors:
        print(f"scrub: an original value or a credential survived in {survivors[0].name}", file=sys.stderr)
        return 1
    for f, s in files.items():
        f.write_text(s, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]).expanduser(), "--rekey" in sys.argv[3:]))
