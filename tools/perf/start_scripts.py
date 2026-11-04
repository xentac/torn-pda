# Prints, for each probe record, the page, the navigation type and the start test scripts that ran.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize import read_records
for kind, r in read_records(Path(sys.argv[1])):
    if kind != "probe":
        continue
    us = r.get("us") or {}
    nav = r.get("nav") or {}
    print(r.get("path"), nav.get("type"), "load", nav.get("load"),
          {k: v.get("start") for k, v in us.items() if k.startswith("start")})
