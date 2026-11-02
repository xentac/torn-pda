#!/usr/bin/env bash
# Runs one Maestro flow against recordings, starting from the replay snapshot.
#   tools/replay/run-test.sh flows/faction.yaml RECORDING.mitm [MORE.mitm ...]
# The clock starts at the first request of the first recording.
# Set PDA_APK to install a build before the test (it keeps the snapshot's app data), and PDA_BUILD
# to name it (for example its commit). The name goes into env.json and the run folder name.
# The run folder gets a status file (passed or failed). tools/perf/summarize.py skips failed runs.
# Results go to $PDA_REC_DIR/runs/<UTC time>-<flow>/.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/common.sh"
[ $# -ge 2 ] || { echo "usage: run-test.sh FLOW.yaml RECORDING.mitm [MORE.mitm ...]" >&2; exit 2; }
flow=$1
shift
name=$(basename "$flow" .yaml)
out="$PDA_REC_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)-$name${PDA_BUILD:+-$PDA_BUILD}"
mkdir -p "$out"
trap stop_proxy EXIT
# run-baseline.sh boots each emulator from the snapshot, and sets PDA_SNAPSHOT_LOADED=1.
if [ -z "${PDA_SNAPSHOT_LOADED:-}" ]; then
  adb emu avd snapshot load "$PDA_SNAPSHOT" >/dev/null
fi
adb wait-for-device
if [ -n "${PDA_APK:-}" ]; then
  adb install -r "$PDA_APK" >/dev/null
  # The install stops PDA. Start it again, so that the flow starts on the blank page as without an install.
  adb shell monkey -p "$PDA_APP" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  for _ in $(seq 1 60); do
    adb shell dumpsys window 2>/dev/null | grep -q "mCurrentFocus=.*$PDA_APP" && break
    sleep 1
  done
  sleep 5
fi
PDA_MISSES="$out/misses.jsonl" start_proxy "$out/proxy.log" "$@"
use_proxy
"$here/emu-clock.sh" "$(python3 "$here/rec_start.py" "$1")"
# What a comparison must keep equal. tools/perf/summarize.py refuses to mix runs that differ here.
pkg=$(adb shell dumpsys package "$PDA_APP")
apk=$(adb shell pm path "$PDA_APP" | grep -m1 'base.apk' | tr -d '\r' | cut -d: -f2)
python3 - "$out/env.json" <<PY
import json, sys
json.dump({
    "pda_commit": "${PDA_BUILD:-$(git -C "$here" describe --always --dirty)}",
    "apk_sha256": "$(adb shell sha256sum "$apk" | cut -c1-16)",
    "app_version": "$(grep -m1 -o 'versionName=[^ ]*' <<<"$pkg" | cut -d= -f2)",
    "app_installed": "$(grep -m1 -o 'lastUpdateTime=.*' <<<"$pkg" | cut -d= -f2)",
    "webview": "$(adb shell dumpsys webviewupdate | grep -m1 -o 'Current WebView package.*' | tr -d '\r')",
    "avd": "$(adb emu avd name | head -1 | tr -d '\r')",
    "snapshot": "$PDA_SNAPSHOT",
    "recordings": "$*",
    "mitm_args": "${MITM_ARGS:-}",
    "static": "$PDA_STATIC",
}, open(sys.argv[1], "w"), indent=1)
PY
# A long flow logs more than the default buffer holds.
adb logcat -G 16M
adb logcat -c
status=0
maestro test --test-output-dir "$out/maestro" "$flow" >"$out/maestro.log" 2>&1 || status=$?
# PDA_PERF builds write the record of a page 10 s after its load. Wait for the last page.
sleep "${PDA_PERF_WAIT:-12}"
adb logcat -d >"$out/logcat.txt"
# PDA's own lines. Chromium also logs the probe's console line ("[PDA-PERF] {"), cut short.
grep -E "\[PDA-PERF-(DART|PROBE)\] " "$out/logcat.txt" >"$out/perf.txt" || true
[ $status -eq 0 ] && echo passed >"$out/status" || echo failed >"$out/status"
misses=$(grep -c '"miss"' "$out/misses.jsonl" 2>/dev/null || true)
echo "$name: $([ $status -eq 0 ] && echo passed || echo FAILED), ${misses:-0} misses. Results in $out"
exit $status
