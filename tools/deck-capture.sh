# Runs ON the Deck, piped in by `tools/deck.sh capture`: copies what the spikes in docs/13 ask for into a temp dir,
# scrubs it, and writes a tar of it to stdout. Read-only on the Deck.
set -u
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
grab() { [ -e "$1" ] && mkdir -p "$t/$2" && cp -r "$1" "$t/$2/" 2>/dev/null; }

mkdir -p "$t/devices"
{
  echo "captured: $(date -Iseconds)"
  grep -E '^(PRETTY_NAME|VERSION_ID|BUILD_ID)=' /etc/os-release
  echo "python: $(/usr/bin/python3 --version 2>&1)"
  echo "board: $(cat /sys/devices/virtual/dmi/id/board_name 2>/dev/null)"
  echo "emudeck backend: $(git -C ~/.config/EmuDeck/backend log -1 --format="%h %cs" 2>/dev/null)"
  flatpak list --app --columns=application,version 2>/dev/null | grep -iE 'dolphin|retroarch|pcsx2|duckstation'
  ls ~/Applications 2>/dev/null | grep -iE 'pcsx2|duckstation'
} > "$t/devices/versions.txt"
cp /proc/bus/input/devices "$t/devices/proc-bus-input-devices"
for d in /sys/class/input/*/device; do
  [ -r "$d/name" ] || continue
  printf '%s\t%s\t%s\t%s\t%s:%s\n' "$(basename "$(dirname "$d")")" "$(cat "$d/name")" "$(cat "$d/uniq" 2>/dev/null)" \
    "$(cat "$d/phys" 2>/dev/null)" "$(cat "$d/id/vendor" 2>/dev/null)" "$(cat "$d/id/product" 2>/dev/null)"
done | sort -u > "$t/devices/sys-class-input.tsv"
# USB devices (not root hubs: their serial is the PCI address) with their sysfs `serial`, for usb-serial: ids (docs/04
# §1.2). The path column matches "S: Sysfs=" in proc-bus-input-devices; the serial (column 3) is scrubbed below.
for d in /sys/bus/usb/devices/*; do
  [ -r "$d/idVendor" ] || continue
  case "$(basename "$d")" in usb*) continue ;; esac
  real=$(cd "$d" && pwd -P)
  printf '%s\t%s\t%s\t%s\t%s:%s\n' "$(basename "$d")" "$(cat "$d/product" 2>/dev/null)" "$(cat "$d/serial" 2>/dev/null)" \
    "${real#/sys}" "$(cat "$d/idVendor")" "$(cat "$d/idProduct")"
done | sort > "$t/devices/usb-devices.tsv"
for f in /sys/class/drm/card*-*/status; do echo "$f $(cat "$f")"; done > "$t/devices/drm-status.txt" 2>/dev/null
for p in /sys/class/power_supply/*; do echo "$p type=$(cat "$p/type") online=$(cat "$p/online" 2>/dev/null)"; done > "$t/devices/power-supply.txt" 2>/dev/null
grab ~/.local/share/Steam/config/virtualgamepadinfo.txt devices

grab ~/.var/app/org.DolphinEmu.dolphin-emu/config/dolphin-emu/. dolphin
# Input config only (docs/10): drop play history, UI state, logging, graphics and the achievements login.
for f in TimePlayed Qt Logger GFX FreeLook RetroAchievements; do rm -f "$t/dolphin/$f.ini" "$t/dolphin/$f.ini.bak"; done
grab ~/.config/PCSX2/inis pcsx2
grab ~/.local/share/duckstation/settings.ini duckstation
grab ~/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg retroarch
grab ~/.var/app/org.libretro.RetroArch/config/retroarch/config retroarch

# Scrub before anything leaves the Deck (tools/deck-scrub.py, pushed by deck.sh). Copies of /proc and sysfs files keep
# their read-only mode, so make everything writable first. If the scrub fails, send nothing.
chmod -R u+w "$t"
/usr/bin/python3 -I ~/map-helper-dev/tools/deck-scrub.py "$t" ~/.local/state/map-helper/capture-salt ||
  { echo "scrub failed; nothing was sent" >&2; exit 1; }

tar -c -C "$t" .
