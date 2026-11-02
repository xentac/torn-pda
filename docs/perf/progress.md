# Progress notes

This file records where the performance work stands, so that a new session can
continue. The plan is in `report.md`. The record and replay tools are in
`tools/replay/`, and their README explains how to use them.

Last update: 2026-11-02 (fourth session, PR #501 opened).

## State

- Branch `perf/analysis`, based on `origin/develop` at `fe76815d`. It is on
  the fork (`xentac/perf/analysis`) since 2026-11-02. Ask before each push to
  the fork. Never push upstream. Before the first push, one commit was
  rewritten to keep a security detail out of the public history. The old
  history is in the local branch `perf/analysis-backup`. Never push that
  branch.
- The report is published as a shared artifact:
  https://claude.ai/artifact/GCojySixXsQJxfYYTqNxfK (version 13). The source is
  `report.md`.
- Track T (record and replay) works from start to finish on the emulator:
  capture, anonymize, snapshot, automated test run. Three flows pass:
  `attack.yaml`, `faction.yaml` and `crimes.yaml`. Track 0 (baseline timing)
  done: all six steps of "Next steps: the baseline" below. The first
  baseline is in `~/pda-recordings/baselines/d20df8c8-profile/` (one file
  per flow, 8 runs each, not in git).
- The user approved the report on 2026-11-02, with the comments answered.
  Follow the plan until the upstream developer gives feedback.
- The report also has the URL
  https://claude.ai/code/artifact/7b1f1105-0a76-480b-8da4-f970a44e4532.
  Comments arrive there. Version 5 answers four comments (1.6 storage trim,
  1.7 share of users with scripts, 1.8 history of the 2-second
  deduplication, 1.9 private chat engine).

## Environment

- The dev shell comes from `~/coding/infra/nixos-config#torn-pda` (direnv).
- For the replay tools, use a Python with mitmproxy:
  `nix shell --impure --expr 'with import <nixpkgs> {}; python3.withPackages (p: [p.mitmproxy p.pytest p.pytest-asyncio])'`.
  Maestro comes from `nix shell nixpkgs#maestro`.
- Emulator: AVD `dev` (`google_apis`, API 36, x86_64, `hw.keyboard=yes`). The
  software renderers crash it. Start it with the host GPU:

  ```sh
  LD_LIBRARY_PATH=/run/opengl-driver/lib emulator -avd dev -gpu host -no-snapshot-load
  ```

- The mitmproxy CA is in `~/.mitmproxy` (valid from 2026-10-30) and is
  installed on the emulator as a user certificate. Do not make a new CA.
- The installed APK is a debug build with `--dart-define=PDA_PROXY=10.0.2.2:8080`.
  A proxy must run whenever PDA is used on the emulator.
- Emulator snapshots:
  - `live-ready`: your real key and website login. Load it before a capture.
    Never load it for a replay run.
  - `replay-ready`: the fake user, built by `make-snapshot.sh`. Tests start
    from it.
- Recordings, `identity.json` and `idmap.json` are in `~/pda-recordings`, never
  in git. The fake PDA key is in `idmap.json`: it is the only `keys` value
  with 16 characters.

## Recordings

| Anonymized file | Raw capture | Usable for replay |
|---|---|---|
| `anon/onboarding.mitm` | `20261102T013938Z-onboarding` | Yes. API calls only. |
| `anon/faction.mitm` | `20261102T025600Z-faction` | Yes. Flow: `flows/faction.yaml`, with every tab and the clicks from the capture. The 9mm Uzi tap does not open its 3D view yet. |
| `anon/crimes.mitm` | `20261102T025850Z-crimes` | Yes. Flow: `flows/crimes.yaml` (hub, Search for Cash, Graffiti, two arson collects, Cracking). |
| `anon/attack.mitm` | `20261102T035242Z-attack` | Yes. Profile, attack, four hits with the Macana, hospitalize, attack log. Flow: `flows/attack.yaml`. |

All four files were anonymized again on 2026-11-01 after two anonymizer fixes
(see the lessons). The old files held the real player ID in the websocket
login tokens and are deleted. `idmap.before-cleanup.json` is the map before
the short IDs were removed.

`20261102T015221Z-navigation` and the other early raw files are not
anonymized and were captured with a warm cache. They can be deleted.

## How a test works

A recording is a set of answers, not a script. A replay test does only what
its Maestro flow tells it to do. When the flow requests a page or an action
that is in the recording, the proxy answers it. So each capture needs a flow
that repeats the same steps, for example `flows/faction.yaml` for the faction
capture.

```sh
tools/replay/run-test.sh tools/replay/flows/faction.yaml ~/pda-recordings/anon/faction.mitm ~/pda-recordings/anon/onboarding.mitm
```

## Lessons from the first captures

- The WebView does not request cached files, so captures must start with a
  cleared HTTP cache. `capture.sh` does this.
- Torn's speculation rules make the WebView prefetch links, and Cloudflare
  answers the prefetches with an empty 503 (`cf-speculation-refused`). Replay
  keeps prefetches and page loads apart. For the report: every prefetch is
  wasted work in PDA.
- Torn's scripts read the `uid` and `rfc_v` cookies. Replay sets the recorded,
  anonymized cookies.
- Torn's crimes page posts a second 32-character `apiKey` in multipart forms.
  The anonymizer replaces credential fields in every form format.
- PDA's tips are invisible to Maestro, appear after a delay, and close only on
  a tap on their target. `make-snapshot.sh` closes them through adb.
- The sidebar polls `sidebarAjaxAction.php?action=servertime` every few
  seconds. Worth a look in the report.
- The profile page shows one more PDA tip, on the green person icon above the
  page. Until it closes, it takes every tap on the page. `make-snapshot.sh` now
  opens a profile (`flows/open-profile.yaml`) and closes it. The script needs
  the attack recording as its third argument.
- Torn's attack page posts every fight step as a multipart form to one URL.
  Replay compares form fields, not the raw body, because the boundary string
  is random.
- The attack page polls every 4 seconds. A poll at another moment than in the
  capture got an old "not started" answer and ended the fight. Replay now never
  goes back in recorded time on one URL, and logs such answers as `state`.
- Fights run on real time. After the last hit, the page gives 30 seconds to
  choose and then sends "leave" by itself. Maestro waits for the screen to
  settle after each tap, which took about 25 seconds on the attack page. The
  flow sets `waitToSettleTimeoutMs: 500` on its taps.
- The anonymizer did not look inside the websocket login token (a JWT), so the
  real player ID stayed in it. It now rewrites the token and its leak check
  decodes it.
- An older version of the anonymizer mapped short numbers, also 0, and the map
  keeps its entries. Torn sends `userID=0` for "no player", and the fake 7 made
  the faction war data miss, so the faction list spun forever. The anonymizer
  now never maps 0, and the short entries are gone from `idmap.json`.
- A test sees only the steps that its flow does. To write a flow, run it with
  `MITM_ARGS="--set pda_replay_log_hits=true"` and compare the miss log with
  the requests in the recording.
- The faction and crime pages never stop moving (timers, fires). Maestro then
  waits long after every tap, so the flows set `waitToSettleTimeoutMs: 500`.
  On a phone, the armory sections are a dropdown (`armour-nav-list`).
- The arson page polls its list. The replay gave the list from after the
  collects before the flow collected. Now a repeated request gets its next
  answer only after the requests between the two answers in the capture
  (`hold` in the miss log).
- The anonymizer replaced known player names only before `[`, `</a>` or `"`,
  so a profile title ("Name' Profile") kept the real name. Torn also sends
  the faction war data as `text/html`, so the anonymizer never read the
  attacker names in it. Names now go everywhere, except names that are also
  words in Torn's scripts. The faction tag and the lowercase faction name are
  replaced too.

## Next steps: the baseline

The goal is a baseline file for each test flow (attack, faction, crimes) on the
emulator. Later PDA builds are compared with it. Do the steps in this order.
Each step lists how to know that it is done.

### 1. Start the tests from an empty browser (done)

Done on 2026-11-02. The replay proxy answers `https://pda-replay.invalid/blank`
with a fixed page. `make-snapshot.sh` opens it last through
`flows/open-blank.yaml` (`tornpda://` links open as `https://` in PDA). The
first runs after the change had no `getProfileData` miss. The crimes flow
still has a few misses that change from run to run, because Torn chooses a
random graffiti banner and cracking image.

The original plan:

`make-snapshot.sh` leaves the profile page from `flows/open-profile.yaml`
open. Every test then restores that tab first. It loads a page in the
background, and its `getProfileData` request is a miss in every run.

- Change `make-snapshot.sh` so that the snapshot has no open browser tab.
  For example, close the tab after the profile tip is closed, and make sure
  that PDA shows its home screen.
- Done when a test run has no `profiles.php?step=getProfileData&XID=8810916`
  miss.

### 2. Build the measurement app (done)

Done on 2026-11-02. The profile build with `PDA_PERF` and `PDA_PROXY` trusts
the mitmproxy CA, and all three flows pass on it. `replay-ready` is now built
from this install. Rebuild the APK and the snapshot after each code change.

The original plan:

- Build in profile mode, not debug mode. Debug timings are not useful.

  ```sh
  flutter build apk --profile --dart-define=PDA_PERF=true --dart-define=PDA_PROXY=10.0.2.2:8080
  ```

- Profile builds trust user certificates through
  `android/app/src/profile/res/xml/network_security_config.xml`. Make sure
  that this is still true on the current `develop`.
- Install it, and build `replay-ready` again from this install with
  `make-snapshot.sh` (it needs the onboarding, faction and attack
  recordings).
- Done when all three tests pass on the profile build, and `perf.txt` in each
  run folder has `[PDA-PERF-DART]` lines.

### 3. Get the probe into PDA_PERF builds (done)

Done on 2026-11-02. What was found and changed:

- `dart:developer` `log()` never reaches logcat, in any build mode. So the
  Dart trace was invisible, and PDA's own `log()` lines are too.
  `PerfTrace.emit` also prints each record.
- Flutter cuts each logcat line at about 1024 bytes. Records go out in parts
  of 300 characters: `[PDA-PERF-DART] <id> <part>/<parts> <text>`.
- `getHandlerSources` puts the probe first in `PDA_PERF` builds.
  `tools/perf/gen-probe.sh` writes the probe into
  `lib/utils/perf/probe_source.g.dart`. Run it after each probe change.
- `onConsoleMessage` sends probe records to `PerfTrace.emit` as
  `[PDA-PERF-PROBE]`, and not to the terminal.
- The probe logs its record on `pagehide` if the page is left before 10 s
  (`final: 1` in the record). Compare such records only with each other.
- Late callbacks (after a record was written) are counted in `latePrev` of
  the next record. Before, they made one log line each, 700 in one faction
  run.
- `run-test.sh` waits 12 s after the flow, so the last page has its record.

The original plan:

Most targets in the report come from the page probe
(`tools/perf/pda-perf-probe.user.js`), for example `probeStart`,
`tap.tapToNavStart`, `bridge.firstAt` and `hooks.*Injected`. Track 0 in the
report says how to inject it: first, before PDA's own document-start scripts,
and only in `PDA_PERF` builds. See also `docs/perf/measurement.md`, section
1.

- Read the report's Track 0 row and the "Measure with" lines before you write
  code.
- The probe prints each record to the console with the prefix `[PDA-PERF]`.
  PDA's `onConsoleMessage` handler (`lib/widgets/webviews/webview_full.dart`,
  near line 2218) passes console messages to `log()`. Make sure that these
  lines reach logcat in a profile build. If they do not, print them from
  the `PDA_PERF` path. `run-test.sh` collects every logcat line with
  `PDA-PERF`.
- Done when a test run's `perf.txt` has one probe record for each page load
  in the flow.

### 4. Write a summary script (done)

Done: `tools/perf/summarize.py`. See `docs/perf/measurement.md`, section 2.

The original plan:

Each run leaves raw lines in `perf.txt`. Write a script (for example
`tools/perf/summarize.py`) that:

- reads the run folders of one flow,
- groups the Dart and probe records by page (URL without IDs),
- gives the median and the spread (for example p25 and p75) of each metric
  over the runs,
- writes one file that is the baseline for that flow and build.

The flow durations are not a useful metric, because Maestro's waits change
from run to run. Use the per-page records.

### 5. Choose the run settings and keep them (done)

Done: `run-test.sh` writes `env.json` (app version and install time, WebView,
AVD, snapshot, recordings, `MITM_ARGS`). `summarize.py` refuses runs with
different values. `run-baseline.sh` uses the recorded latency by default.

The original plan:

- Network timing: use `MITM_ARGS="--set pda_replay_latency=recorded"`, so
  that the pages load at about the speed of the real server. Every comparison
  must use the same setting.
- Remote Config flags come live from Firebase, and the emulator drifts
  during a session. Run the two builds of a comparison in alternation in one
  session (`PDA_APKS`), or pin the flags.
- Close other apps on the emulator. Use the same AVD and the same host load.
- Write the WebView version (`adb shell dumpsys webviewupdate`) and the PDA
  commit into the baseline file.

### 6. Run the baseline (done)

Use `tools/replay/run-baseline.sh FLOW 8 RECORDINGS...` (see the replay
README). It boots a new emulator from the snapshot for each run. On
2026-11-02, 8 runs of each flow passed (24 of 24), on the profile build of
commit `d20df8c8`, WebView 133.0.6943.137, recorded latency. The files are
in `~/pda-recordings/baselines/d20df8c8-profile/`.

Medians:

| Page | `nav.load` ms | `probeStart` ms | `getHtml` | `setState` |
|---|---|---|---|---|
| `profiles.php?XID=N` | 1163 | 317 | 16 | 80 |
| `page.php?sid=attack` | 958 | 296 | 15 | 27 |
| `page.php?sid=attackLog` | 1332 | 748 | 12 | 66 |
| `factions.php?step=your` | 1647 | 322 | 45 | 206 |
| `factions.php?step=your&type=N` | 1207 | 300 | 38 | 96 |
| `page.php?sid=crimes` (whole visit) | 896 | 267 | 62 | 136 |

How much the numbers vary (p25 to p75, as a share of the median):

- Counts (`getHtml`, `setState`) are the same or almost the same in each
  run. Any change shows.
- `nav.ttfb`, `probeStart` and `bridge.firstAt`: 8 % or less. A change of 10 %
  shows.
- `nav.dcl` and `nav.load`: 2 % (crimes) to 13 % (profile). On the profile
  and faction pages, a change of 10 % does not show clearly. Use 16 runs
  for these pages, or compare the whole distributions.
- `cb.onLoadStop.wallMs` (16 to 65 %) and the `lag` counts (small numbers)
  are too noisy for a comparison alone.

Three notes for reading the numbers:

- `probeStart` counts from the navigation start, so it includes the server
  time of the recording (718 ms on the attack log). The injection delay is
  `injectAfterTtfb` (`probeStart` minus `nav.ttfb`): 20 to 37 ms. Use it for
  the B2 target "within 50 ms of Tampermonkey".

- The profile page is left before its 10 s report, so its probe record is
  the `pagehide` one (`final: 1`). It covers a shorter time than the others.
- `bridge.firstAt` comes 20 to 60 ms after `probeStart`, but this is PDA's
  own first handler call. No userscript is installed in the snapshot, so
  finding 1.8 (userscript calls wait for `load`) is not measured yet. For
  that, install a test userscript that calls `PDA_httpGet` at document
  start.

The original plan:

- Run each flow 5 to 10 times with `run-test.sh` and the profile APK.
- Run the summary script, and save the result as the baseline for the build.
- If the spread is too large to see a change of about 10%, add runs, or find
  the source of the noise first.

## Upstream pull requests

Each fix has two branches. The measurement branch starts from
`perf/analysis` and has the `PDA_PERF` hooks. The upstream branch starts
from `origin/develop` and has only the fix, with plain `getHtml()` in place
of `PerfTrace.getHtml`. The user opens and writes each PR. Update this
table when a PR is opened, changed or closed.

| Fix | Measurement branch | Upstream branch | PR | Status |
|---|---|---|---|---|
| A1 1.1, travel check | `perf/a1-travel-check` | `travel-check-observer` | [#501](https://github.com/Manuito83/torn-pda/pull/501) | Open since 2026-11-02 |

To see the state of all PRs:

```sh
gh pr list -R Manuito83/torn-pda --author xentac --state all
```

- The Analyze and Test checks also fail on `develop` (since `fe76815d`
  or earlier). The Analyze error is `ChatEngine.recheck` in
  `native_chat.dart`, because the public stub
  `lib/config/chat_engine.dart.example` has no `recheck`. Do not fix this in
  a PR.
- Measure each new fix against `perf/analysis` without the open fixes, so
  that each comparison shows one fix.
- When a PR is merged, rebase `perf/analysis` on `origin/develop`. In a
  conflict, keep the upstream code and put `PerfTrace.getHtml` back in
  place of `getHtml()`. Then delete the measurement branch of the fix.
- If the maintainer asks for changes, change the upstream branch first,
  then copy the change to the measurement branch. Measure again only if
  the change can change the numbers.

## Next steps

1. The A1 and B1 quick fixes from the report, one branch each. For each fix,
   build the APK before and after the fix, and run both in one session with
   `PDA_APKS` (see the replay README). The builds then alternate, and the
   Remote Config flags are the same. Compare them with
   `summarize.py --compare`, and name the success metric of the fix with
   `--metric`.

   The APKs are in `~/pda-recordings/apks/`, named after their commit.
   Copy each new APK out of `build/` right after the build, because the
   next build overwrites it. Commit the fix before you build, so that the
   name matches `lib/`. Build with the same flags (profile,
   `PDA_PERF=true`, `PDA_PROXY=10.0.2.2:8080`). Then run 8 runs of each
   build on the attack flow:

   ```sh
   export LD_LIBRARY_PATH=/run/opengl-driver/lib
   PDA_APKS="OLD.apk NEW.apk" PDA_EMULATOR="nix develop /home/xentac/coding/infra/nixos-config#torn-pda -c emulator" \
     nix shell --impure --expr 'with import <nixpkgs> {}; [ maestro (python3.withPackages (p: [p.mitmproxy])) ]' \
     -c tools/replay/run-baseline.sh tools/replay/flows/attack.yaml 8 ~/pda-recordings/anon/attack.mitm ~/pda-recordings/anon/onboarding.mitm
   ```

   The 16 runs take about 25 minutes. Run them in the background. The
   tests of the tools run in the replay shell:
   `python3 -m pytest -o asyncio_mode=auto tools/perf tools/replay`.

   Fix 1.1 of A1 (the travel check) is done, see "Fix 1.1: the travel
   check" below. The next fix is 1.3 (the progress bar), on a new branch
   from `perf/analysis`. Use `ec113644.apk` as the old build only if the
   new branch starts from `perf/a1-travel-check`. Otherwise use
   `50a4a3d9.apk`.
2. Done: `summarize.py --compare` (see "Comparing two builds" in
   `measurement.md`).
3. A test userscript that calls `PDA_httpGet` at document start, in the
   snapshot, so that finding 1.8 gets a number.
4. 16 runs for the profile and faction pages, where the `nav.load` spread is
   over 10 %.
5. Find why one crimes run went back to the blank page (see the lessons).

### Fix 1.1: the travel check (done)

Done on 2026-11-02, on the branch `perf/a1-travel-check` (on the fork
since 2026-11-02). The comparison below measured commit `ec113644`. The last commit
`cef61134` adds only a guard: a check that ends after the next page load
does not change the status. One attack run on `cef61134.apk` passed, with
the same `getHtml` counts (4 on the attack page in that run). `assessTravel` no longer copies and parses the page
10 times. One `callAsyncJavaScript` call waits in the page with a
`MutationObserver` for up to 2 s. Only if the element appears, the app copies
the page once for the stock upload. The check still runs on every page,
because no recording shows on which pages the element can appear. The stock
retry loop in `_sendStockInformation` runs only abroad and is not changed.

Comparison: 8 runs of each build on the attack flow, alternated in one
session, all 16 passed. Old build `50a4a3d9.apk`, new build
`ec113644.apk`. The summaries and the comparison are in
`~/pda-recordings/comparisons/a1-1.1-ec113644-vs-50a4a3d9/`.

| Page | `getHtml` old | `getHtml` new | p |
|---|---|---|---|
| `profiles.php?XID=N` | 16 | 6 | 0.000 |
| `page.php?sid=attack` | 15 | 5 | 0.000 |
| `page.php?sid=attackLog` | 12 | 2 | 0.000 |

Each page now makes exactly 10 fewer copies. The report target "at most 2
on a plain page" is for all of A1. The other copies come from other call
sites, for example the `onLoadStart` copy. `lag.over50`, `setState` and
`nav.load` did not change, except `setState` on the profile page (80 to 84,
p = 0.019). This fix adds no `setState` call, but `frames.n` rose by the
same 4 (p = 0.016). With ten fewer parses on the main isolate, more frames
and rebuilds can fall inside the profile visit. The change may be real, and
it does no harm.

The new observer has a cost that the probe sees. It counts one more
observer (`hooks.moInjected` 2 to 3), and the observer callbacks take more
time in the page: `hooks.moCbMsInjected` from 0.4 to 3.2 ms on the profile
page. Among the unmarked leads (`--all`), `longTasks.total` on the profile
page went from 257 to 317 ms (p = 0.015), and `lag.totalMs` on the attack
log from 298 to 397 ms (p = 0.021). About 12 such leads are expected by
chance over the three pages. 3 ms of observer callbacks cannot cause
60 ms of long tasks, so these leads are chance or a shift in timing. The
observer stays: it finds the element at once, and a check every 200 ms
would remove no measured cost. Check these leads again in the comparison
of all of A1.

No recording is from abroad, so the abroad path (the observer finds the
element, one `getHtml`, the stock upload) was checked only by reading the
code. To test it, turn on the remote debugging setting of PDA, then run
the function body of `waitForSelectorJS` in the WebView devtools and add
a `div.travel-home` element.

### Lessons from the baseline work

- The emulator crashed (SIGSEGV in `gfxstream ColorBuffer::onLoad`) on the
  second snapshot load after a boot. The trigger was a snapshot saved 12 s
  after the blank page loaded. With the save right after the load, six loads
  in a row passed. `run-baseline.sh` boots a new emulator for each run.
- Background jobs that are stopped can leave a replay proxy on port 8080, or
  a test loop that keeps running. Before a new run, make sure that no
  `mitmdump` or `run-test.sh` process is left.
- mitmdump buffers its log when the output is a file. `start_proxy` waited
  for the "listening" line, which came only after traffic. Fixed with
  `PYTHONUNBUFFERED=1`.
- One crimes run of six failed: in the middle of the flow, the tab showed
  the blank start page again. The crimes page wrote no `pagehide` record, so
  PDA probably replaced the WebView. The blank-page detector and the
  rebuild of an unresponsive WebView can do that, and they log only with
  `log()`. Not explained yet.
- First numbers (8 runs to come): 12 to 15 `getHtml` calls on each attack
  page, as the report estimated, and about 62 over the whole crimes visit.
- The emulator drifts during a session. On one build, the faction runs got
  faster from run 1 to run 8: `nav.load` from 1750 to 1545 ms, and
  `lag.totalMs` from 1147 to 666 ms. The first four and the last four runs
  differ by 10 to 12 % (p = 0.03). The cause is not known, for example the
  host CPU or disk cache. Thus a build that runs after another build seems
  faster. Run the two builds in alternation in one session (`PDA_APKS`),
  never one after the other.
- The first `--compare` rule (the p25 to p75 ranges do not overlap) marked 44
  metrics on two halves of the same attack runs. `summarize.py` now uses a
  rank test (Mann-Whitney, exact) on the per-run values. It tests only the
  main metrics and the `--metric` names. On odd and even runs of each flow it
  marked 0 or 1 of about 30 metrics, as expected at p < 0.05.
- A/A check of `PDA_APKS` on 2026-11-02: one APK under two names, 4 runs
  each of the attack flow, in the order A B B A A B B A. All 8 runs passed.
  1 of 21 tests got a mark (p = 0.029), as expected by chance. The same
  runs against the baseline from the morning differ by 6 % in `nav.load` on
  the attack page (p = 0.048). Thus compare only builds that ran in the same
  session. The runs are in `~/pda-recordings/runs/*-attack-aa-*`.

### Later

- The comparison with Firefox and Tampermonkey needs a real phone, as the
  report says. The phone can use the replay proxy on the computer.
- The control app from Track 0 (a minimal `flutter_inappwebview` app) is
  still to do.
- Optional: make the faction flow open the 9mm Uzi's 3D view.
- Report to the maintainer: PDA's tips block all taps on the page until the
  user taps their target.
