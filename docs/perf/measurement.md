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

1. In Torn PDA, open Settings, then Userscripts. Add `tools/perf/pda-perf-probe.user.js` as a new script. Keep the `@run-at document-start` header.
2. In Firefox for Android, install Tampermonkey. Add the same file as a new script.
3. In each browser, open the same list of pages. Open each page three times. The first visit fills the cache. Use the second and third visits for warm-cache numbers.
4. Wait at least 10 seconds on each page. The probe writes its record 10 seconds after the `load` event.
5. Tap the badge at the bottom left of the page. Tap "Copy all" and paste the JSON into a file, for example `pda.json` and `firefox.json`.

Compare these fields first.

| Field | What a large difference means |
|-------|-------------------------------|
| `probeStart` | Injection happens late. In Tampermonkey, document-start is close to 0. |
| `nav.dcl`, `nav.load` | The page itself is slower to parse or load. |
| `res.cacheRatio` | Near 0 on a repeat visit means that the HTTP cache is off. |
| `longTasks.total` | Main-thread JavaScript blocks the page. Chromium only. |
| `hooks.*Injected` | Injected code (PDA built-ins or userscripts) adds observers and timers. |
| `bridge.byName` | The number and round-trip time of calls from JavaScript to Dart. PDA only. |
| `interactions.max`, `interactions.p75` | Taps and key presses are slow to paint a response. |
| `frames.scrollGaps50` | Frames over 50 ms during scrolls, measured in the page. |

Two warnings apply to the probe.

- The `hooks` section wraps `MutationObserver` and `setInterval`. This adds a small overhead. If you suspect that the overhead changes the result, set `HOOKS = false` at the top of the script.
- Firefox does not report `longtask` or `largest-contentful-paint` in all versions. Those fields stay at 0 or empty there. Compare them only between PDA builds.

## 2. Dart trace (Torn PDA only)

Build a profile build with the flag. A profile build is optimized like a release build but keeps the tracing hooks.

```bash
flutter run --profile --dart-define=PDA_PERF=true
```

For each navigation in each tab, the app logs one line that starts with `[PDA-PERF-DART]`. The line contains:

- `cb`: for each WebView callback, the number of calls, the synchronous Dart time, and the total time until its `Future` completed (this includes awaited platform calls),
- `counts.setState`: the number of `setState` calls on the `WebViewFull` state, which rebuilds the whole browser widget,
- `counts.WebViewProvider.notify`: the number of `notifyListeners` calls on `WebViewProvider`,
- `frames`: Flutter frames rendered, frames with UI or raster time over 16 ms, and the average UI and raster time.

The flag also turns on Flutter's `debugProfilePlatformChannels`. Flutter then logs the platform channel traffic by channel and method once per second. Use it to count `evaluateJavascript`, `getUrl`, `onLoadResource` and other messages per page load.

To read the log, run:

```bash
adb logcat | grep -E 'PDA-PERF|Platform Channel'
```

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
