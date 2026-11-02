#!/usr/bin/env bash
# Runs one Maestro flow against recordings, starting from the replay snapshot.
#   tools/replay/run-test.sh flows/faction.yaml RECORDING.mitm [MORE.mitm ...]
# The clock starts at the first request of the first recording.
# Set PDA_APK to install a build before the test (it keeps the snapshot's app data).
# Results go to $PDA_REC_DIR/runs/<UTC time>-<flow>/.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/common.sh"
[ $# -ge 2 ] || { echo "usage: run-test.sh FLOW.yaml RECORDING.mitm [MORE.mitm ...]" >&2; exit 2; }
flow=$1
shift
name=$(basename "$flow" .yaml)
out="$PDA_REC_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)-$name"
mkdir -p "$out"
trap stop_proxy EXIT
adb emu avd snapshot load "$PDA_SNAPSHOT" >/dev/null
adb wait-for-device
if [ -n "${PDA_APK:-}" ]; then
  adb install -r "$PDA_APK" >/dev/null
fi
PDA_MISSES="$out/misses.jsonl" start_proxy "$out/proxy.log" "$@"
use_proxy
"$here/emu-clock.sh" "$(python3 "$here/rec_start.py" "$1")"
adb logcat -c
status=0
maestro test --test-output-dir "$out/maestro" "$flow" >"$out/maestro.log" 2>&1 || status=$?
adb logcat -d >"$out/logcat.txt"
grep -E "PDA-PERF" "$out/logcat.txt" >"$out/perf.txt" || true
misses=$(grep -c '"miss"' "$out/misses.jsonl" 2>/dev/null || true)
echo "$name: $([ $status -eq 0 ] && echo passed || echo FAILED), ${misses:-0} misses. Results in $out"
exit $status
