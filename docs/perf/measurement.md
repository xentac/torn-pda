# Measuring browser performance

This page describes the measurement tools in `tools/perf/` and in `lib/utils/perf/`. Use it to get a baseline before you change code, and to compare each change against that baseline.

The tools have three parts. Each part sees a different layer of the app.

| Part | Layer | Needs a custom build |
|------|-------|----------------------|
| `tools/perf/pda-perf-probe.user.js` | Page JavaScript: load timing, long tasks, interaction latency, bridge calls | No |
| `lib/utils/perf/perf_trace.dart` | Dart: callback counts and time, `setState` count, Flutter frame timing, platform channel traffic | Yes (`--dart-define=PDA_PERF=true`) |
| `tools/perf/adb-bench.sh` | Whole app: frame pacing during scrolls, memory, CPU | No |

## 1. Page probe (Torn PDA and Firefox)

The probe is a userscript that runs at document start. It runs without changes in Torn PDA and in Tampermonkey or Violentmonkey. This lets you compare the two browsers on the same pages with the same code.

1. In Torn PDA, open Settings, then Userscripts. Add `tools/perf/pda-perf-probe.user.js` as a new script. Keep the `@run-at document-start` header. A `PDA_PERF` build (see section 2) injects the probe itself, before PDA's own scripts. With such a build, do not add the script.
2. In Firefox for Android, install Tampermonkey. Add the same file as a new script.
3. In each browser, open the same list of pages. Open each page three times. The first visit fills the cache. Use the second and third visits for warm-cache numbers.
4. Wait at least 10 seconds on each page. The probe writes its record 10 seconds after the `load` event, and keeps the last 50 records.
5. Tap the badge at the bottom left of the page. Tap "Copy all" and paste the JSON into a file, for example `pda.json` and `firefox.json`.

Compare these fields first.

| Field | What a large difference means |
|-------|-------------------------------|
| `probeStart` | Injection happens late. In Tampermonkey, document-start is close to 0. |
| `tap.tapToNavStart`, `tap.tapToTtfb` | Time from your tap on the previous page to the start of the new document and to its first byte. This includes the time that the app holds the navigation before the request starts. |
| `nav.dcl`, `nav.load` | The page itself is slower to parse or load. |
| `res.cacheRatio` | Near 0 on a repeat visit means that the HTTP cache is off. |
| `longTasks.total` | Main-thread JavaScript blocks the page. Chromium only. |
| `hooks.*Injected` | Injected code (PDA built-ins or userscripts) adds observers and timers. |
| `bridge.byName` | The number and round-trip time of calls from JavaScript to Dart. PDA only. `bridge.byName.onLoadResource.n` counts the plugin messages for subresources. |
| `bridge.firstAt` | The time of the first call to Dart, for example the first `PDA_httpGet` of a userscript. |
| `segments` | For each route change in a single-page part of Torn, the long tasks, bridge calls and frame gaps in the next 3 seconds. |
| `interactions.max`, `interactions.p75` | Taps and key presses are slow to paint a response. |
| `frames.scrollGaps50` | Frames over 50 ms during scrolls, measured in the page. |

Two warnings apply to the probe.

- The `hooks` section wraps `MutationObserver` and `setInterval`. This adds a small overhead. If you suspect that the overhead changes the result, set `HOOKS = false` at the top of the script.
- In PDA, code that the app registers before this script runs first. Observers that this code creates at document start are not in `hooks`. As a userscript, the probe runs after the plugin bridge and the PDA handler bundle. In a `PDA_PERF` build, it runs after the plugin bridge only.
- If you change the probe, run `tools/perf/gen-probe.sh`. It writes the copy that `PDA_PERF` builds inject (`lib/utils/perf/probe_source.g.dart`).
- The tap fields need two pages in the same tab. The probe stores the tap time in `sessionStorage` and ignores taps older than 15 seconds.
- Firefox does not report `longtask` or `largest-contentful-paint` in all versions. Those fields stay at 0 or empty there. Compare them only between PDA builds.

## 2. Dart trace (Torn PDA only)

Build a profile build with the flag. A profile build is optimized like a release build but keeps the tracing hooks.

```bash
flutter run --profile --dart-define=PDA_PERF=true
```

For each navigation in each tab, the app logs one line that starts with `[PDA-PERF-DART]`. The line contains:

- `cb`: for each WebView callback, the number of calls and two times. `syncMs` is the synchronous Dart time. `wallMs` is the time until its `Future` completed. Wall time includes awaited platform calls and delays, so it measures latency, not cost. `shouldOverrideUrlLoading` fires before `onLoadStart`, so it shows up in the next record as `shouldOverrideUrlLoading(preNav)`.
- `counts.getHtml`: the number of full-page HTML copies that Dart requested,
- `counts.setState`: the number of `setState` calls on the `WebViewFull` state, which rebuilds the whole browser widget,
- `counts.WebViewProvider.notify`: the number of `notifyListeners` calls on `WebViewProvider`,
- `frames`: Flutter frames rendered, frames with UI or raster time over 16 ms, and the average UI and raster time,
- `lag`: how late a 16 ms Dart timer fired. This shows main-thread work between frames, such as HTML parsing, channel handlers and storage, that `frames` does not see.

`frames` and `lag` are process-wide. They appear only in the record of the tab that started the most recent navigation. Do not add them up across tabs. A callback that finishes after its record was written is counted in `latePrev` of the next record of the same tab. The late callbacks of the last page in a tab are not written.

The flag also turns on Flutter's `debugProfilePlatformChannels`. Flutter then logs the platform channel traffic by channel and method once per second. Use it to count `evaluateJavascript`, `getUrl`, `onLoadResource` and other messages per page load.

The same build also writes each record of the page probe (section 1) with the prefix `[PDA-PERF-PROBE]`. It takes these records from the console, so they do not go to PDA's terminal.

`dart:developer` logs do not reach logcat, so the app writes each record twice: to the developer log (DevTools), and to logcat with `print`. Flutter cuts logcat lines at about 1 KB, so the logcat copy is split into lines of this form:

```text
[PDA-PERF-DART] <id> <part>/<parts> <text>
```

To get a record, join the text of all parts of one id, in order. To read the log, run:

```bash
adb logcat | grep -E 'PDA-PERF-(DART|PROBE)|Platform Channel'
```

The replay tests (`tools/replay/run-test.sh`) save these lines in `perf.txt` in each run folder. They also write `env.json`: the app version and install time, the WebView version, the AVD, the snapshot, the recordings and `MITM_ARGS`.

To make a baseline from several runs of one flow, run:

```bash
tools/perf/summarize.py ~/pda-recordings/runs/*-faction -o baseline-faction.json
```

The script joins the parts of each record and groups the records by page (the URL without host, fragment and IDs). For each number in the records, it writes the median, p25, p75, min and max over the runs, and the per-run values. If the runs have different `env.json` values, the script stops.

### Comparing two builds

The emulator drifts during a session. In one session, the same build got 10 % faster from the first runs to the last runs. Thus do not run the old build first and the new build after it. Run them in alternation in one session, with `PDA_APKS` (see `tools/replay/README.md`). Each run folder name then ends in the build name.

1. Summarize the runs of each build:

   ```bash
   tools/perf/summarize.py ~/pda-recordings/runs/*-attack-50a4a3d9 -o old.json
   ```

2. Summarize the runs of the new build, and compare them with the old summary. Name the metric that the fix must change with `--metric`:

   ```bash
   tools/perf/summarize.py ~/pda-recordings/runs/*-attack-1a2b3c4d -o new.json --compare old.json --metric dart.cb.onLoadStop.wallMs
   ```

For each page, the comparison shows the old and the new median with p25 to p75, the change, and a p-value. The p-value comes from a rank test (Mann-Whitney) on the per-run values. A change with p < 0.05 is marked `higher` or `lower`. The script tests only the main metrics and the `--metric` names. A page has about 80 metrics, and a test at p < 0.05 marks about 4 of them on two identical builds. `--all` also lists the other metrics with p < 0.05, without a mark. Read them as leads, not as results.

Runs with `PDA_APKS` install the build and start PDA again before the flow. Their start state is not the same as in runs without an install. Thus compare `PDA_APKS` runs only with `PDA_APKS` runs of the same session, not with a saved baseline.

With 4 runs per build, the smallest possible p-value is 0.029. Use at least 6 runs per build. If the two summaries come from different recordings, the script stops. If other `env.json` values differ, for example the WebView version, it prints a warning.

## 3. Whole-app bench (adb)

`tools/perf/adb-bench.sh` opens a list of URLs with a VIEW intent, scrolls each page with `adb shell input swipe`, and saves frame, memory and CPU data.

```bash
tools/perf/adb-bench.sh -n 3 -o perf-results com.manuito.tornpda
tools/perf/adb-bench.sh -n 3 -o perf-results org.mozilla.firefox
```

The script writes `perf-results/<package>/summary.tsv`. Use the `janky_pct`, `p90_ms` and `p99_ms` columns for Torn PDA builds. For Firefox, gfxinfo does not see GeckoView content frames in the same way. Compare Firefox with the probe's `frames` data instead.

For a deeper look, record a Perfetto trace while you scroll. Open it in https://ui.perfetto.dev and look at the Flutter `1.ui` and `1.raster` threads, the `CrRendererMain` thread of the WebView, and the `RenderThread` of the app.

```bash
adb shell perfetto -o /data/misc/perfetto-traces/pda.pftrace -t 20s \
  sched freq idle am wm gfx view webview binder_driver hal dalvik input res
adb pull /data/misc/perfetto-traces/pda.pftrace
```

## Rules for a fair comparison

- Use the same device, the same network, and the same Torn account for every run.
- Close other apps. Keep the device on a charger and at a stable temperature.
- Keep the same set of userscripts enabled between the PDA and Firefox runs.
- Use at least three runs per page. Report the median, not the best run.
- Record the PDA version, the WebView version (Settings, Apps, Android System WebView), and the Firefox version with each result.
