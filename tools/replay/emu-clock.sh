#!/usr/bin/env bash
# Set the emulator clock for a replay, or give control back to the network.
#   tools/replay/emu-clock.sh 2026-11-01T18:30:00Z
#   tools/replay/emu-clock.sh --auto
# Needs an emulator image without the Play Store (google_apis), so that adb root works.
set -euo pipefail
t=${1:?usage: emu-clock.sh UTC-TIME | --auto}
adb root >/dev/null
adb wait-for-device
if [ "$t" = --auto ]; then
  adb shell settings put global auto_time 1
  exit 0
fi
adb shell settings put global auto_time 0
# toybox date sets the time from MMDDhhmmCCYY.ss.
adb shell date -u "$(date -u -d "$t" +%m%d%H%M%Y.%S)" >/dev/null
echo "Device clock: $(adb shell date -u)"
