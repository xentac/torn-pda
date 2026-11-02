#!/usr/bin/env bash
# Builds the emulator snapshot that replay tests start from ($PDA_SNAPSHOT).
#   PDA_FAKE_KEY=... tools/replay/make-snapshot.sh ONBOARDING.mitm FACTION.mitm PROFILE.mitm
# ONBOARDING answers the API key check. setup.yaml opens the faction page once and
# open-profile.yaml opens a profile once, to get the first-run tips out of the way.
# add-userscripts.yaml adds the test userscripts (tools/replay/userscripts/).
# Then open-blank.yaml leaves the browser on an empty page, so that no Torn page
# runs when a test starts.
# PROFILE must have the profile in open-profile.yaml (the attack recording has it).
# Needs the replay shell (mitmproxy in Python), maestro and adb.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/common.sh"
[ $# -ge 3 ] || { echo "usage: make-snapshot.sh ONBOARDING.mitm FACTION.mitm PROFILE.mitm" >&2; exit 2; }
: "${PDA_FAKE_KEY:?set PDA_FAKE_KEY to the fake API key that pda_anonymize.py printed}"
# PDA's browser tips are invisible to Maestro: the overlay is an empty full-screen
# element. They come in a fixed order, a short time after the first page load, and
# each one closes only on a tap on the element it points at: the page title
# ("Options menu"), the "..." button ("Quick menu") and the "+" button ("New tab
# button"). The targets are fractions of the screen size.
TIP_TARGETS=("0.44 0.09" "0.85 0.95" "0.95 0.95")
# The first profile page shows one more tip ("Did you know?"). It points at the
# green person icon at the right of PDA's bar above the page.
PROFILE_TIP_TARGETS=("0.954 0.134")

ui_dump() {
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  adb exec-out cat /sdcard/ui.xml
}

tip_overlay() {
  local size
  size=$(adb shell wm size | grep -o '[0-9]*x[0-9]*' | tail -1)
  ui_dump | grep -o "<node [^>]*bounds=\"\[0,0\]\[${size%x*},${size#*x}\]\"[^>]*>" | grep 'clickable="true"' | grep -q 'text=""'
}

screen_has() {
  ui_dump | grep -qF "$1"
}

# Closes one tip for each target given, in order.
close_pda_tips() {
  local size w h target i
  size=$(adb shell wm size | grep -o '[0-9]*x[0-9]*' | tail -1)
  w=${size%x*}
  h=${size#*x}
  for target in "$@"; do
    for i in $(seq 1 30); do
      tip_overlay && break
      [ "$i" = 30 ] && { echo "Expected a PDA tip for the target $target, but none appeared." >&2; exit 1; }
      sleep 1
    done
    read -r fx fy <<<"$target"
    adb shell input tap "$(awk "BEGIN{print int($w*$fx)}")" "$(awk "BEGIN{print int($h*$fy)}")"
    sleep 2
  done
}

logs="$PDA_REC_DIR/logs"
mkdir -p "$logs"
trap stop_proxy EXIT
PDA_MISSES="$logs/make-snapshot.misses.jsonl" start_proxy "$logs/make-snapshot-proxy.log" "$@"
use_proxy
"$here/emu-clock.sh" "$(python3 "$here/rec_start.py" "$1")"
adb shell pm clear "$PDA_APP" >/dev/null
# Open torn.com links in PDA, not in Chrome.
adb shell pm set-app-links-user-selection --user 0 --package "$PDA_APP" true torn.com www.torn.com
maestro test -e PDA_FAKE_KEY="$PDA_FAKE_KEY" "$here/flows/setup.yaml"
close_pda_tips "${TIP_TARGETS[@]}"
maestro test "$here/flows/dismiss-tips.yaml"
maestro test "$here/flows/open-profile.yaml"
close_pda_tips "${PROFILE_TIP_TARGETS[@]}"
if tip_overlay || screen_has "Swipe right to reveal the sidebar"; then
  echo "A tip is still open. The snapshot was not saved." >&2
  exit 1
fi
maestro test "$here/flows/add-userscripts.yaml"
maestro test "$here/flows/open-blank.yaml"
adb emu avd snapshot save "$PDA_SNAPSHOT"
echo "Saved snapshot $PDA_SNAPSHOT."
