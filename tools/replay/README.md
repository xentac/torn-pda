# Record and replay

These tools record a session of PDA traffic, remove personal data from the
recording, and answer PDA from the recording later. With them, two builds of
PDA can get the same input for regression and speed tests, and no test sends
automated traffic to Torn. The plan is in `docs/perf/report.md`, section
"Regression testing".

Rules:

- Only a person plays during a capture. The proxy only listens. Never point a
  test runner, a tap script or a crawler at the live site.
- Raw recordings, `identity.json` and the ID map hold your API key, your
  cookies and other players' data. Keep them in `$PDA_REC_DIR`
  (`~/pda-recordings` by default), never in the repository. The `.gitignore`
  here is a second line of defense, not the first.
- Anonymized recordings still hold other players' names in free text, such as
  chat. Keep them private too.

## Files

| File | Use |
|---|---|
| `capture.sh` | Starts mitmproxy for a capture session with `pda_capture.py`. |
| `pda_capture.py` | Adds marks and a manifest to a capture. |
| `pda_anonymize.py` | Replaces personal data in a recording and checks the result for leaks. |
| `replay.sh` | Starts mitmproxy in replay mode with `pda_replay.py`. |
| `pda_replay.py` | Answers from recordings, logs misses, never forwards. |
| `emu-clock.sh` | Sets the emulator clock to the time of a recording. |
| `common.sh` | The proxy port, the passthrough hosts, the saved hosts and the recording folder. |
| `test_replay.py` | Tests for the three addons, with made-up data. |

## One-time setup

1. Get Python with mitmproxy. On NixOS:

   ```sh
   nix shell --impure --expr 'with import <nixpkgs> {}; python3.withPackages (p: [p.mitmproxy p.pytest p.pytest-asyncio])'
   ```

2. Create the mitmproxy CA before the first recording. Run `mitmdump` once and
   stop it with Ctrl+C. The CA is in `~/.mitmproxy`. A replay sets the device
   clock back to the time of a recording, and the CA must already be valid
   at that time. So do not create a new CA later. If you must, make new
   recordings.
3. Create an Android emulator with a `google_apis` image, not a
   `google_play` image. Only the first kind allows `adb root`, which
   `emu-clock.sh` needs.
4. Install the CA on the emulator as a user certificate:

   ```sh
   adb push ~/.mitmproxy/mitmproxy-ca-cert.cer /sdcard/Download/
   ```

   Then on the emulator, open Settings, Security, Encryption and
   credentials, Install a certificate, CA certificate, and select the file.
5. Build PDA for capture. A debug build trusts user certificates (see
   `android/app/src/main/res/xml/network_security_config.xml`). The Dart HTTP
   client does not use the Android proxy, so give it the proxy with a flag:

   ```sh
   flutter build apk --debug --dart-define=PDA_PROXY=10.0.2.2:8080
   ```

   `10.0.2.2` is the host computer as the emulator sees it. On a real phone,
   use the IP address of the computer.

   For speed tests, build in profile mode with the same flag. Profile builds
   trust user certificates through
   `android/app/src/profile/res/xml/network_security_config.xml`. Release
   builds do not trust them.

## Capture

1. Clear the app data, and enter your real API key during the capture:

   ```sh
   adb shell pm clear com.manuito.tornpda
   ```

   A replay starts from a cleared app too. PDA checks a new key with API
   calls. The replay can answer these calls only when the capture has them.
2. Start the proxy. The label goes into the file name.

   ```sh
   tools/replay/capture.sh trades
   ```

3. Send the emulator's WebView and Android traffic to the proxy:

   ```sh
   adb shell settings put global http_proxy 10.0.2.2:8080
   ```

4. Play by hand. To label a moment, open
   `https://www.torn.com/pda-mark/<label>` in the PDA browser, for example
   `https://www.torn.com/pda-mark/trade-open`. The proxy answers it
   locally, and the label goes into the manifest with its time.
5. Stop the proxy with Ctrl+C. Turn the device proxy off:

   ```sh
   adb shell settings put global http_proxy :0
   ```

6. Read the manifest (`<recording>.mitm.json`). Its `hosts` list shows the
   hosts that were seen but not saved. To save more hosts in later
   captures, change `PDA_SAVE` in `common.sh`.

By default, only `torn.com` and its subdomains are saved. Google and Firebase
traffic passes through without interception (`PDA_PASSTHROUGH`).

## Anonymize

1. Write `$PDA_REC_DIR/identity.json` with your own values. The fields are
   described at the top of `pda_anonymize.py`. `player_id` and
   `player_name` are required.
2. Run the tool. Use the same map file for all recordings, so that one
   real ID always becomes the same fake ID.

   ```sh
   cd "$PDA_REC_DIR"
   python3 /path/to/torn-pda/tools/replay/pda_anonymize.py \
     --identity identity.json --map idmap.json \
     raw/20261101T183000Z-trades.mitm anon/trades.mitm
   ```

3. If the leak check fails, the tool writes nothing and prints the flows
   with a problem. Add the missing values to `identity.json` under
   `strings`, or fix the rules in the tool. Then run it again.
4. The tool prints the fake API key. You enter this key in PDA for replay.

## Replay

1. Start the proxy with one or more anonymized recordings:

   ```sh
   tools/replay/replay.sh "$PDA_REC_DIR/anon/trades.mitm"
   ```

   At startup, it prints the `emu-clock.sh` command for the recording.
2. Set the emulator clock to the start of the recording, for example:

   ```sh
   tools/replay/emu-clock.sh 2026-11-01T18:30:00Z
   ```

3. Clear the app data, so that no real key or cookie is left:

   ```sh
   adb shell pm clear com.manuito.tornpda
   ```

4. Set the device proxy as in the capture steps. Open PDA, and enter the
   fake API key from the anonymize step.
5. Use the app. After the test, give the clock back to the network with
   `emu-clock.sh --auto`, and turn the device proxy off.

Answers come back at once by default. For speed tests, `MITM_ARGS="--set
pda_replay_latency=recorded"` keeps the recorded server time per answer, and
`--set pda_replay_latency=150` gives a fixed 150 ms.

### What the replay does not do

- It does not change game state. A purchase or a trade gets its recorded
  answer, and the next page shows the state from the recording.
- Websockets (chat, live updates) get a 502. The pages work without them.
- A request with no recording gets a 502 with the header
  `x-pda-replay: miss`, and goes to the miss log. Compare the miss logs of
  two builds as part of the behavioral diff.
- Google and Firebase stay live, so the remote feature flags come from the
  network. For a comparison of two builds, run both on the same day, or
  set the flag values in the test.
- The replay matches requests without the parameters `rfcv`, `_`, `key` and
  `timestamp`. Change this with `--set pda_replay_ignore=...`.

If the proxy options are wrong, the addon still refuses live connections to
`torn.com` (`pda_replay_guard`).

## Tests

```sh
python3 -m pytest -o asyncio_mode=auto tools/replay
```
