#!/usr/bin/env python3
"""Turns the perf records of several replay test runs into one baseline file.

    tools/perf/summarize.py RUN_DIR [RUN_DIR ...] -o baseline.json

Each RUN_DIR is a folder that tools/replay/run-test.sh made. The script reads its
perf.txt (and env.json, if present), joins the split logcat lines of each record, and
groups the records by page. A page is the URL without host, fragment and IDs, so that
the same step of a flow has the same name in every run. If a flow opens the same page
twice, the second visit is "<page> #2".

For each page and each number in its records, the output has the count of runs, the
median, p25, p75, min and max. Dart records (perf_trace.dart) give metrics that start
with "dart.", probe records (pda-perf-probe.user.js) give metrics that start with
"probe.". Lists (for example the probe's route segments) are not summarized.

Use the median to compare builds, and p25 to p75 to judge the noise.
"""

import argparse
import json
import re
import statistics
import sys
import urllib.parse
from pathlib import Path

LINE = re.compile(r"\[(PDA-PERF-DART|PDA-PERF-PROBE)\] (\d+) (\d+)/(\d+) (.*)$")
# Fields that identify a record, not measure it.
# "final" stays: 1 means the page was left before the 10 s report, so the probe's window was shorter.
SKIP = {"v", "ts", "timeOrigin", "url", "path", "ua", "env", "tab", "reason"}
# Query parameters that change on every request.
DROP_PARAMS = {"rfcv", "_", "timestamp", "t"}


def read_records(perf_txt: Path) -> list[tuple[str, dict]]:
    """Joins the parts of each record. Returns (kind, record) in log order."""
    parts: dict[tuple[str, str], dict[int, str]] = {}
    totals: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for line in perf_txt.read_text(errors="replace").splitlines():
        m = LINE.search(line)
        if not m:
            continue
        prefix, rid, part, total, text = m.groups()
        key = (prefix, rid)
        if key not in parts:
            parts[key] = {}
            order.append(key)
        parts[key][int(part)] = text
        totals[key] = int(total)
    out = []
    for key in order:
        got = parts[key]
        if len(got) != totals[key]:
            print(f"{perf_txt}: record {key[1]} has {len(got)} of {totals[key]} parts, skipped", file=sys.stderr)
            continue
        text = "".join(got[i] for i in sorted(got))
        try:
            rec = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"{perf_txt}: record {key[1]} is not JSON ({e}), skipped", file=sys.stderr)
            continue
        out.append(("dart" if key[0] == "PDA-PERF-DART" else "probe", rec))
    return out


def page_name(url: str) -> str | None:
    """The page of a URL, without IDs. None for pages that are not on Torn."""
    u = urllib.parse.urlsplit(url)
    if u.hostname != "www.torn.com":
        return None
    path = re.sub(r"/\d+(?=/|$)", "/N", u.path)
    params = []
    for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True):
        if k in DROP_PARAMS:
            continue
        if re.fullmatch(r"\d+", v):
            v = "N"
        elif re.fullmatch(r"[0-9a-f]{16,}", v):
            v = "H"
        params.append(f"{k}={v}")
    return path + ("?" + "&".join(params) if params else "")


def flatten(obj, prefix: str, out: dict[str, float]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not prefix and k in SKIP:
                continue
            flatten(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(obj, bool):
        out[prefix] = float(obj)
    elif isinstance(obj, (int, float)):
        out[prefix] = float(obj)
    elif isinstance(obj, str):
        # perf_trace.dart writes times as strings with one decimal.
        try:
            out[prefix] = float(obj)
        except ValueError:
            pass


def run_metrics(run: Path) -> dict[str, dict[str, float]]:
    """Metrics per page for one run."""
    pages: dict[str, dict[str, float]] = {}
    seen: dict[tuple[str, str], int] = {}
    for kind, rec in read_records(run / "perf.txt"):
        page = page_name(rec.get("url", ""))
        if page is None:
            continue
        n = seen[(kind, page)] = seen.get((kind, page), 0) + 1
        name = page if n == 1 else f"{page} #{n}"
        flat: dict[str, float] = {}
        flatten(rec, "", flat)
        pages.setdefault(name, {}).update({f"{kind}.{k}": v for k, v in flat.items()})
    return pages


def stats(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    if len(values) >= 2:
        q = statistics.quantiles(values, n=4, method="inclusive")
        p25, p75 = q[0], q[2]
    else:
        p25 = p75 = values[0]
    return {
        "n": len(values),
        "median": round(statistics.median(values), 2),
        "p25": round(p25, 2),
        "p75": round(p75, 2),
        "min": values[0],
        "max": values[-1],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+", type=Path, help="run folders of one flow")
    ap.add_argument("-o", "--output", type=Path, required=True, help="baseline file to write")
    args = ap.parse_args()

    envs = {}
    per_run = {}
    for run in args.runs:
        if not (run / "perf.txt").exists():
            print(f"{run}: no perf.txt (a crashed run?), skipped", file=sys.stderr)
            continue
        status = run / "status"
        if status.exists() and status.read_text().strip() != "passed":
            print(f"{run}: the test failed, skipped", file=sys.stderr)
            continue
        per_run[run.name] = run_metrics(run)
        env_file = run / "env.json"
        if env_file.exists():
            envs[run.name] = json.loads(env_file.read_text())
    # Runs on different builds or settings must not be mixed.
    distinct = {json.dumps({k: v for k, v in e.items() if k != "time"}, sort_keys=True) for e in envs.values()}
    if len(distinct) > 1:
        sys.exit("The runs have different env.json values (build, WebView or settings). Summarize them apart.")

    values: dict[str, dict[str, list[float]]] = {}
    for pages in per_run.values():
        for page, metrics in pages.items():
            for metric, v in metrics.items():
                values.setdefault(page, {}).setdefault(metric, []).append(v)

    baseline = {
        "runs": sorted(per_run),
        "env": json.loads(distinct.pop()) if distinct else None,
        "pages": {
            page: {metric: stats(v) for metric, v in sorted(metrics.items())}
            for page, metrics in sorted(values.items())
        },
    }
    args.output.write_text(json.dumps(baseline, indent=1) + "\n")

    print(f"{len(per_run)} runs, written to {args.output}")
    for page, metrics in baseline["pages"].items():
        print(f"\n{page}")
        for metric in ("probe.nav.load", "probe.probeStart", "probe.bridge.firstAt", "dart.counts.getHtml",
                       "dart.counts.setState", "dart.lag.over50"):
            s = metrics.get(metric)
            if s:
                print(f"  {metric:24} median {s['median']:>9}  p25 {s['p25']:>9}  p75 {s['p75']:>9}  n {s['n']}")


if __name__ == "__main__":
    main()
