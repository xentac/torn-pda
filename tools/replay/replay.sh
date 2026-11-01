#!/usr/bin/env bash
# Answer PDA from anonymized recordings. Nothing is forwarded to Torn.
#   tools/replay/replay.sh ANON.mitm [MORE.mitm ...]
# Misses go to <first recording>.misses.jsonl, or to $PDA_MISSES.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/common.sh"
[ $# -ge 1 ] || { echo "usage: replay.sh ANON.mitm [MORE.mitm ...]" >&2; exit 2; }
recs=$(IFS=,; echo "$*")
misses=${PDA_MISSES:-${1%.mitm}.misses.jsonl}
exec mitmdump --listen-port "$PDA_PROXY_PORT" \
  --set connection_strategy=lazy --set upstream_cert=false \
  --ignore-hosts "$PDA_PASSTHROUGH" \
  -s "$here/pda_replay.py" --set pda_replay="$recs" --set pda_replay_misses="$misses" \
  ${MITM_ARGS:-}
