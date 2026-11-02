#!/usr/bin/env bash
# Record a capture session. A person plays, the proxy only listens.
#   tools/replay/capture.sh LABEL
# Writes $PDA_REC_DIR/raw/<UTC time>-LABEL.mitm and a .json manifest next to it.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/common.sh"
label=${1:?usage: capture.sh LABEL}
raw="$PDA_REC_DIR/raw"
mkdir -p "$raw"
chmod 700 "$PDA_REC_DIR" "$raw"
out="$raw/$(date -u +%Y%m%dT%H%M%SZ)-$label.mitm"

# Files in the WebView cache are not requested, so a capture would miss them and a
# replay (which starts with an empty cache) would break. Clear the HTTP cache first.
# Cookies are kept, so the login stays. Set PDA_KEEP_CACHE=1 to skip this.
if [ -z "${PDA_KEEP_CACHE:-}" ]; then
  adb root >/dev/null
  adb wait-for-device
  adb shell am force-stop com.manuito.tornpda
  adb shell rm -rf "'/data/data/com.manuito.tornpda/cache/WebView/Default/HTTP Cache'"
  echo "Cleared the WebView HTTP cache. Start PDA again after the proxy is up."
fi
echo "Recording to $out"
# Connect to a server only for a request that goes there, so that marks never reach Torn.
exec mitmdump --listen-port "$PDA_PROXY_PORT" --set connection_strategy=lazy \
  --ignore-hosts "$PDA_PASSTHROUGH" \
  -s "$here/pda_capture.py" --set pda_manifest="$out.json" \
  -w "$out" --set save_stream_filter="$PDA_SAVE" \
  ${MITM_ARGS:-}
