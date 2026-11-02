# Progress notes

This file records where the performance work stands, so that a new session can
continue. The plan is in `report.md`. The record and replay tools are in
`tools/replay/`, and their README explains how to use them.

Last update: 2026-11-02 (second session).

## State

- Branch `perf/analysis`, based on `origin/develop` at `fe76815d`. It is not
  pushed. Ask before you push it to the fork (`xentac`). Never push upstream.
- The report is published as a shared artifact:
  https://claude.ai/artifact/GCojySixXsQJxfYYTqNxfK (version 4). The source is
  `report.md`.
- Track T (record and replay) works from start to finish on the emulator:
  capture, anonymize, snapshot, automated test run. Three flows pass:
  `attack.yaml`, `faction.yaml` and `crimes.yaml`. Track 0 (baseline timing)
  started: step 1 of "Next steps: the baseline" below is done.
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

### 2. Build the measurement app

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

### 3. Get the probe into PDA_PERF builds

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

### 4. Write a summary script

Each run leaves raw lines in `perf.txt`. Write a script (for example
`tools/perf/summarize.py`) that:

- reads the run folders of one flow,
- groups the Dart and probe records by page (URL without IDs),
- gives the median and the spread (for example p25 and p75) of each metric
  over the runs,
- writes one file that is the baseline for that flow and build.

The flow durations are not a useful metric, because Maestro's waits change
from run to run. Use the per-page records.

### 5. Choose the run settings and keep them

- Network timing: use `MITM_ARGS="--set pda_replay_latency=recorded"`, so
  that the pages load at about the speed of the real server. Every comparison
  must use the same setting.
- Remote Config flags come live from Firebase. Run the baseline and each
  comparison on the same day, or pin the flags.
- Close other apps on the emulator. Use the same AVD and the same host load.
- Write the WebView version (`adb shell dumpsys webviewupdate`) and the PDA
  commit into the baseline file.

### 6. Run the baseline

- Run each flow 5 to 10 times with `run-test.sh` and the profile APK.
- Run the summary script, and save the result as the baseline for the build.
- If the spread is too large to see a change of about 10%, add runs, or find
  the source of the noise first.

### Later

- The comparison with Firefox and Tampermonkey needs a real phone, as the
  report says. The phone can use the replay proxy on the computer.
- The control app from Track 0 (a minimal `flutter_inappwebview` app) is
  still to do.
- Optional: make the faction flow open the 9mm Uzi's 3D view.
- Report to the maintainer: PDA's tips block all taps on the page until the
  user taps their target.
