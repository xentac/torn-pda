#!/usr/bin/env bash
# Compare Torn PDA against another Android browser on the same pages, on the same device.
#
# Usage:
#   tools/perf/adb-bench.sh [-n RUNS] [-o OUTDIR] PACKAGE [URL...]
#
# Examples:
#   tools/perf/adb-bench.sh com.manuito.tornpda
#   tools/perf/adb-bench.sh org.mozilla.firefox
#   tools/perf/adb-bench.sh -n 5 com.manuito.tornpda https://www.torn.com/item.php
#
# Requirements:
# - adb on PATH and exactly one device attached (or ANDROID_SERIAL set).
# - You are logged in to torn.com in the browser under test.
# - For page-load numbers, install tools/perf/pda-perf-probe.user.js in both browsers.
#   This script measures what the probe cannot see: frame pacing of the whole app
#   (Flutter UI + platform view + WebView), process memory and CPU.
#
# What it does for each URL and run:
# 1. Opens the URL with a VIEW intent in PACKAGE and waits SETTLE seconds.
# 2. Resets gfxinfo, performs SWIPES scroll gestures, then saves `dumpsys gfxinfo`.
# 3. Saves `dumpsys meminfo` and the CPU time of the app process(es).
# Output goes to OUTDIR/<package>/<run>-<slug>.{gfx,mem,cpu}.txt plus a summary.tsv.
#
# Notes:
# - A VIEW intent is not a link tap. In Torn PDA it goes through the deep-link handler and a
#   Dart loadUrl, so it does not include the shouldOverrideUrlLoading delay of a real tap. It
#   can also show a toast, and with "open deep links in a new tab" it opens a new tab on every
#   run. Turn that option off and close extra tabs first. Measure tap latency with the probe's
#   "tap" fields instead.
# - SETTLE=8 starts the swipes after most post-load work is done. Run once more with SETTLE=1 to
#   see scrolling while the app is still busy with the page load.
# - CPU covers the app process (and its ":" subprocesses). WebView renderer processes are
#   shared and their names do not include the package, so they are counted only with
#   RENDERERS=1. Close other WebView apps and Chrome first if you use it.
# - Firefox (GeckoView) does not report its content frames through gfxinfo the same way
#   as an Android View hierarchy. Compare Firefox with the probe's rAF frame-gap data and
#   with Perfetto (see docs/perf/measurement.md), not with gfxinfo alone.
# - For Torn PDA, gfxinfo covers the Flutter surface. With Hybrid Composition the WebView
#   is part of the Android view hierarchy, so its frames show up there too.
set -euo pipefail

RUNS=3
OUTDIR="perf-results"
SETTLE="${SETTLE:-8}"
SWIPES="${SWIPES:-10}"
while getopts "n:o:" opt; do
  case "$opt" in
    n) RUNS="$OPTARG" ;;
    o) OUTDIR="$OPTARG" ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
PKG="${1:?package name required}"
shift
if [ "$#" -eq 0 ]; then
  set -- \
    "https://www.torn.com/index.php" \
    "https://www.torn.com/item.php" \
    "https://www.torn.com/profiles.php?XID=1" \
    "https://www.torn.com/factions.php?step=your" \
    "https://www.torn.com/page.php?sid=ItemMarket" \
    "https://www.torn.com/gym.php"
fi

mkdir -p "$OUTDIR/$PKG"
SUMMARY="$OUTDIR/$PKG/summary.tsv"
[ -f "$SUMMARY" ] || printf "run\turl\tframes\tjanky_pct\tp50_ms\tp90_ms\tp99_ms\tpss_kb\tcpu_ticks\n" >"$SUMMARY"

# "Override size" (if present) comes after "Physical size" and wins.
read -r W H < <(adb shell wm size | awk -F'[ x]' '/size:/ {w = $3; h = $4} END {print w, h}')
X=$((W / 2))
Y1=$((H * 3 / 4))
Y2=$((H / 4))

cpu_ticks() {
  # utime+stime of every process of the package, in clock ticks.
  local total=0 pid
  for pid in $(adb shell pidof "$@" 2>/dev/null); do
    # Isolated renderer processes can be unreadable without root.
    t=$(adb shell cat "/proc/$pid/stat" 2>/dev/null | awk '{print $14 + $15}' || true)
    total=$((total + ${t:-0}))
  done
  echo "$total"
}

procs() {
  # The app process and its own subprocesses (Gecko content processes are "$PKG:tab<N>").
  local re="^$PKG(:|$)"
  [ "${RENDERERS:-0}" = 1 ] && re="$re|webview|sandboxed_process|privileged_process"
  adb shell ps -A -o NAME | grep -E "$re" | sort -u | tr '\n' ' '
}

for run in $(seq 1 "$RUNS"); do
  for url in "$@"; do
    slug=$(echo "$url" | sed -E 's#https?://##; s#[^A-Za-z0-9]+#_#g' | cut -c1-60)
    base="$OUTDIR/$PKG/$run-$slug"
    echo ">> $PKG run $run: $url"
    adb shell am start -W -a android.intent.action.VIEW -d "'$url'" "$PKG" >"$base.start.txt"
    sleep "$SETTLE"
    # shellcheck disable=SC2046
    c0=$(cpu_ticks $(procs))
    adb shell dumpsys gfxinfo "$PKG" reset >/dev/null
    for _ in $(seq 1 "$SWIPES"); do
      adb shell input swipe "$X" "$Y1" "$X" "$Y2" 250
      adb shell input swipe "$X" "$Y2" "$X" "$Y1" 250
    done
    sleep 1
    adb shell dumpsys gfxinfo "$PKG" >"$base.gfx.txt"
    adb shell dumpsys meminfo "$PKG" >"$base.mem.txt"
    # shellcheck disable=SC2046
    c1=$(cpu_ticks $(procs))
    echo "$((c1 - c0))" >"$base.cpu.txt"
    frames=$(awk -F': ' '/Total frames rendered/ {print $2; exit}' "$base.gfx.txt")
    janky=$(awk -F'[()]' '/Janky frames:/ {print $2; exit}' "$base.gfx.txt")
    p50=$(awk '/^50th percentile/ {print $3; exit}' "$base.gfx.txt")
    p90=$(awk '/^90th percentile/ {print $3; exit}' "$base.gfx.txt")
    p99=$(awk '/^99th percentile/ {print $3; exit}' "$base.gfx.txt")
    pss=$(awk '/TOTAL PSS:/ {print $3; exit} /^ *TOTAL / {print $2; exit}' "$base.mem.txt")
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$run" "$url" "${frames:-NA}" "${janky:-NA}" "${p50:-NA}" "${p90:-NA}" "${p99:-NA}" "${pss:-NA}" "$((c1 - c0))" >>"$SUMMARY"
  done
done
echo "Summary: $SUMMARY"
column -t -s $'\t' "$SUMMARY"
