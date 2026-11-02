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

    tools/perf/summarize.py RUN_DIR [RUN_DIR ...] -o new.json --compare baseline.json

With --compare, the script also compares the new summary with an older one of the same
flow. For each main metric (MAIN) and each --metric, it prints the old and the new median
with p25 to p75, and a p-value from a rank test (Mann-Whitney) on the per-run values. A change
with p < 0.05 is marked. Test only the metrics that a fix must change: the more metrics
you test, the more false marks you get.

The emulator drifts during a session. Thus run the two builds in alternation (A, B, A, B),
not one after the other.
"""

import argparse
import itertools
import json
import math
import random
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
# Metrics that the printout always shows.
MAIN = ("probe.nav.load", "probe.injectAfterTtfb", "probe.bridge.firstAt", "dart.counts.getHtml",
        "dart.counts.setState", "dart.lag.over50")
# env.json fields that change with the build. A comparison expects them to differ.
BUILD_ENV = {"pda_commit", "apk_sha256", "app_installed", "app_version"}
# env.json fields that may differ between runs of one build. A run with PDA_APK installs the
# build again, which changes the install time.
RUN_ENV = {"time", "app_installed"}
ALPHA = 0.05


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
        # probeStart counts from the navigation start, so it includes the server time.
        # The injection delay is the time after the first byte.
        if "probeStart" in flat and "nav.ttfb" in flat:
            flat["injectAfterTtfb"] = round(flat["probeStart"] - flat["nav.ttfb"], 1)
        pages.setdefault(name, {}).update({f"{kind}.{k}": v for k, v in flat.items()})
    return pages


def stats(values: list[float]) -> dict:
    """Summary of one metric. "values" keeps the runs in time order for the comparison."""
    ordered = sorted(values)
    if len(ordered) >= 2:
        q = statistics.quantiles(ordered, n=4, method="inclusive")
        p25, p75 = q[0], q[2]
    else:
        p25 = p75 = ordered[0]
    return {
        "n": len(ordered),
        "median": round(statistics.median(ordered), 2),
        "p25": round(p25, 2),
        "p75": round(p75, 2),
        "min": ordered[0],
        "max": ordered[-1],
        "values": values,
    }


def ranks(values: list[float]) -> list[float]:
    """Rank of each value, from 1. Equal values get the mean of their ranks."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def permutation_p(a: list[float], b: list[float], samples: int = 10000) -> float:
    """Two-sided p-value that a and b come from the same distribution (Mann-Whitney).

    The statistic is the rank sum of a. The p-value is the share of all splits of the pooled
    runs into groups of len(a) and len(b) whose rank sum is as far from the mean as the real
    one. Ranks keep one slow run from hiding a change. The result is exact when there are
    few splits, otherwise it comes from a fixed random sample, so the same input always gives
    the same p.
    """
    r = ranks(a + b)
    expected = len(a) * (len(r) + 1) / 2
    observed = abs(sum(r[: len(a)]) - expected)
    if observed == 0:
        return 1.0
    idx = range(len(r))
    if math.comb(len(r), len(a)) <= 20000:
        splits = itertools.combinations(idx, len(a))
        total = math.comb(len(r), len(a))
    else:
        rng = random.Random(0)
        splits = (rng.sample(idx, len(a)) for _ in range(samples))
        total = samples
    hits = sum(1 for c in splits if abs(sum(r[i] for i in c) - expected) >= observed - 1e-9)
    return hits / total


def compare(old: dict, new: dict, checked: set[str], show_all: bool = False) -> list[str]:
    """Lines that compare two summaries page by page.

    Only the checked metrics get a mark. With about 80 metrics per page, a 5 % test marks
    about four of them on two identical builds, so marks on other metrics mean nothing.
    show_all also lists the other metrics with p < ALPHA, without a mark.
    """
    old_env, new_env = old.get("env") or {}, new.get("env") or {}
    if old_env.get("recordings") != new_env.get("recordings"):
        sys.exit("The two summaries come from different recordings (another flow?). Compare runs of the same flow.")
    for k in sorted((set(old_env) | set(new_env)) - BUILD_ENV - {"recordings"}):
        if old_env.get(k) != new_env.get(k):
            print(f"warning: env.json {k} differs: {old_env.get(k)!r} -> {new_env.get(k)!r}", file=sys.stderr)

    lines = [
        f"pda_commit {old_env.get('pda_commit')} -> {new_env.get('pda_commit')}",
        f"Columns: old median [p25-p75] -> new median [p25-p75], change, p. Marked: p < {ALPHA}.",
    ]
    for page in sorted(set(old["pages"]) | set(new["pages"])):
        if page not in new["pages"]:
            lines.append(f"\n{page}\n  only in the old summary")
            continue
        if page not in old["pages"]:
            lines.append(f"\n{page}\n  only in the new summary")
            continue
        o, n = old["pages"][page], new["pages"][page]
        lines.append(f"\n{page}")
        for metric in sorted(set(o) & set(n), key=lambda m: (m not in checked, m)):
            if "values" not in o[metric] or "values" not in n[metric]:
                sys.exit("A summary has no per-run values. Make it again with this version of the script.")
            p = permutation_p(o[metric]["values"], n[metric]["values"])
            if metric not in checked and not (show_all and p < ALPHA):
                continue
            a, b = o[metric], n[metric]
            pct = f"{(b['median'] - a['median']) / a['median'] * 100:+.1f} %" if a["median"] else ""
            mark = ""
            if metric in checked and p < ALPHA:
                mark = "higher" if b["median"] > a["median"] else "lower"
            lines.append(
                f"  {metric:40} {a['median']:>8} [{a['p25']}-{a['p75']}] -> {b['median']:>8} [{b['p25']}-{b['p75']}]"
                f" {pct:>9}  p {p:.3f}  {mark}"
            )
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+", type=Path, help="run folders of one flow")
    ap.add_argument("-o", "--output", type=Path, required=True, help="baseline file to write")
    ap.add_argument("--compare", type=Path, metavar="BASELINE", help="older summary to compare with")
    ap.add_argument("--metric", action="append", default=[],
                    help="with --compare, also test this metric, for example dart.cb.onLoadStop.wallMs (repeatable)")
    ap.add_argument("--all", action="store_true",
                    help="with --compare, also list other metrics with p < 0.05 (not marked: expect false positives)")
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
    if not per_run:
        sys.exit("No run has usable perf records.")
    # Runs on different builds or settings must not be mixed.
    distinct = {json.dumps({k: v for k, v in e.items() if k not in RUN_ENV}, sort_keys=True) for e in envs.values()}
    if len(distinct) > 1:
        sys.exit("The runs have different env.json values (build, WebView or settings). Summarize them apart.")

    values: dict[str, dict[str, list[float]]] = {}
    for name in sorted(per_run):
        for page, metrics in per_run[name].items():
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
    if args.compare:
        print(f"Compared with {args.compare}:")
        print("\n".join(compare(json.loads(args.compare.read_text()), baseline, set(MAIN) | set(args.metric), args.all)))
        return
    for page, metrics in baseline["pages"].items():
        print(f"\n{page}")
        for metric in MAIN:
            s = metrics.get(metric)
            if s:
                print(f"  {metric:24} median {s['median']:>9}  p25 {s['p25']:>9}  p75 {s['p75']:>9}  n {s['n']}")


if __name__ == "__main__":
    main()
