#!/usr/bin/env bash
# Runs one flow N times, each time in a new emulator process that boots from the replay snapshot.
#   PDA_EMULATOR="emulator" tools/replay/run-baseline.sh flows/faction.yaml 8 RECORDING.mitm [MORE.mitm ...]
# A new process per run removes GPU and memory state that earlier runs leave, and it avoids an
# emulator crash on a second snapshot load (gfxstream ColorBuffer::onLoad).
# Stop any running emulator first. PDA_EMULATOR is the emulator command (it must find the AVD and,
# on NixOS, the host GL drivers). The network timing defaults to the recorded latency.
# Then summarize the run folders with tools/perf/summarize.py.
# To compare builds, set PDA_APKS to two or more APK files, each named after its build, for example
# "apks/50a4a3d9.apk apks/1a2b3c4d.apk". RUNS is then the number of runs per build. The builds take
# turns in the order A B B A A B B A, because the emulator drifts during a session. Each run folder
# name ends in the build name.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/common.sh"
[ $# -ge 3 ] || { echo "usage: run-baseline.sh FLOW.yaml RUNS RECORDING.mitm [MORE.mitm ...]" >&2; exit 2; }
flow=$1
runs=$2
shift 2
: "${PDA_AVD:=dev}"
export MITM_ARGS="${MITM_ARGS:---set pda_replay_latency=recorded}"
if adb get-state >/dev/null 2>&1; then
  echo "An emulator is already running. Stop it first (adb emu kill)." >&2
  exit 1
fi

emu_pid=
stop_emulator() {
  [ -n "$emu_pid" ] || return 0
  adb emu kill >/dev/null 2>&1 || true
  wait "$emu_pid" 2>/dev/null || true
  emu_pid=
}
trap stop_emulator EXIT

# One entry per run: the APK to install, or "" to test the installed build.
read -r -a apks <<<"${PDA_APKS:-}"
order=()
if [ ${#apks[@]} -eq 0 ]; then
  for _ in $(seq 1 "$runs"); do order+=(""); done
else
  for r in $(seq 1 "$runs"); do
    if [ $((r % 2)) -eq 1 ]; then
      order+=("${apks[@]}")
    else
      for ((k = ${#apks[@]} - 1; k >= 0; k--)); do order+=("${apks[k]}"); done
    fi
  done
fi
total=${#order[@]}

failed=0
for i in $(seq 1 "$total"); do
  apk=${order[i - 1]}
  log="$PDA_REC_DIR/logs/run-baseline-emulator.log"
  mkdir -p "$(dirname "$log")"
  # shellcheck disable=SC2086
  ${PDA_EMULATOR:-emulator} -avd "$PDA_AVD" -gpu host -snapshot "$PDA_SNAPSHOT" -no-snapshot-save -no-boot-anim >"$log" 2>&1 &
  emu_pid=$!
  adb wait-for-device
  # A snapshot boot reports boot_completed at once. Wait until PDA has the screen.
  for _ in $(seq 1 120); do
    adb shell dumpsys window 2>/dev/null | grep -q "mCurrentFocus=.*$PDA_APP" && break
    sleep 1
  done
  echo "Run $i of $total${apk:+ ($(basename "$apk" .apk))}:"
  if [ -n "$apk" ]; then
    PDA_SNAPSHOT_LOADED=1 PDA_APK="$apk" PDA_BUILD="$(basename "$apk" .apk)" "$here/run-test.sh" "$flow" "$@" || failed=$((failed + 1))
  else
    PDA_SNAPSHOT_LOADED=1 "$here/run-test.sh" "$flow" "$@" || failed=$((failed + 1))
  fi
  stop_emulator
done
echo "$total runs, $failed failed."
[ "$failed" -eq 0 ]
