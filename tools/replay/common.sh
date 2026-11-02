# Shared settings for capture.sh and replay.sh. Source it, do not run it.

# Port that mitmproxy listens on. The emulator reaches the host at 10.0.2.2.
PDA_PROXY_PORT=${PDA_PROXY_PORT:-8080}

# Hosts that pass through without interception, in capture and in replay.
# Firebase and Google services do not need recording, and their traffic holds
# Google account tokens. They also stay live during replay, so the app starts.
PDA_PASSTHROUGH=${PDA_PASSTHROUGH:-'^(.+\.)?(google|googleapis|gstatic|googleusercontent|firebaseio|firebaseapp|crashlytics|app-measurement|doubleclick)\.(com|net|io)(:[0-9]+)?$'}

# Hosts whose flows capture.sh saves (a mitmproxy filter). Keep the quotes
# around the regex. Write a dot as [.], because the filter parser removes
# backslashes. Add third-party services, for example:
#   PDA_SAVE="~d '(^|[.])(torn[.]com|yata[.]yt|tornstats[.]com)\$'"
PDA_SAVE=${PDA_SAVE:-"~d '(^|[.])torn[.]com\$'"}

# Where recordings go. Keep this outside the repository.
PDA_REC_DIR=${PDA_REC_DIR:-$HOME/pda-recordings}

# The app under test and the emulator snapshot that replay tests start from.
PDA_APP=${PDA_APP:-com.manuito.tornpda}
PDA_SNAPSHOT=${PDA_SNAPSHOT:-replay-ready}

# Files that the replay proxy serves at fixed URLs (see pda_replay.py): the test
# userscripts, and PDA's example scripts if they were saved (see the README).
if [ -z "${PDA_STATIC+x}" ]; then
  PDA_STATIC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/userscripts/static.json
  [ -f "$PDA_REC_DIR/userscripts/examples/static.json" ] && PDA_STATIC+=",$PDA_REC_DIR/userscripts/examples/static.json"
fi

# Maestro sends usage data unless this is set.
export MAESTRO_CLI_NO_ANALYTICS=1

# Starts replay.sh in the background with the given recordings and waits until it listens.
# Sets PROXY_PID. The caller stops it with stop_proxy.
start_proxy() {
  local log=$1
  shift
  # Python buffers output to a file. Without this, the "listening" line can wait for traffic.
  PYTHONUNBUFFERED=1 "$here/replay.sh" "$@" >"$log" 2>&1 &
  PROXY_PID=$!
  for _ in $(seq 1 100); do
    grep -q "listening" "$log" 2>/dev/null && return 0
    kill -0 "$PROXY_PID" 2>/dev/null || { cat "$log" >&2; return 1; }
    sleep 0.2
  done
  echo "The replay proxy did not start. See $log." >&2
  return 1
}

stop_proxy() {
  [ -n "${PROXY_PID:-}" ] && kill "$PROXY_PID" 2>/dev/null && wait "$PROXY_PID" 2>/dev/null
  PROXY_PID=
}

# Points the emulator at the proxy. Without this, the WebView would reach the live site.
use_proxy() {
  adb shell settings put global http_proxy "10.0.2.2:$PDA_PROXY_PORT"
}
