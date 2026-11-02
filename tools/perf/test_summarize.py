"""Tests for summarize.py. All data here is made up.

    python3 -m pytest tools/perf
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import summarize  # noqa: E402

SCRIPT = Path(__file__).parent / "summarize.py"
URL = "https://www.torn.com/profiles.php?XID=1234567"
ENV = {"recordings": "a.mitm", "webview": "133", "mitm_args": "", "pda_commit": "x"}


def make_runs(root: Path, arm: str, loads: list[float], get_html: list[int], commit: str) -> list[Path]:
    runs = []
    for i, (load, gh) in enumerate(zip(loads, get_html)):
        run = root / f"2026110{i}T000000Z-{arm}"
        run.mkdir()
        dart = json.dumps({"url": URL, "counts": {"getHtml": gh, "setState": 20}})
        probe = json.dumps({"url": URL, "nav": {"load": load, "ttfb": 100}, "probeStart": 130})
        # The second record is split in two parts, as perf_trace.dart does with long records.
        (run / "perf.txt").write_text(
            f"I flutter: [PDA-PERF-DART] {i} 1/1 {dart}\n"
            f"I chromium: [PDA-PERF-PROBE] {i} 1/2 {probe[:20]}\n"
            f"I chromium: [PDA-PERF-PROBE] {i} 2/2 {probe[20:]}\n"
        )
        (run / "status").write_text("passed\n")
        (run / "env.json").write_text(json.dumps({**ENV, "pda_commit": commit}))
        runs.append(run)
    return runs


def summarize_runs(runs: list[Path], out: Path, *extra: str) -> str:
    res = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, runs), "-o", str(out), *extra],
        capture_output=True, text=True, check=True,
    )
    return res.stdout


def main_lines(output: str) -> dict[str, str]:
    return {line.split()[0]: line for line in output.splitlines() if line.startswith("  ")}


def test_records_are_joined_and_grouped(tmp_path):
    runs = make_runs(tmp_path, "a", [1000, 1100, 1200], [12, 12, 13], "x")
    summarize_runs(runs, tmp_path / "a.json")
    page = json.loads((tmp_path / "a.json").read_text())["pages"]["/profiles.php?XID=N"]
    assert page["probe.nav.load"]["median"] == 1100
    assert page["probe.nav.load"]["values"] == [1000, 1100, 1200]
    assert page["probe.injectAfterTtfb"]["median"] == 30
    assert page["dart.counts.getHtml"]["median"] == 12


def test_same_build_gets_no_mark(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    loads = [1000, 1150, 1080, 1300, 990, 1210, 1120, 1050]
    a = make_runs(tmp_path / "a", "a", loads[0::2] + loads[1::2], [12, 12, 13, 12, 12, 12, 13, 12], "x")
    b = make_runs(tmp_path / "b", "b", loads[1::2] + loads[0::2], [12, 13, 12, 12, 12, 12, 12, 13], "y")
    summarize_runs(a, tmp_path / "a.json")
    out = summarize_runs(b, tmp_path / "b.json", "--compare", str(tmp_path / "a.json"))
    lines = main_lines(out)
    assert "probe.nav.load" in lines and "dart.counts.getHtml" in lines
    assert not any(line.rstrip().endswith(("higher", "lower")) for line in lines.values())


def test_real_change_gets_a_mark(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    loads = [1000, 1150, 1080, 1300, 990, 1210, 1120, 1050]
    a = make_runs(tmp_path / "a", "a", loads, [12, 12, 13, 12, 12, 12, 13, 12], "x")
    b = make_runs(tmp_path / "b", "b", [v * 0.8 for v in loads], [2, 2, 2, 2, 2, 2, 2, 2], "y")
    summarize_runs(a, tmp_path / "a.json")
    out = summarize_runs(b, tmp_path / "b.json", "--compare", str(tmp_path / "a.json"))
    lines = main_lines(out)
    assert lines["dart.counts.getHtml"].rstrip().endswith("lower")
    assert lines["probe.nav.load"].rstrip().endswith("lower")
    assert "pda_commit x -> y" in out


def test_other_flow_is_refused(tmp_path):
    (tmp_path / "a").mkdir()
    a = make_runs(tmp_path / "a", "a", [1000, 1100], [12, 12], "x")
    summarize_runs(a, tmp_path / "a.json")
    other = json.loads((tmp_path / "a.json").read_text())
    other["env"]["recordings"] = "b.mitm"
    (tmp_path / "other.json").write_text(json.dumps(other))
    res = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, a), "-o", str(tmp_path / "c.json"), "--compare", str(tmp_path / "other.json")],
        capture_output=True, text=True,
    )
    assert res.returncode != 0
    assert "different recordings" in res.stderr


def test_permutation_p():
    assert summarize.permutation_p([1, 1, 1, 1], [1, 1, 1, 1]) == 1.0
    # Full separation of 4 and 4 runs: 2 of the 70 splits are as extreme.
    assert abs(summarize.permutation_p([1, 2, 3, 4], [11, 12, 13, 14]) - 2 / 70) < 1e-9
    # Above 20000 splits, the result comes from a fixed sample.
    a, b = list(range(12)), list(range(5, 17))
    assert summarize.permutation_p(a, b) == summarize.permutation_p(a, b)


def test_userscript_times_get_derived_metrics(tmp_path):
    run = tmp_path / "20261101T000000Z-us"
    run.mkdir()
    us = {
        "start": {"callAt": 300, "readyAt": 1000, "answerAt": 1100},
        "endAll": {"start": 1060},
        "endProfile": {"start": 1100},
    }
    probe = json.dumps({"url": URL, "nav": {"load": 980, "ttfb": 100}, "probeStart": 130, "us": us})
    (run / "perf.txt").write_text(f"I chromium: [PDA-PERF-PROBE] 1 1/1 {probe}\n")
    page = summarize.run_metrics(run)["/profiles.php?XID=N"]
    assert page["probe.us.start.waitMs"] == 700
    assert page["probe.us.start.rttMs"] == 800
    assert page["probe.us.endAll.afterLoad"] == 80
    assert page["probe.us.endGapMs"] == 40
