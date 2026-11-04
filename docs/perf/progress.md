# Progress notes

This file records where the performance work stands, so that a new session can
continue. The plan is in `report.md`. The record and replay tools are in
`tools/replay/`, and their README explains how to use them.

Last update: 2026-11-03 (twelfth session).

## State

- Start of a session: read this file, then run
  `gh pr list -R Manuito83/torn-pda --author xentac --state all` and update
  the table in "Upstream pull requests".
- The maintainer's commit `610af44f` on `develop` (2026-11-02, "browser
  speed") fixed most of A1 without our PRs: 1.1 (their own travel observer),
  1.3 (the progress bar uses a `ValueNotifier`, and does not animate when
  the bar is off or the tab is not on screen), the `onLoadStart` copy (now
  only on `loader.php`), the `getUrl()` per progress event, the repeated
  `endRefreshing()`, the attack condition, the terminal listener
  (`listen: false`, 500 entries at most) and the show-case timer. PR #501
  had only a counter on top of their travel check, and was merged on
  2026-11-02. See "Next steps".
- Branch `perf/analysis`, based on `origin/develop` at `5ea591af` since
  the twelfth session. The rebase had no conflicts, and the local copy
  before it (`perf/analysis-pre-5ea591af`) was deleted after the check
  runs passed. Before that, it was based on `1edf12c5` (the
  merge of #504) since the eleventh session. Both rebases of that
  session had no conflicts. The branches before them are the local
  `perf/analysis-pre-19912e5a` and `perf/analysis-pre-1edf12c5` (deleted at the end of the session, with the user's approval). The
  fork has the rebased branch (force push with the user's approval,
  2026-11-03). The user also had all merged branches deleted on the
  fork: it now has only `master` and `perf/analysis`. Before that, it
  was based on `a2377dcc` since the
  eighth session. The rebase had no conflicts. The new `develop` has only
  `c27e9e54` (the changelog pauses its animation under the browser) and a
  TornTools catalog update. The branch before this rebase is the local
  `perf/analysis-pre-a2377dcc`. The user approved a force push, and the
  fork has the rebased branch since 2026-11-02 (eighth session). Before that, it was based on
  `34594b4c` (after the merge of #501). The first rebase, on `610af44f`, was on 2026-11-02
  (fifth session). The branch before the rebase is the
  local `perf/analysis-pre-610af44f`. The rebased profile build is
  `~/pda-recordings/apks/d4a7dbad.apk`. One attack run on it passed. It
  has new misses that the old recordings cannot answer, because the new
  `develop` makes new requests: `tchat/settings`, `tchat/rooms/tokens` and
  the API call `user/organizedcrime`. Before the rebase, it was based on
  `fe76815d`. It is on
  the fork (`xentac/perf/analysis`) since 2026-11-02. Ask before each push to
  the fork. Never push upstream. Before the first push, one commit was
  rewritten to keep a security detail out of the public history. The old
  history is in the local branch `perf/analysis-backup`. Never push that
  branch.
- Open question for the user: a lesson below (on `MyHttpOverrides` since
  `610af44f`) describes the strict certificate check, and it is on the
  fork. The user can choose to reword it, so that it says nothing about
  the old behavior.
- These APKs are in `~/pda-recordings/apks/`:
  - `50a4a3d9`: the old base, before `610af44f`.
  - `d4a7dbad`: `develop` at `610af44f` with the hooks, without #501.
  - `8f24d8e4`: `d4a7dbad` with the `TickerMode` change. It is only for
    the frame measurement.
  - `5dad324a`: `perf/analysis` on `develop` at `34594b4c`. It was built
    in the seventh session.
  - `b64a3b8c` and `b585eab7`: the old base and `5dad324a` with a timer
    on each await in `onLoadStop`. They are only for that measurement.
  - `53fad5c1`: `perf/analysis` on `develop` at `a2377dcc`, with the probe
    that records the test userscripts. It is the B1 base. Built in the
    eighth session.
  - `244141a6`: fix 1.8 (`perf/userscript-ready-ping`). Ninth session.
  - `79ca88ea`: fix 1.7, part 1 (`perf/end-scripts-together`). Tenth
    session.
  - `96f83dde`: `perf/analysis` on `develop` at `19912e5a`. It has fix
    1.8. It is the new B1 base, in place of `53fad5c1`. Eleventh
    session.
  - `31711aab`: `perf/analysis` on `develop` at `1edf12c5`. It has
    fixes 1.8 and 1.7 part 1. It is the B1 base in place of `96f83dde`.
    Eleventh session.
  - `cd6ed330`: `perf/analysis` on `develop` at `5ea591af`. The B1 base
    in place of `31711aab`. Twelfth session. Its 2 check runs on
    `replay-ready-b1` passed (`20261103T212007Z`, `20261103T212213Z`).
  - `57955d23`: the first try of fix 1.8, which did not work. Only for
    the record in "Fix 1.8: the platform-ready wait".
- Emulator snapshots for replay: `replay-ready` is the A1 snapshot. Keep
  it. `replay-ready-b1` (eighth session) has the test userscripts and
  PDA's five example scripts. Use it for all B1 work, with
  `PDA_SNAPSHOT=replay-ready-b1`. Compare runs only within one snapshot.
- All commits of the tenth session are on the fork (pushed on
  2026-11-03 with the user's approval). Ask before each push.
- The report is published as a shared artifact:
  https://claude.ai/artifact/GCojySixXsQJxfYYTqNxfK (version 15, 2026-11-04, with a status section and status notes in 1.4 and 1.7 part 4). The source is
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
| GM handler crashes after renderer recovery (before this project) | none | `fix/gm-handler-reinject` | [#480](https://github.com/Manuito83/torn-pda/pull/480) | Merged on 2026-07-22. |
| B1 1.7 part 4, start script skip and page `@match` check | `perf/start-skip` (`81da92e3`), `perf/start-guard` (`cbfa3236`) | `start-guard` (commit `9b523b82`, on `match-semantics` plus the #505 commit, pushed to the fork on 2026-11-03) | [#508](https://github.com/Manuito83/torn-pda/pull/508) | Open since 2026-11-04. Its diff shows the #505 and #507 commits until they are merged. |
| `@match` as in Tampermonkey (issue #314) | `perf/match-semantics` (`29014052`) | `match-semantics` (commit `787b2406`, on `5ea591af`, pushed to the fork on 2026-11-03) | [#507](https://github.com/Manuito83/torn-pda/pull/507) | Open since 2026-11-04. |
| B1 1.7 part 3, cache the adapted source | `perf/cond-sources-list` | `cond-sources-cache` (commit `d7165545`, on `5ea591af`, pushed to the fork on 2026-11-03) | [#505](https://github.com/Manuito83/torn-pda/pull/505) | Open since 2026-11-03. |
| B1 1.7 part 1, end scripts together | deleted | deleted | [#504](https://github.com/Manuito83/torn-pda/pull/504) | Merged on 2026-11-03 as `1edf12c5`, without comments or changes. |
| B1 1.8, platform-ready wait | deleted | deleted | [#502](https://github.com/Manuito83/torn-pda/pull/502) | Merged on 2026-11-03 as `19912e5a`, without comments or changes. |
| A1 1.1, travel check counter | none (upstream did 1.1) | `travel-check-observer` (commit `b47209b0`, from local `travel-check-counter`) | [#501](https://github.com/Manuito83/torn-pda/pull/501) | Merged on 2026-11-02 as `9b690feb`. The maintainer then shortened its two comments (`34594b4c`). Keep comments in upstream branches to a few words. |

To see the state of all PRs:

```sh
gh pr list -R Manuito83/torn-pda --author xentac --state all
```

- CI on `develop` is green again since `610af44f`. The stub
  `lib/config/chat_engine.dart.example` now has `recheck`.
- Measure each new fix against `perf/analysis` without the open fixes, so
  that each comparison shows one fix.
- When a PR is merged, rebase `perf/analysis` on `origin/develop`. In a
  conflict, keep the upstream code and put `PerfTrace.getHtml` back in
  place of `getHtml()`. Then delete the measurement branch of the fix.
- If the maintainer asks for changes, change the upstream branch first,
  then copy the change to the measurement branch. Measure again only if
  the change can change the numbers.

## Next steps

0. Start here. The user's decision on 2026-11-02 (seventh session): plan
   as if the maintainer does no more work from the report. All open
   report items are ours. The maintainer still reviews and merges our
   PRs. Before each fix, look at `origin/develop` for the same change,
   because the maintainer did most of A1 without notice once.

   Done in the sixth and seventh sessions:

   - The 60 frames each second come from the changelog dialog (see
     "The 60 frames each second"). `dismiss-tips.yaml` closes it now.
   - The clean A1 run (see "A1 after the maintainer's commit 610af44f").
   - The longer `onLoadStop` is noise (see "The longer onLoadStop").

   Lessons from the seventh session:

   - The run folders of all sessions are in `~/pda-recordings/runs/`.
     For `50a4a3d9`, earlier sessions left 32 more folders there. Give
     `summarize.py` only the folders of this session, by their times.
   - `run-baseline.sh` alternates the builds in pairs (A B B A A B B A),
     not one by one.

   The next task is B1, the userscript quick fixes (the user chose it).
   `610af44f` already did three B1 items:

   - It removes only the registered script groups
     (`_registeredScriptGroups`).
   - It caches the compiled `@match` patterns (`_compiledFor`).
   - A second request for the same URL within 2 s gets the first answer
     (`sendOrShare` in `remote_snippets.dart`).

   Open B1 items, in order of user impact:

   1. Finding 1.8: done in the ninth session, PR #502 (merged). See
      "Fix 1.8: the platform-ready wait".
   2. Finding 1.7, part 1: done in the tenth session. See
      "Fix 1.7, part 1: the end scripts together".
   3. Finding 1.7, part 3: done in the eleventh session. The cache of
      the adapted source and the real list are on the fork as
      `cond-sources-cache`. See the entry "Fix 1.7, part 3, eleventh
      session" below.
   4. Finding 1.7, part 4: mostly done upstream in `610af44f`. The rest
      is done in the twelfth session: #507 (`@match`) and #508 (skip
      and page check), both open. See "Fix 1.7, part 4, twelfth
      session" below.

   Step 1, the measurement setup, is done (eighth session). See "The B1
   baseline".

   Fix 1.7, part 4, twelfth session. `develop` at `5ea591af` already
   removes the stale start scripts before each navigation that the app
   sees: `_removeStaleUserScripts` runs in `shouldOverrideUrlLoading`
   and in `_loadUrl` (added in `610af44f`). The tab mode is on by
   default, and its back and forward go through `loadFromExterior` and
   `_loadUrl`. So the report text of part 4 is out of date for the
   usual case. Correct it in `report.md`. The cases that remain, all on
   Android, found by reading the code:

   - A native `goBack()` or `goForward()`: the back button while a
     trade goes to the vault (`_backButtonPopsContext` false), and the
     swipe when the tab mode is off. Android does not call
     `shouldOverrideUrlLoading` for history navigation.
   - Navigations that the page starts and that Android does not report
     (a form POST, `history.back()` in page JavaScript). Only the track
     B dispatcher fixes these.

   In these cases, the start script of the old page runs once on the
   new page, and the target's start scripts come late, from the probe
   in `onLoadStop`. `onLoadStop` then removes the stale groups, so the
   cost is one wrong page for each event. iOS is not affected, because
   WKWebView asks the navigation policy for back and forward too. The
   park path returns to the same page, so it is not affected.

   Correction, found with the emulator: the swipe branch with native
   `goBack()`/`goForward()` in `_tryGoBack`/`_tryGoForward` is dead
   code. Every `WebViewFull` is built with `useTabs: true`
   (`webview_provider.dart`), also with "Use tabs in browser" off. The
   swipe always goes through `_loadUrl`. The only native `goBack()` is
   the back button when `_backButtonPopsContext` is false (a trade that
   goes to a vault, and the chaining browser's medical menu, where
   userscripts do not run). The first fix (a helper before the native
   calls, `perf/history-step-scripts`) was dropped and deleted.

   The test setup: snapshot `replay-ready-b1-notabs` (from
   `replay-ready-b1`, tab mode off, plus the narrow start scripts
   `perf-start-profile` and `perf-start-page`), the flows
   `add-start-narrow.yaml` and `history-back.yaml`. On the old APK, the
   swipe back from the attack page gave a fresh `navigate` load of the
   profile, with `startProfile` at 59 ms and no `startPage`. So the
   reported back path is clean.

   The user wants one fix for every Android navigation type, also the
   ones that the page starts (`history.back()`, a POST). The plan, in
   two PRs:

   1. PR A, the `@match` semantics (issue #314, closed 2026-04-30 by
      `9b104324`, but not complete). Branch `perf/match-semantics`
      (`29014052`): the `#hash` is not part of the match (as in
      Tampermonkey), `http*://` is the same as `*://`, and a host
      without a port matches any port. 4 new tests, 93 model tests
      pass. Not done, a later report item: `@exclude`,
      `@exclude-match` and `@include` are ignored. The user's export
      uses none of them, but has five exact patterns (no trailing `*`).
   2. PR B, the page guard: each registered start script checks
      `location.href` against its own `@match` before it runs, inside
      the once-per-document condition. Registration stays per
      navigation, so the cost is a few regex tests per page. Tests: a
      Node test that compares the generated check with Dart
      `matchesTarget` (also on the user's export), and a replay test in
      which a test script on the attack page calls `history.back()`
      once. Then 8 and 8 alternated runs.

   What stays after B: on a navigation that Android does not report,
   the target's own start scripts come late, from the `onLoadStop`
   probe (once each). Only "register all start scripts always" fixes
   that, and it costs a parse of every enabled source on each page.
   Measure it before any proposal.

   A correction to the miss counts in the notes: `run-test.sh` prints
   only the records of kind `miss`. The counts of 47 to 54 above are
   all lines of `misses.jsonl` (with the websocket, `state` and `loose`
   records). The check runs of `cd6ed330` printed 20 and 19 (54 and
   about 48 lines). The last run of `1239f828` had 16 (48 lines). The
   URLs are the same.

   Option 1, measured (twelfth session). The user wants document-start
   scripts at document start on every navigation, so "register all
   start scripts once" was measured against the guard alone. The
   branches, all local, on `perf/analysis` at `a2bc5867`:

   - `perf/match-semantics` `29014052` (PR A, rebased from `0ead1112`).
   - `perf/start-guard` `cbfa3236` (PR B on A): `_guardedOnce` puts
     `UserScriptModel.matchGuardJs` into the once-per-document
     condition. If the list has `*`, `matchGuardJs` is null. A Node
     test (`test/models/userscript_guard_test.dart`) compares it with
     `matchesTarget` on 15 lists and 25 URLs, and on the user's export
     with `PDA_BENCH_SCRIPTS=<export>`. It passes. Torn's CSP has no
     `'unsafe-eval'`, so the guard is plain code in the source, not a
     string for `eval`.
   - `perf/start-register-all` `ab0accf5` (measurement only, on B):
     At the webview creation, `_registerAllStart` registers every
     enabled start source once. `_removeStaleUserScripts` does nothing.

   The APKs are `~/pda-recordings/apks/cbfa3236.apk` and `ab0accf5.apk`.
   The two snapshots come from `replay-ready-b1`, with the preferences
   file changed by `tools/perf/add_scripts.py` (a new
   `pda_userScriptsList` record, `PDA_B64:` plus base64 JSON, the last
   record wins). The manual way is PDA's own script import. The
   export has API keys, so the tool removes the custom keys and the
   update URLs, and nothing of it goes into git:

   - `replay-ready-b1-user`: plus the user's 9 enabled start scripts
     (768 KB).
   - `replay-ready-b1-stress`: the user snapshot, plus the 35 enabled
     end scripts (3.9 MB) as start scripts with `@match
     https://pda-replay.invalid/never/*`. It shows the cost of all end
     scripts as start scripts (for example with `DOMContentLoaded`).

   8 and 8 alternated runs of the attack flow on each snapshot, all
   passed (user: `20261103T224829Z` to `20261103T232450Z`, stress: to
   `20261103T235601Z`). Old is the guard, new is register-all. Medians:

   - User snapshot. `shouldOverrideUrlLoading` before a navigation:
     177 to 1.5 ms (attack), 200 to 1.5 ms (attack log). Tap to
     navigation start: 185 to 12 ms. Tap to DOMContentLoaded: 1104 to
     928 ms (-16 %), 1630 to 1416 ms (-13 %). `nav.dcl`, `nav.load`
     and `us.start.start` (from the navigation start) do not change
     (p > 0.3). So 768 KB of start scripts on every page costs
     nothing that the runs can see.
   - Stress snapshot. `shouldOverrideUrlLoading`: 114 to 1 ms and 130
     to 0.8 ms. Tap to DOMContentLoaded on the attack page: 978 to
     839 ms (-14 %). But the parse costs show: `nav.dcl` on the attack
     log 1205 to 1305 ms (+8 %, p 0.03), `bridge.firstAt` +30 ms
     (attack), +85 ms (attack log), +124 ms (profile), the longest
     long task 77 to 140 ms (attack log) and 92 to 207 ms (profile),
     and `us.start.waitMs` +21 to +85 ms. The tap to TTFB is still
     115 to 130 ms shorter. The Dart UI max frame goes from 33 to
     95 ms once a run (the registration of 4.6 MB at the webview
     creation).

   The result: the cost of `_removeStaleUserScripts` and the new
   registration on each tap (115 to 200 ms on the UI thread) is larger
   than the parse cost of the user's own start scripts. Register-all
   with the guard is faster for this user, and starts every start
   script at document start on every navigation type. With 4.6 MB of
   start scripts, the page work grows by about 100 ms. The tap to
   DOMContentLoaded is then still shorter on the attack page, and
   about the same on the others.

   Where the per-tap registration time goes (measurement branch
   `perf/reg-timing`, `47aaa518`, 3 runs on each snapshot, 6 taps
   each). The record is `PDA-PERF-REG` in `logcat.txt`, and the
   tool `tools/perf/reg_records.py` joins it. On each tap, the attack pages
   match 6 start scripts (646 KB), and all 6 are already registered.
   `_addUserScriptsAvoidDuplicates` still removes and adds all 6
   again. Medians on the user snapshot (the stress snapshot is the
   same, because its scripts match no page): the whole step 126 ms
   (63 to 175), the wrap into `_guardedOnce` 16 ms, the 6 removes
   28 ms (4 to 65), the 6 sequential `addUserScript` calls 70 ms (41
   to 95). The message encoding is only 2 ms of the add, and the time
   of one call does not follow its size (a 1 KB script took 45 ms
   once). So most of the time is the wait for the Android main thread
   and the native work. The handler check and the stale removal are
   below 1 ms. Timers in the plugin's Java code were refused, because
   they change the shared pub cache.

   Guard plus skip (branch `perf/start-skip`, `81da92e3`: the guard,
   the PR #505 cache commit, and "skip a group that is registered
   with the same source"). The script model keeps the finished start
   source (storage wrapper, once check, guard), built again only when
   the body or the guard string changes, so the skip is an
   `identical` check. `removeAllUserScripts` now also clears the
   record of registered groups. 8 and 8 alternated runs against
   `cbfa3236` on `replay-ready-b1-user`, all passed. Medians:
   `shouldOverrideUrlLoading` 159 to 1.5 ms (attack) and 217 to
   1.6 ms (attack log), tap to navigation start 168 to 9 ms and 223
   to 9 ms, tap to DOMContentLoaded 1075 to 921 ms (-14 %) and 1606
   to 1407 ms (-12 %). `nav.dcl`, `nav.load` and `us.start.start` do
   not change (p > 0.19). So the skip gives the same gain as
   register-all, without the parse of scripts that do not match.

   Memory: the cache holds one finished copy per start script, shared
   by all tabs. The plugin's Dart controller keeps every added
   `UserScript` in its `_userScripts` list while it is registered, so
   a registered source stays in Dart memory in any design. A design
   that builds the string per registration (no cache) holds one copy
   per tab instead. The cache only costs extra for a start script
   that no tab has registered at that moment.

   The PR branches (thirteenth step of part 4, same session). In the
   worktree `<scratchpad>/up` (copy the ignored `lib/config` and
   `android` stubs into a new worktree before `flutter test`):

   - `match-semantics` `787b2406` on `develop` `5ea591af`: PR A, only
     the `@match` fix and its 4 tests (52 tests in the file pass).
     Draft: `~/pda-recordings/pr-drafts/pr-match-semantics.md`.
   - `start-guard` `9b523b82`: PR B, on `match-semantics` plus the
     PR #505 commit (`c3f53ace`, the same change as `d7165545`). One
     commit: the guard, the skip with the cached start source, and a
     test of the cache (same string, new string after a key or
     `@match` change). It also clears the registered sources in
     `onRenderProcessGone` and `onWebContentProcessDidTerminate`. 97
     model tests pass. Draft:
     `~/pda-recordings/pr-drafts/pr-start-guard.md`.

   Both branches and `perf/analysis` (`3534b46a`) are on the fork
   since 2026-11-03, pushed with the user's approval. The user posted
   them as #507 (PR A) and #508 (PR B) on 2026-11-04.

   The `history.back()` test: snapshot `replay-ready-b1-back`
   (`replay-ready-b1-notabs` plus `perf-back-once`, added with
   `add-back-once.yaml`, then `open-blank.yaml`). The flow is
   `page-back.yaml`, with `anon/attack.mitm`. The script goes back
   1.5 s after the attack page loads, often before Maestro sees that
   page, so the flow waits 10 s and does not look for "Start fight".
   The script is in the snapshot: a change to the file needs a new
   snapshot. Results (`tools/perf/start_scripts.py` on `perf.txt`): on
   `cd6ed330`, the profile after the back step has `startPage` (the
   stale attack-page script, 285 to 290 ms) in all 4 runs. On
   `cbfa3236` and `81da92e3`, it has none, in all 4 runs. In all of
   them, `startProfile` comes late (640 to 800 ms, from `onLoadStop`).
   The last two runs passed (`20261104T021630Z`, `20261104T021755Z`).

   Start of the twelfth session. At the end of the eleventh session:

   - `cond-sources-cache` (`d7165545`, on `develop` at `5ea591af`) is
     PR #505, open since 2026-11-03. Run the `gh pr list` command in
     "State" and update the table. Do not change the branch while the
     PR is open, unless the maintainer asks for changes.
   - `perf/analysis` and `perf/cond-sources-list` are on the fork
     (pushed on 2026-11-03 with the user's approval).
   - Done: the report artifact is version 14. The user had the four
     local `perf/analysis-pre-*` backup branches deleted. Keep
     `perf/analysis-backup` (see "State"). Before the next rebase, make a
     new local copy, and delete it after the check runs pass.
   - Remove the upstream worktree in the old
     scratchpad (`git worktree list`, then `git worktree remove
     --force`). It has untracked config stubs that git ignores. The
     scratchpad of a new session is a new folder, so make a new
     worktree for the next upstream branch.
   - `perf/analysis` is on `develop` at `1edf12c5`. `develop` is now at
     `5ea591af`. If more commits came, rebase `perf/analysis` (keep a
     local copy first), build the base APK, and run 2 check runs on
     `replay-ready-b1`, as in the eleventh session. Then rebase
     `perf/cond-sources-list` on it.
   - The next fix is 1.7, part 4 (item 4 above). First make sure that a
     document-start script of the previous page still stays registered
     on `develop`. Read the code (`_registeredScriptGroups`,
     `_addUserScriptsAvoidDuplicates`, `shouldOverrideUrlLoading` in
     `webview_full.dart`), and tell the user what you find before you
     propose a fix.
   - Run flutter in the nix shell: `nix develop
     /home/xentac/coding/infra/nixos-config#torn-pda -c sh -c 'flutter
     ...'`. The git remotes are `origin` (upstream, never push) and
     `xentac` (the fork).
   - A cache question from the user, answered: the cache compares the
     key on every read, and the source by identity (`identical`, a
     pointer check). So a new PDA key, a new custom key, or a new
     source rebuilds the copy. A copy is never stale. An equal source
     in a new string object only costs one more adapt. A page that is
     already open keeps its scripts until the next load, as before the
     PR.

   Done in the eleventh session: steps 1 to 4 below. The rebase had no
   conflicts. `perf/end-scripts-together` is one commit again
   (`49511c4e`). The local fix 1.8 branches are deleted. On the fork,
   `perf/userscript-ready-ping` and `userscript-ready-ping` still exist,
   and `perf/analysis` is the old one, until the user approves. The 2
   check runs of `96f83dde` passed (`20261103T171412Z`,
   `20261103T171556Z`). The chat change added no new kind of miss. Each
   run had 52 misses, and 7 of them were `attackData` polls. In the 16
   runs of fix 1.7, part 1, the totals were 47 to 54, and the
   `attackData` misses were 3 to 7.

   Start of the eleventh session: #502 is merged (`19912e5a`), and
   `develop` also has `b0361eda` (a large chat change, 15 files). So
   first:

   1. Rebase `perf/analysis` on `origin/develop`. Keep a local copy of
      the branch before the rebase (`perf/analysis-pre-19912e5a`). In a
      conflict, keep the upstream code and put `PerfTrace.getHtml` back.
   2. Delete the local branches `perf/userscript-ready-ping` and
      `userscript-ready-ping`. Ask the user before you delete them on the
      fork and before the force push of `perf/analysis`.
   3. Rebase `perf/end-scripts-together` on the new `perf/analysis`, so
      that it stays one commit. Do not change `end-scripts-together`
      while #504 is open, unless the maintainer asks for changes.
   4. Build the new base APK from the rebased `perf/analysis`, and run 2
      check runs on `replay-ready-b1`. The chat change can change the
      flow or the misses. If a run fails, find why before you go on.
      This APK is the new base for B1 fixes, in place of `53fad5c1`,
      because it has fix 1.8.

   Fix 1.7, part 3, eleventh session. Later on the same day, #504 was
   merged (`1edf12c5`), so `perf/analysis` was rebased again and the
   base APK is `31711aab`. The user approved the `.toList()` fix and
   asked for a Dart benchmark with many scripts (the user has 73,
   most of them enabled). The measurement branch is
   `perf/cond-sources-list`: the benchmark
   `test/perf/cond_sources_bench_test.dart` (run it with
   `PDA_BENCH=1`) and the fix ("Return a real list from getCondSources"). The benchmark uses the real
   provider with generated scripts (sources of 4 to 300 KB, 1 in 4
   on every Torn page) and repeats the reads of one page load on a
   profile page. Medians on the host, per page load:

   | Scripts (enabled, on the page) | Base | `.toList()` | Cached `adaptSource` |
   |---|---|---|---|
   | 10 (9, 5) | 2.6 to 2.7 ms | 2.5 ms | 0.08 ms |
   | 40 (34, 20) | 8.0 to 8.2 ms | 5.7 to 7.7 ms | 0.08 to 0.17 ms |
   | 73 (61, 37) | 10.9 to 15.6 ms | 13.8 to 14.3 ms | 0.15 to 0.30 ms |
   | 150 (125, 75) | 25.1 to 25.9 ms | 22.0 to 31.7 ms | 0.71 to 0.74 ms |

   So the `.toList()` gives no gain that the benchmark can see. The
   time is in `adaptSource`: three passes over each full source on
   each call, and the start scripts go through it twice per page
   load. The cache column is a local test, not committed (a map by
   `storageId`, valid while the source is the same object and the
   key is the same). A phone is slower than the host. The work is on
   the UI isolate, and the call in `shouldOverrideUrlLoading` comes
   before the navigation policy returns. The cache is a proposal to
   the user, not yet approved.

   The user's own export (`~/Downloads/userscripts_export.json`, not
   in git, it holds API keys): 73 scripts, 44 enabled, 4.6 MB of
   enabled source. The largest enabled script is FF Scouter V2 - DEV
   (397 KB, document start, every Torn page). The user also has two
   disabled copies of FF Scouter V2 of the same size. With
   `PDA_BENCH_SCRIPTS` set to the export, the medians per page load
   on the host were 16 to 31 ms on the current code. They were 0.26 to
   0.78 ms with the cache (two runs each):

   | Page | Scripts on it | Current | Cached |
   |---|---|---|---|
   | `index.php` | 6, 684 KB | 20.0, 20.7 ms | 0.50, 0.27 ms |
   | `profiles.php` | 6, 919 KB | 29.1, 28.7 ms | 0.78, 0.52 ms |
   | `loader.php?sid=attack` | 4, 441 KB | 15.6, 15.6 ms | 0.37, 0.26 ms |
   | `page.php?sid=crimes` | 10, 1096 KB | 31.1, 30.8 ms | 0.78, 0.56 ms |
   | `page.php?sid=ItemMarket` | 9, 1180 KB | 30.0, 31.1 ms | 0.71, 0.59 ms |
   | `factions.php` | 10, 1084 KB | 21.8, 21.5 ms | 0.46, 0.39 ms |
   | `item.php` | 9, 1061 KB | 21.8, 21.4 ms | 0.39, 0.40 ms |

   Memory of the cache (the user asked to reduce it). Of the 44
   enabled scripts, 9 contain `###PDA-APIKEY###` (1.6 MB) and 1 of
   them also has curly quotes. FF Scouter has neither. 20 scripts
   have characters outside Latin-1, so Dart keeps them at 2 bytes for
   each character. A full cache holds about 7.4 MiB for this user.
   Two other versions were tested locally, not committed (medians on
   the host, two runs):

   - Flags only (whether the source has the placeholder or curly
     quotes, no copy): 0.8 to 2.8 ms, but crimes stays at 10 ms,
     because cRaCked still takes the slow path.
   - Mixed (a full copy only for a script that needs a change, a flag
     for the others): 0.8 to 1.8 ms on all seven pages, about
     2.8 MiB for this user, nothing for a user without such scripts.
     The extra time over the full cache is the copy that wraps the
     source on each call.

   A version with no copy at all is possible: keep the offsets of the
   placeholders and quotes, and build the result from them.

   The curly quote replacement in `adaptSource` has no comment and no
   documentation. It came in `d9be50ba` (2023-01-18, "Fixed
   userscripts injection on iOS when windowId has been defined") for
   `“` and `”`. `ea0b2238` (2025-09-07) added `‘` and `’`. The test
   `normalizes smart quotes before injection` in
   `test/models/userscript_model_test.dart` covers it. It changes
   every such quote in the whole source, also inside strings. So a
   `’` inside a single-quoted string (`'Don’t'`) becomes a syntax
   error. A possible later report item, not a performance one. The
   cache must keep the replacement as it is.

   The user's decision: the mixed cache and the `.toList()` in one PR,
   and document the quote problem. The cache is in `UserScriptModel`
   (`adaptedBody`). `adaptSource` is split into `adaptBody` (the
   script part, the same string when nothing changes) and
   `_wrapSource`, so a script that needs no change costs no memory.
   The upstream branch is `cond-sources-cache` (on `1edf12c5`). The
   measurement branch has two more commits: the benchmark and a check
   that the output equals the old code for every exported script
   (passed). Medians with the user's export, after the fix: 0.56 to
   1.9 ms per page load (two runs). `report.md` now has the corrected
   part 3 and a section on the quote problem (with a Node test). The
   artifact is version 14 now. The fix APK is `1239f828`. Its 2
   check runs on `replay-ready-b1` passed (`20261103T193615Z`,
   `20261103T193755Z`), with 51 and 48 misses, 5 and 4 of them
   `attackData`. All test scripts ran on the three pages, the start
   script had status 200, and `us.endGapMs` was 1 to 4 ms. The PR
   draft is `~/pda-recordings/pr-drafts/pr-cond-sources-cache.md`.
   The upstream branch passes `flutter analyze` and `test/models` on
   its own, with the `.example` stubs placed as `docs/README.md` says.
   Later, `develop` moved to `5ea591af` (three commits, one in
   `userscripts_provider.dart`, only the handler scripts). The branch
   was rebased with no conflicts, to `d7165545`, and analyze and the
   91 model tests passed again. The check runs were not repeated,
   because the new commits do not touch the fixed code.

   The risk of a script change during `onLoadStop`: since part 1, the
   end scripts go to `Future.wait`, which reads the list at once, with
   no await between the steps. The other reads have no await inside
   them either. Only the debug loops (off, `_debugScriptsInjection`)
   read the list after an await. So the `ConcurrentModificationError`
   cannot happen now, and nothing in the chain throws in practice. The
   `.toList()` is only hygiene. Tell the user this before the PR.

   The first proposal to the user (before the benchmark): `develop` at `19912e5a` still has the lazy chain. The fix
   is a `.toList()` inside the `UnmodifiableListView` in
   `getCondSources`. The return type stays, so no caller changes. What
   the code read showed:

   - The `try/catch` in `getCondSources` catches nothing today, because
     the `where` and `map` run at the call site.
   - The SDK `ListIterator` reads `length` at each step, which runs the
     filter again. The end-script loop in `onLoadStop` awaits between
     steps. If the number of matches changes during an await, it throws
     `ConcurrentModificationError`. The loop is in the `try` that ends
     at `webview_full.dart:2068`, so the error skips the rest of that
     block.
   - Each read makes new `UserScript` objects.
   - Speed: a Dart count of one loop gave 39 `matchesTarget` calls in
     place of 9 (9 scripts, 2 matches), and 206 in place of 40 (40
     scripts, 3 matches). `adaptSource` runs once per script in each
     pass. So "quadratic" and "on each access" in `report.md` are
     wrong. Correct them. The gain is microseconds, which the replay
     cannot show.
   - Proposed measurement: 2 check runs for no regression, the call
     counts as PR evidence, `flutter analyze` and `test/models`. The
     `RegExp` objects in `adaptSource` are a separate, later PR.

   Then fix 1.7, part 3 (item 3 above), with the same steps as fix 1.7,
   part 1 (see that section). Part 3 changes only Dart work, so its
   success metric is `dart.cb.onLoadStop.wallMs`. With two test scripts,
   the gain can be too small to see. Look at the code first, and tell the
   user what the replay can show before you run it.

   Measure each fix against the new base APK, without the other open
   fixes (#504), so that the comparison shows one fix.

   Then one branch for each fix, as in item 1. The user writes and posts
   each PR.

   Also open, not B1:

   - The `TickerMode` change is dropped (the user's decision, eighth
     session). The maintainer's `c27e9e54` pauses the changelog animation
     under the browser, which was the only case that we measured. Keep
     the local branch `perf/drawer-tickermode`. Make a PR only if a frame
     run shows another animation under the browser.
   - The A1 items from 1.4 (the iframe fast path, the `http` race,
     document-start scripts once per navigation), and `getHtml` 3 on the
     profile page.
   - Done (2026-11-04): the status of each finding is in `report.md`
     and in the artifact (version 15). Update the status section when
     a PR is merged.
   - Later (the user's request, 2026-11-04): find PDA's real share of
     a page load. Tap to DOMContentLoaded is 920 to 1400 ms in the
     replay, but the first byte (recorded Torn server time) is 260 to
     730 ms of it, and the 620 to 800 ms after it is mostly Torn's
     HTML, blocking scripts and their recorded latency. Two ways: split
     that time with the probe's resource timings (cheap, the data is
     in the runs), and load the same replayed pages in the track 0
     control app (a plain WebView). The difference to the control app
     is PDA's total cost.
   - The new `develop` makes requests that the recordings do not have
     (`tchat/settings`, `tchat/rooms/tokens`, `user/organizedcrime`). A
     new capture needs the user's login (`live-ready`), so ask the user
     first.

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

   The maintainer's commit `610af44f` did most of A1, and #501 is merged
   (see "State" and "A1 after the maintainer's commit 610af44f"). There is
   no measurement branch now. For a new fix, make the branch from
   `perf/analysis`, and the upstream branch from `origin/develop` with only
   the fix (see "Upstream pull requests"). The user writes and posts each
   PR. Give the user a draft of the PR text in the scratchpad. Keep code
   comments in upstream branches to a few words: the maintainer shortened
   ours after the merge.

   Finding 1.2 (the app reads the page in about 75 places) has no quick
   fix of its own. Its fix is track P, the page data layer.

   The user's own answers:

   - PR shape: one small PR per fix, each one testable alone. Keep doing
     this.
   - Travel pages: the element appears only on a small number of travel
     pages, but nobody has a list yet, and Torn can change the pages. So
     the travel check stays on every page for now. Later: collect the
     travel pages (for example in an abroad capture), and then limit the
     check to them.

   The maintainer's answers (2026-11-02):

   - The `onLoadStart` copy: already limited to `loader.php` on `develop`.
   - `_assessGeneral` at both `onLoadStart` and `onLoadStop`: the
     maintainer thinks that it is for iOS, but does not remember. The
     maintainer does not want to change such WebView behavior without
     tests with beta testers, because such problems were hard to find in
     the past. Do not propose this change without a test plan for iOS and
     beta testers.
   - The `PDA_PERF` hooks and the replay tools stay in the fork. Each PR
     gives the numbers only.
   - CI: fixed upstream, see "Upstream pull requests".

   Done in the fifth session: the rebase on `develop`, the comparison of
   the new `develop` with `50a4a3d9.apk`, and the deletion of the old fix
   branches. The open items of this list are in item 0.

2. Done: `summarize.py --compare` (see "Comparing two builds" in
   `measurement.md`).
3. Done: test userscripts in the snapshot (see "The B1 baseline").
4. 16 runs for the profile and faction pages, where the `nav.load` spread is
   over 10 %.
5. Find why one crimes run went back to the blank page (see the lessons).

### Fix 1.7, part 1: the end scripts together

Done on 2026-11-03 (tenth session). `origin/develop` had no such change
(still `a2377dcc`).

The fix: `onLoadStop` sent each document-end script with
`evaluateJavascript` and awaited it before it sent the next one. Now it
sends all calls at once and awaits them with `Future.wait`. The report
said "in one `evaluateJavascript`", but the user chose separate calls. In
one call, a syntax error in one script stops all end scripts, and in-page
`eval` can be blocked by the page's CSP. The order stays the same: the
Android plugin posts each call to the main looper in sequence
(`injectDeferredObject` in `InAppWebView.java`). On iOS, the plugin
calls `WKWebView.evaluateJavaScript` directly, with no queue of its own
(`InAppWebView.swift`). iOS and Windows are not tested. The steps before the first script did not change, so
`us.endAll.afterLoad` was not expected to change. A reorder of those
steps is a separate fix, and it needs an iOS test plan.

The run: 2 check runs of `79ca88ea` (`20261103T064050Z`,
`20261103T064230Z`, not in the summary) showed a gap of 1 ms at once.
Then 8 runs of `53fad5c1` and `79ca88ea`, alternated, on
`replay-ready-b1`, from `20261103T064417Z` to `20261103T070955Z`. All 16
passed. The summaries are in
`~/pda-recordings/baselines/fix17p1-79ca88ea/` (`old/` and `new/`).

Medians in ms (p25 to p75):

| Page | `us.endGapMs` | `onLoadStop` wall | `us.endAll.afterLoad` |
|---|---|---|---|
| `profiles.php?XID=N` | 162 (96 to 279) to 1 (0 to 1), p < 0.001 | 698 to 326, p 0.014 | 292 to 241, p 0.23 |
| `page.php?sid=attack` | 29 (27 to 32) to 1 (1 to 2), p < 0.001 | 150 to 101, p 0.16 | 79 to 72, p 0.52 |
| `page.php?sid=attackLog` | 53 (42 to 83) to 2 (1 to 2), p < 0.001 | 308 to 234, p 0.51 | 190 to 156, p 0.28 |

Other results:

- `nav.load`, `getHtml` and `setState` did not change.
- On the profile page, `probe.injectAfterTtfb` is 2 ms later (20.2 to
  22.6, p 0.035). It comes before `onLoadStop`, so the fix cannot cause
  it. With many metrics, one such p is expected by chance.
- The gain grows with the number of matching end scripts, because each
  script after the first one saves one round trip. The replay has only
  two.

### Fix 1.8: the platform-ready wait

Done on 2026-11-02 (ninth session). `origin/develop` had no such change.

Why the wait exists: Dart registers the handlers once per WebView, in
`onWebViewCreated`. Before that, it awaits `clearAllCache` and the script
setup. The first page of a tab can run its document-start scripts before
the handlers exist. A call to a missing handler gets `null` back without
an error. In the Android plugin, `in_app_webview_controller.dart` skips
the `_javaScriptHandlersMap.containsKey` block. If the native channel is
not ready, the call never settles. After the first page, the handlers
always exist. The plugin event comes only in `onPageFinished` (Android)
or `didFinish` (iOS). iOS never sets `_platformReady`.

The fix: a handler `PDA_handlersReady`, registered last in
`addScriptApiHandlers`, returns `true`. The promise in
`handler_flutterPlatformReady` asks it, and resolves on `true` or on the
old event, whichever comes first. The copy in `_pdaApiBaseJS` is the
same, and its version is not changed. The `__TornPDA_ReadyEvent__` script
runs first and Remote Config cannot replace it, so the fix holds with an
older RC override. Only `webview_full.dart` registers the script
handlers, so other WebViews do not change. Document-end scripts run in
`onLoadStop`, after the event, so they do not change.

A lesson: the first try (`57955d23`) asked once at document start, and
16 runs showed no change. PDA's document-start scripts run before the
bridge's `callHandler` exists. It appears some 20 to 30 ms later (the probe polls for it for the same reason). The try/catch hid
the error. The fix now retries every 10 ms, 100 times at most.

The run: 8 runs of `53fad5c1` and `244141a6`, alternated, on
`replay-ready-b1`. All 16 passed. Two check runs of `244141a6` came
before them (`20261103T010339Z` and `20261103T010530Z`). They are not in
the summary. Give `summarize.py` the run folders by name, not with a
time glob, because a glob also takes such check runs. The summaries are in
`~/pda-recordings/baselines/fix18-244141a6/` (`old/` and `new/`). The
runs of the first try are in `~/pda-recordings/baselines/fix18/`.

Medians in ms (p < 0.001 for all):

| Page | `us.start.waitMs` | `us.start.rttMs` |
|---|---|---|
| `profiles.php?XID=N` | 803 to 36 | 1012 to 139 |
| `page.php?sid=attack` | 647 to 60 | 699 to 92 |
| `page.php?sid=attackLog` | 515 to 79 | 612 to 142 |

Other results:

- All 22 start-script records have status 200. Some records have no
  `us.start` field, as in the baseline.
- `nav.load` did not change.
- On the profile page, `nav.dcl` (+48 ms, +4.7 %), `domInteractive`
  (+4.6 %) and `paint.lcp` (+4.9 %) are later, with p < 0.03. The
  attack pages do not show this. The likely cause is the earlier answer,
  but there are two candidates. The bridge work of the answer can delay
  the page parse, which is a real cost on a phone. Or the Dart request
  and the page share the one replay proxy, which is only a cost of the
  test. The first try did not show the delay. Name it in the PR.
- On the attack page, `onLoadStop` is 54 % shorter (p 0.010).
- Not tested in the replay: the first page of a new tab. The replay flow
  opens no new tab. The PR test plan asks for it on a phone.
- The user tested `244141a6` live on the emulator (`live-ready`, with a
  plain `mitmdump` that records nothing). FF Scouter V2 works and pages
  load quickly. FF Scouter V2 runs at `document-start` and uses
  `GM_xmlhttpRequest`, which calls `PDA_httpGet`, so it gets the gain. It
  caches estimates for one hour, so only new players show the change.

### The B1 baseline

Done on 2026-11-02 (eighth session).

What changed in the tools:

- The replay proxy serves files at fixed URLs (`pda_replay_static`,
  `PDA_STATIC` in `common.sh`), without a recording. See the replay
  README.
- PDA's five example scripts are saved from `origin/master` (`3d5e6d4a`)
  in `~/pda-recordings/userscripts/examples/`, with `static.json`, the map
  of their GitHub URLs. The proxy serves them, and PDA installs them on
  its first run.
- The test userscripts are in `tools/replay/userscripts/`. `perf-start`
  runs at document start on every Torn page and calls `PDA_httpGet`.
  Three scripts run at document end: `perf-end-all` (every page, also
  calls `PDA_httpGet`), `perf-end-profile` (`profiles.php*`) and
  `perf-end-page` (`page.php*`). Each one writes its times into
  `window.__pdaPerfUs`. The probe (version 0.3.0) adds this object to its
  record, so `summarize.py` shows the fields as `probe.us.<script>.<field>`.
  The probe also writes `bridge.byName.<handler>.firstAt`.
- `summarize.py` derives four metrics per run from these fields:
  `us.start.waitMs` (`readyAt` minus `callAt`), `us.start.rttMs`
  (`answerAt` minus `callAt`), `us.endAll.afterLoad` (`endAll.start`
  minus `nav.load`) and `us.endGapMs` (the second document-end script's
  `start` minus `endAll.start`).
- `make-snapshot.sh` adds the test scripts through PDA's remote load
  dialog (`flows/add-userscripts.yaml`). The success message is a toast,
  which Maestro cannot see, so the flow waits for the script name.
- A correction: the example script `Company Stock Order` (`auto-stock-fill`)
  matches `https://www.torn.com/*`, so it runs on every page. It only
  waits for a hash change, so it is cheap.
- An open question: the old `replay-ready` snapshot already listed the
  five example scripts, although the proxy answered their downloads with
  a 502. Where the list came from is not known. But the old split runs
  (`b585eab7`) have no `ols.endScript` records, so no document-end script
  ran. Thus the A1 runs did not run the example scripts.

The run: 8 runs of `53fad5c1.apk` on the attack flow, from
`replay-ready-b1`, with `PDA_APKS` (each run installs the APK again and
starts PDA). All 8 passed, and all 8 have the test-script fields, so the
scripts stay after a restart. The misses are the same as before (the
websocket, `tchat/*`, `user/organizedcrime`). The summary is in
`~/pda-recordings/baselines/b1-53fad5c1/attack.json`.

Medians in ms from the navigation start:

| Page | `nav.load` | `start.callAt` | `start.readyAt` | `start.answerAt` | `endAll.start` | second end script `start` | `onLoadStop` wall |
|---|---|---|---|---|---|---|---|
| `profiles.php?XID=N` | 1081 | 354 | 1180 | 1360 | 1621 | 1756 | 732 |
| `page.php?sid=attack` | 911 | 291 | 932 | 969 | 971 | 1000 | 136 |
| `page.php?sid=attackLog` | 1220 | 750 | 1267 | 1370 | 1416 | 1468 | 258 |

Per-run medians (p25 to p75) of the derived metrics, in ms:

| Page | `us.start.waitMs` | `us.start.rttMs` | `us.endAll.afterLoad` | `us.endGapMs` |
|---|---|---|---|---|
| `profiles.php?XID=N` | 830 (748 to 880) | 1015 (899 to 1064) | 557 (501 to 595) | 112 (63 to 160) |
| `page.php?sid=attack` | 643 (638 to 650) | 681 (676 to 697) | 68 (61 to 81) | 27 (12 to 37) |
| `page.php?sid=attackLog` | 513 (474 to 547) | 620 (590 to 628) | 202 (183 to 221) | 32 (26 to 58) |

What the numbers show:

- Finding 1.8 is real. A `PDA_httpGet` call at document start waits
  for the platform-ready event, which comes 21 to 99 ms after the page
  `load` (medians). The call waits 513 to 830 ms, and its answer comes
  620 to 1015 ms after the call. In Tampermonkey, the same request would
  start at once. `waitMs` has a small spread on the attack pages, so a
  change of 10 % shows.
- Finding 1.7: the first document-end script starts 68 to 557 ms after
  `load`. The second matching script starts 27 to 112 ms after the
  first one, because `onLoadStop` runs them one at a time. The spread of
  `us.endGapMs` is large, so it needs 16 runs or a large change.
- `dart.cb.onLoadStop.wallMs` is much larger with scripts: 732, 136 and
  258 ms. In the clean A1 run (no test scripts, other snapshot), it was
  187, 42 and 98 ms. Do not compare these runs directly, because the
  snapshots differ. A fix must be compared with `53fad5c1` in one
  session.
- `getHtml` (3, 2, 2) and `setState` (6 on each page) are as in A1.
- The profile page record is `final` in 6 of 8 runs. Compare its probe
  times with care.

### A1 after the maintainer's commit 610af44f

The clean run is from 2026-11-02 (seventh session). It has 8 runs of each
build on the attack flow, alternated in one session. All 16 runs passed.
The old build is `50a4a3d9.apk`, our base before `610af44f`. The new
build is `5dad324a.apk`, `perf/analysis` on `develop` at `34594b4c`. It
has #501. The changelog closed in all 8 runs of the new build, and each
page had 44 to 104 frames. The summaries and the comparison are in
`~/pda-recordings/comparisons/a1-clean-5dad324a-vs-50a4a3d9/`.

| Page | `getHtml` | `setState` | `frames.n` | `lag.totalMs` | `onLoadStop` ms | `nav.load` ms |
|---|---|---|---|---|---|---|
| `profiles.php?XID=N` | 15.5 to 3 | 77.5 to 6 | 90.5 to 98.5 (p 0.12) | 898 to 659 (p 0.028) | 139 to 187 (p 0.028) | 1193 to 1168 (p 0.88) |
| `page.php?sid=attack` | 15 to 2 | 26.5 to 6 | 36.5 to 47 (p < 0.001) | 825 to 707 (p < 0.001) | 35 to 42 (p 0.51) | 898 to 911 (p 0.28) |
| `page.php?sid=attackLog` | 12 to 2 | 62.5 to 6 | 60.5 to 65 (p 0.020) | 303 to 328 (p 0.96) | 64 to 98 (p 0.038) | 1215 to 1239 (p 0.44) |

The `getHtml` and `setState` changes have p < 0.001. The A1 targets for
`setState` (under 10) are met on all three pages. The target for
`getHtml` (at most 2) is met on the attack pages. The profile page has 3.
`dart.frames.rasterOver16` stays at 0 or 1 on all pages. `lag.over50` on
the attack page fell from 1 to 0 (p 0.012). The page load times did not
change.

The 60 frames each second of the first A1 run are gone. They came from
the changelog, not from the browser (see "The 60 frames each second").
The attack page now draws about 10 frames more than the old build, and
the attack log about 5 more. Each frame is cheap: the total Dart lag is
14 % lower on the attack page and 27 % lower on the profile page.

In this run, `onLoadStop` rose by 48 ms on the profile page and by
34 ms on the attack log, both with p < 0.05. A second run did not show
the rise, so it is not a regression (see "The longer onLoadStop").

In this run, both builds write the same records for the profile page:
the probe record is final, and the Dart record ends at the next page
load. Thus the profile page's time metrics are comparable. In the first
A1 run, they were not.

The first A1 run, with `d4a7dbad.apk`, had the changelog open under the
browser. Its frame and lag numbers are wrong. Its files are in
`~/pda-recordings/comparisons/a1-develop-d4a7dbad-vs-50a4a3d9/`.

### The longer onLoadStop

Checked on 2026-11-02 (seventh session). `onLoadStop` uses only 0.1 to
0.25 ms of Dart CPU time (`dart.cb.onLoadStop.syncMs`) in both builds.
The rest of its wall time is waiting on awaits, so it does not block the
UI thread. The awaited helpers are the same in both builds, except for
the script removal, which `610af44f` changed.

To find the slow await, two local builds time each await in
`onLoadStop` with `PerfTrace.cb` (names `ols.*`). `b64a3b8c` is the old
base (branch `perf/onloadstop-split-old`), and `b585eab7` is
`perf/analysis` (branch `perf/onloadstop-split`). Both branches are
local only. 8 runs of each, alternated, all 16 passed. The files are in
`~/pda-recordings/comparisons/onloadstop-split-b585eab7-vs-b64a3b8c/`.

| Page | `onLoadStop` ms, old to new | `ols.getHtml` ms, old to new |
|---|---|---|
| `profiles.php?XID=N` | 133 to 131 (p 0.80) | 124 to 126 (p 0.80) |
| `page.php?sid=attack` | 44 to 40 (p 0.80) | 36 to 33 (p 0.67) |
| `page.php?sid=attackLog` | 73 to 93 (p 0.083) | 64 to 73 (p 0.23) |

The other awaits take under 0.5 ms each. The replay has no userscripts,
so `ols.endScript` has no records and the removal is near 0 ms. Thus the
wall time of `onLoadStop` is the `getHtml` copy of the page. Its time
depends on the WebView, not on Dart. In this run, no page has a
significant change. The spread is large (the profile page has p25 to
p75 of 105 to 213 ms in the old build). So the rise in the clean A1 run
was noise. `getHtml` in `onLoadStop` is the page title read, one of the
reads that the page data layer (track P) removes.

The old base does not build with the current ignored stubs in
`lib/torn-pda-native/`. The old code imports from there, and the new
code from `lib/config/`. For the old build, put
`lib/config/stats_controller.dart.example` of the old branch in
`lib/torn-pda-native/stats/stats_controller.dart`. Keep the current
`chat_engine.dart`, because the old stub has no `recheck`. Restore the
current file after the build.

### The 60 frames each second

Found on 2026-11-02 (sixth session). The source is the changelog dialog,
not the browser. `_AnimatedChangelogWordmark` (`lib/utils/changelog.dart`)
runs an `AnimationController` with `repeat()` for the gradient on the word
"CHANGELOG". The browser does not cover the dialog with a route:
`lib/main.dart` shows the app and the browser in an `IndexedStack`, and an
`IndexedStack` does not stop the tickers of the hidden child. So the
animation draws 60 frames each second under the browser.

Why only the new build: `610af44f` changed `androidCompilation` from 698
to 700, and `replay-ready` has 698. So the new build shows the changelog
after the install, and the old build does not. `dismiss-tips.yaml` does
not close it. The check runs before the dialog appears, and during the
countdown the button text is "Great! (3)", which the full-match regex
"Great!" does not match. All `d4a7dbad` runs in the A1 comparison had the
dialog open under the browser.

VM timeline (a profile build, `profileWidgetBuilds` and paint profiling
on, idle profile page): with the dialog under the browser, 180 frames in
3 s, each with an `AnimatedBuilder` and a `ShaderMask` build. After a tap
on "Great!", 4 frames in 3 s. The VM timeline is a ring buffer: with paint
profiling on, a trace of the dialog in front covers only 0.16 s. Check the
time span of each trace.

Measurement build: `8f24d8e4` on the local branch `perf/drawer-tickermode`
wraps the hidden app child of the `IndexedStack` in
`TickerMode(enabled: !browserShowInForeground)`. The navigator has a
`GlobalKey`, so its state stays. Side effect: an open chat conversation
on the app side counts as covered while the browser is in front
(`chat_conversation_page.dart` reads `TickerMode`), so it stops its API
poll. The chat window in the browser is not affected.

Comparison: 8 runs each of `50a4a3d9`, `d4a7dbad` and `8f24d8e4` on the
attack flow, alternated in one session, all 24 passed. Files in
`~/pda-recordings/comparisons/frames-8f24d8e4-vs-d4a7dbad-vs-50a4a3d9/`.

| Page | `frames.n` old, current, fix | `lag.totalMs` old, current, fix |
|---|---|---|
| `profiles.php?XID=N` | 92, 615, 97.5 | 777, 1115, 661 |
| `page.php?sid=attack` | 34, 601.5, 48 | 820, 1099, 753 |
| `page.php?sid=attackLog` | 58.5, 611, 62.5 | 334, 756, 270 |

The fix against the current build: `frames.n` minus 84 to 92 % and
`lag.totalMs` minus 31 to 64 % (all p < 0.01). The fix against the old
build: `lag.totalMs` is 8 to 19 % lower (not significant), `nav.load` is
the same. So the corrected A1 result is: fewer copies and rebuilds, and
no new frame cost. The rise of `onLoadStop` on the attack page (26 to
49 ms, p 0.005) stays with the fix. `frames.uiAvgMs` is higher in the fix
only because the cheap animation frames are gone from the average.

### Fix 1.1: the travel check (done)

Done on 2026-11-02, on the branch `perf/a1-travel-check` (deleted after
upstream did its own fix in `610af44f`). The comparison below measured commit `ec113644`. The last commit
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

- When upstream changes `androidCompilation`, the new build shows the
  changelog after the install, and `replay-ready` does not have it
  closed. Before a comparison, look at an early screenshot of a run, and
  make sure that no dialog stays open under the browser.
  `dismiss-tips.yaml` now waits up to 15 s for the changelog and taps
  "Great!" until it closes. An `extendedWaitUntil` with a 10 s timeout
  failed after 2 s there, so the flow uses a `repeat` loop.

- In zsh, an unquoted variable that holds several paths stays one word.
  Give `summarize.py` the run folders as a glob or an array, for example
  `old=(~/pda-recordings/runs/*-attack-50a4a3d9)`, never through `$(ls)`
  in a variable. Otherwise it skips the folders and says "no perf.txt".

- Rebase lesson: in a conflict, never take a whole file with
  `git checkout --ours`. It also drops the hunks of the commit that did not
  conflict. On the rebase on `610af44f`, this lost 20 `PerfTrace.getHtml`
  hooks, and commit `d4a7dbad` put them back. After a rebase, count the
  hooks: `grep -rn '\.getHtml()' lib` must show only `perf_trace.dart`.
- Since `610af44f`, `MyHttpOverrides` rejects certificates that are not
  from a known root (Remote Config `network_strict_mode`). In `PDA_PROXY`
  builds, the fork also accepts a certificate whose issuer contains
  `mitmproxy`. Without this, the Dart API calls fail in the replay.
- The ignored files in `lib/torn-pda-native/` are copies of the public
  stubs in `lib/config/*.dart.example`. When upstream changes a stub, copy
  it again, or `flutter analyze` fails. On 2026-11-02, 60 tests in
  `test/chat/` failed locally after the rebase. The fork does not change
  chat code. Not yet checked on a clean `develop`.

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
