# Progress notes

This file records where the performance work stands, so that a new session can
continue. The plan is in `report.md`. The record and replay tools are in
`tools/replay/`, and their README explains how to use them.

Last update: 2026-11-01.

## State

- Branch `perf/analysis`, based on `origin/develop` at `fe76815d`. It is not
  pushed. Ask before you push it to the fork (`xentac`). Never push upstream.
- The report is published as a shared artifact:
  https://claude.ai/artifact/GCojySixXsQJxfYYTqNxfK (version 4). The source is
  `report.md`.
- Track T (record and replay) works from start to finish on the emulator:
  capture, anonymize, snapshot, automated test run. Track 0 (baseline timing)
  is not started.

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
  in git. The fake PDA key is in `idmap.json` (the `keys` values).

## Recordings

| Anonymized file | Raw capture | Usable for replay |
|---|---|---|
| `anon/onboarding.mitm` | `20261102T013938Z-onboarding` | Yes. API calls only. |
| `anon/faction.mitm` | `20261102T025600Z-faction` | Yes. Captured with a cleared cache. |
| `anon/crimes.mitm` | `20261102T025850Z-crimes` | Yes. Captured with a cleared cache. No test flow yet. |
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
- The faction flow only opens the page. Your clicks and scrolls in the capture
  are answers in the recording, but a test sees them only if its flow does the
  same steps.

## Next steps

1. Write `flows/crimes.yaml` for the crimes capture. If the faction test must
   cover more than the page load, add your capture's clicks to
   `flows/faction.yaml`.
2. Report to the maintainer: PDA's tips block all taps on the page until the
   user taps their target.
3. Build the APK with `PDA_PERF=true` and `PDA_PROXY`, install it, build
   `replay-ready` again, and run each test several times for a baseline.
4. Track 0 from the report: probe hooks in `PDA_PERF` builds, the control app,
   and the comparison with Firefox and Tampermonkey (on a real phone against
   the replay proxy).
