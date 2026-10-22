#!/usr/bin/env bash
# Work against a real Steam Deck from the Mac or Windows (Git Bash). Code is written here and shipped over ssh;
# nothing is built on the Deck. Set DECK_HOST if `deck@steamdeck` doesn't resolve on your network.
#   tools/deck.sh push               copy core/, data/, examples/, the scrub to ~/map-helper-dev on the Deck
#   tools/deck.sh run ARGS...        push, then run `map-helper ARGS` there (e.g. run devices)
#   tools/deck.sh capture SCENARIO   dump devices and emulator configs into tests/fixtures/*/SCENARIO/
#   tools/deck.sh ssh                open a shell on the Deck
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=${DECK_HOST:-deck@steamdeck}
DIR=map-helper-dev

push() {
  # tar over ssh rather than rsync: Git Bash on Windows has no rsync. COPYFILE_DISABLE keeps macOS's ._ files out.
  COPYFILE_DISABLE=1 tar -c --exclude __pycache__ --exclude .DS_Store core data examples tools/deck-scrub.py |
    ssh "$HOST" "rm -rf $DIR && mkdir -p $DIR && cd $DIR && tar -x 2>/dev/null"
}

capture() {
  # Layout per docs/10: devices/<scenario>/ for the device dump, <emu>/<scenario>/ for each emulator's config.
  local name="${1:?usage: tools/deck.sh capture SCENARIO (e.g. ds4-bt-steam-input)}"
  for d in devices dolphin pcsx2 duckstation retroarch; do
    [ -e "tests/fixtures/$d/$name" ] && { echo "tests/fixtures/$d/$name already exists. Pick another name." >&2; exit 1; }
  done
  local tmp; tmp="$(mktemp -d)"
  push
  ssh "$HOST" "bash -s" < tools/deck-capture.sh | tar -x -C "$tmp"
  for d in "$tmp"/*/; do
    d="$(basename "$d")"
    # Emulator configs rarely change between controller scenarios; keep a copy only when it differs from every
    # earlier capture.
    same=""
    if [ "$d" != devices ]; then
      for prev in tests/fixtures/"$d"/*/; do
        diff -rq "$tmp/$d" "$prev" >/dev/null 2>&1 && { same="$prev"; break; }
      done
    fi
    if [ -n "$same" ]; then echo "  $d: same as ${same%/}, not kept"; continue; fi
    mkdir -p "tests/fixtures/$d/$name"; cp -R "$tmp/$d/." "tests/fixtures/$d/$name/"
    echo "  tests/fixtures/$d/$name"
  done
  rm -rf "$tmp"
  echo "Add a line to tests/fixtures/README.md saying what was connected, how, and what was changed beforehand."
}

case "${1:-}" in
  push) push ;;
  run) shift; push; ssh "$HOST" "cd $DIR/core && /usr/bin/python3 -m maphelper $(printf '%q ' "$@")" ;;
  capture) shift; capture "$@" ;;
  ssh) exec ssh "$HOST" ;;
  *) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
