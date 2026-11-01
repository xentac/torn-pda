# Shared settings for capture.sh and replay.sh. Source it, do not run it.

# Port that mitmproxy listens on. The emulator reaches the host at 10.0.2.2.
PDA_PROXY_PORT=${PDA_PROXY_PORT:-8080}

# Hosts that pass through without interception, in capture and in replay.
# Firebase and Google services do not need recording, and their traffic holds
# Google account tokens. They also stay live during replay, so the app starts.
PDA_PASSTHROUGH=${PDA_PASSTHROUGH:-'^(.+\.)?(google|googleapis|gstatic|googleusercontent|firebaseio|firebaseapp|crashlytics|app-measurement|doubleclick)\.(com|net|io)(:[0-9]+)?$'}

# Hosts whose flows capture.sh saves (a mitmproxy filter). Add third-party
# services, for example: PDA_SAVE='~d (^|\.)(torn\.com|yata\.yt|tornstats\.com)$'
PDA_SAVE=${PDA_SAVE:-'~d (^|\.)torn\.com$'}

# Where recordings go. Keep this outside the repository.
PDA_REC_DIR=${PDA_REC_DIR:-$HOME/pda-recordings}
