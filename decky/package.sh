#!/usr/bin/env bash
# Builds the plugin and packs it as out/map-helper.zip, laid out as Decky expects (docs/14 §1):
#   map-helper/{dist/index.js, package.json, plugin.json, main.py, LICENSE, README.md}
# No py_modules/ yet: the core is installed separately (tools/deck.sh install).
# Runs on macOS (bash 3.2) and Git Bash on Windows; needs node with corepack, and python3 for the zip.
set -euo pipefail
cd "$(dirname "$0")"

export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
corepack pnpm install --frozen-lockfile
corepack pnpm run typecheck
corepack pnpm run build   # always a real build: never the fixture one

# A fixture build answers with sample data instead of asking the backend; it must never ship.
if grep -q 'sample: true' dist/index.js; then
  echo "package.sh: dist/index.js contains sample data (a build:fixture bundle); refusing to pack it" >&2
  exit 1
fi

python3 -I - <<'PY'
import pathlib, zipfile

root = pathlib.Path.cwd()
out = root / "out"
out.mkdir(exist_ok=True)
target = out / "map-helper.zip"

# Our licence on top, the plugin template's BSD-3-Clause notice below it (store rule, docs/14 §9).
license_text = (root.parent / "LICENSE").read_text(encoding="utf-8").rstrip("\n")
license_text += "\n\n" + "-" * 78 + "\n\n" + (root / "TEMPLATE-LICENSE").read_text(encoding="utf-8")

files = {name: (root / name).read_bytes() for name in ("package.json", "plugin.json", "main.py", "README.md")}
files["LICENSE"] = license_text.encode("utf-8")
for path in sorted((root / "dist").rglob("*")):
    if path.is_file():
        files[path.relative_to(root).as_posix()] = path.read_bytes()

with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
    for name in sorted(files):
        info = zipfile.ZipInfo(f"map-helper/{name}", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, files[name])
print(f"wrote {target.relative_to(root.parent)} ({len(files)} files)")
PY
