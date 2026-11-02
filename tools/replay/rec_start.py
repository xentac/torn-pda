"""Prints the UTC time of the first request in a recording, for emu-clock.sh.

    python3 rec_start.py RECORDING.mitm
"""

import datetime
import sys

from mitmproxy import http, io

with open(sys.argv[1], "rb") as f:
    first = min(fl.request.timestamp_start for fl in io.FlowReader(f).stream() if isinstance(fl, http.HTTPFlow))
print(datetime.datetime.fromtimestamp(first, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
