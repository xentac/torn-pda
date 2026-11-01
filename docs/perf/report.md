# Torn PDA browser performance: analysis and plan

## Summary

Chromium is not the cause of the slow Torn PDA browser. The Android System WebView is the same engine that Chrome uses. The cause is the work that Torn PDA does around the engine.

The main problem is one thread that does too much. Since Flutter 3.29, Dart code runs on the Android main thread. In Flutter 3.47 you cannot turn this off. The Android WebView also runs its browser side (input routing, navigation control, the JavaScript bridge) on that same thread. With Hybrid Composition, Flutter rasterizes its frames on that thread too. Torn PDA then does a lot of Dart work on every page load:

- about 12 full copies of the page HTML, each parsed in Dart,
- about 65 Dart-to-WebView round trips,
- one bridge message for each subresource,
- 100 to 200 rebuilds of the 7,000-line browser widget.

While that work runs, the WebView cannot react quickly to taps, scrolls, or the next navigation. Firefox with Tampermonkey has none of this work.

Most of the cost comes from a few fixable sources. Five of them affect every user on every page with the default settings. The plan at the end groups the fixes into five independent tracks. Each track has a metric from the measurement tools in `tools/perf/` that proves or disproves its effect.

The user prompt that started this work was cut off at "a similar app that". This report reads it as "a similar app that is as fast as Firefox with Tampermonkey, with the same features".

## Scope and evidence

Read this section before you use any number in this report.

- Nobody ran the app for this report. No Android device was available. Every count in this report comes from reading the code. Every millisecond figure is an estimate.
- The measurement tools in `tools/perf/` exist to replace the estimates with numbers. `docs/perf/measurement.md` tells you how to use them. Each finding below names the field that confirms it.
- Four analysis agents read upstream `master` at `3d5e6d4a`. Then the main findings were verified again on `origin/develop` at `fe76815d`. All of them still hold there. Where this report gives a line number, the number is for `develop` at `fe76815d`. Where it gives no line number, it names the file and the function.
- The plugin is the Manuito83 fork of `flutter_inappwebview`, pinned at `765d75b6` in `pubspec.yaml`.
- "Verified" means that the code path was read and confirmed. "Suspected" means that the mechanism is clear but the size of the cost is not known.

## The central problem: one thread does everything

Three facts combine.

1. Flutter 3.29 and later run the Dart UI isolate on the Android platform thread. In Flutter 3.47 the opt-out flag `DisableMergedPlatformUIThread` only throws an exception (`FlutterEngineFlags.java` in the engine source). This is verified.
2. The app uses legacy Hybrid Composition for every WebView. The plugin defaults `useHybridComposition` to true, and the app never changes it. In this mode the Flutter raster thread merges into the platform thread for every frame that contains a platform view. This is verified in the engine source (`AndroidExternalViewEmbedder::PostPrerollAction`).
3. Android WebView runs the Chromium browser side on the app main thread. Input events, navigation decisions and `@JavascriptInterface` replies that post to the main looper all wait for that thread.

So a Dart `package:html` parse of a 300 KB Torn page blocks WebView input. A `setState` on the browser widget at 60 Hz blocks it. A sembast compaction blocks it. In Firefox, the equivalent thread is mostly idle.

This changes how to judge each fix. The goal is less Dart main-thread work during page loads and interactions. A different composition mode does not remove that work. The section "Questions about the design" covers composition modes.

## Findings

The findings are in three tiers. A tier 1 finding is on by default, happens on every navigation, and has a large cost. A tier 2 finding applies only to some pages, some settings, or some users. A tier 3 finding is background or startup cost.

### Tier 1: every user, every page

#### 1.1 The travel detection fetches and parses the page 10 more times after each load

This is verified. In `onLoadStop`, the app calls `_travelHandler.assessTravel(document)` on every page (`webview_full.dart:1974`). In `travel_handler.dart:52-66`, the function first looks for a `.travel-home` element. If the page has no such element, the function loops 10 times. Each loop waits 200 ms, calls `getHtml()`, and parses the result with `package:html`. A page has no `.travel-home` element unless you are abroad, so the loop runs on almost every page.

`getHtml()` is two round trips. The first is `getSettings()`. The second evaluates `outerHTML`, which also blocks the page's own main thread while it serializes the DOM. So each page load causes 20 round trips, 10 DOM serializations and 10 Dart parses in the 2 seconds after load. You often tap the next link in those 2 seconds. The stock-table code in the same file (`travel_handler.dart:103`) has a second loop of the same type.

Fix: query `.travel-home` with one `evaluateJavascript` that returns a boolean. Run this query only on pages where travel is possible.

Confirm with: `cb.onLoadStop.totalMs` in the Dart trace, and the count of `evaluateJavascript` calls in the platform channel log.

#### 1.2 Many more full-page parses in Dart

This is verified. `webview_full.dart` has 20 `getHtml()` calls. In the default path:

- `onLoadStart` parses the HTML (`webview_full.dart:1757-1758`). At that moment the document is still the old page or a blank page, so most of this parse is wasted.
- `onLoadStop` parses it again.
- `onLoadResource` parses it on trade, property, jail and bounty pages, with retries.
- Section tests in `onProgressChanged` can start more parses before the first one finishes. This is suspected.

Each parse runs on the main thread (see "The central problem"). A parse of a 200 to 400 KB page with `package:html` takes an estimated 20 to 80 ms on a mid-range phone.

Fix, short term: delete the `onLoadStart` parse. Replace the other parses with small `evaluateJavascript` queries that return only the needed fields. Fix, long term: track A2 below.

#### 1.3 The progress bar rebuilds the whole browser widget on every frame

This is verified. `_onProgressAnimationUpdate` calls `setState` on each animation tick (`webview_full.dart:7457-7461`). `_animateProgressTo` restarts a 300 ms animation on every `onProgressChanged` event. The load bar setting only hides the bar. So the animation runs also with the load bar turned off.

So during a page load, the full `WebViewFull.build` runs at the display refresh rate. Each build also creates a new `InAppWebView` widget. The plugin's `build()` then runs `initialSettings.toMap()` with about 200 fields. The native view is reused, but the Dart work happens on every frame. The estimate is 100 to 180 rebuilds for a load of 1.5 to 3 seconds. Hidden tabs that load also do this, because `IndexedStack` does not stop their tickers.

Fix: drive the bar from a `ValueNotifier` or an `AnimatedBuilder` that wraps only the 2 px bar. If the bar is off or the tab is not visible, skip the animation.

Confirm with: `counts.setState` per navigation in the Dart trace.

#### 1.4 Every link tap is cancelled, sent to Dart, and started again

This is verified. The app sets `useShouldOverrideUrlLoading: true` (`webview_full.dart:640`). In the plugin, the Android client returns "cancel" for every main-frame navigation and waits for Dart (`InAppWebViewClientCompat.java`). If Dart allows the navigation, the client calls `loadUrl` again. The network request does not start until the Dart callback finishes.

Before the Dart callback answers, it does this work:

- an optional hit test,
- userscript matching (see 1.6),
- one `removeUserScriptsByGroupName` call for each matching script,
- `addUserScripts` calls, one at a time, each with the full script source.

Each native add or remove also removes and re-adds a second plugin script (`updateContentWorldsCreatorScript`). For iframe navigations, Dart still runs this work with the iframe URL, but the plugin ignores the answer.

Fix, short term: return "allow" at once for iframes. If the set of scripts did not change, do not change the script registration. Fix, long term: track B. After track B, set `regexToAllowSyncUrlLoading` to match `https://www.torn.com/` so that Torn navigations do not go through Dart.

Confirm with: `cb.shouldOverrideUrlLoading.totalMs`, and `nav.ttfb` in the probe for PDA and for Firefox.

#### 1.5 Each subresource sends a message through the bridge

This is verified. The app sets `useOnLoadResource: true` (`webview_full.dart:639`). The plugin then injects a `PerformanceObserver` into every frame. For each resource, the observer calls `callHandler`. The message first goes as JSON through a synchronous Java bridge call. Then it goes to the main looper, then over the method channel to Dart. An `evaluateJavascript` call then resolves the promise. The plugin setting `pluginScriptsForMainFrameOnly` is false by default, so iframes also get the observer.

The Dart side of `onLoadResource` does real work only on a few pages: trades, vault, jail, bounties, properties and factions. All other resources pay the bridge cost for nothing. Torn pages load about 100 resources, and polling requests keep the messages going after load.

Fix: set `useOnLoadResource: false`. Add a document-start hook that watches XHR and `fetch` on the pages that need it. If a URL matches, the hook calls one handler. Set `pluginScriptsForMainFrameOnly: true`. The code comment near the settings says that intercepting AJAX broke `onLoadResource` on iOS. Test the replacement on iOS first.

#### 1.6 Userscripts run late and cost Dart work on every navigation

This is verified. There are four parts.

1. `@run-at document-end` scripts run from `onLoadStop` with `evaluateJavascript`, one at a time. `onLoadStop` fires after the window `load` event, which waits for every image. Tampermonkey runs these scripts at `DOMContentLoaded`. On Torn's image-heavy pages, the difference can be seconds. The plugin's own native "document end" option also waits for `load` on Android, so switching to it does not help.
2. Before the first end script runs, `onLoadStop` awaits many `removeUserScriptsByGroupName` calls (`webview_full.dart:1913-1916`). It makes one call for each script that does not match the page, including disabled scripts. With 40 installed scripts and 3 matches, that is 37 sequential round trips. On iOS, each removal rebuilds the whole `WKUserContentController` and sends every script source to the web content process again.
3. `getCondSources` in `userscripts_provider.dart` returns a lazy view. Each access runs the `where` and `map` again. `matchesTarget` in `userscript_model.dart` compiles new `RegExp` objects for each `@match` pattern on every call, with no cache. `adaptSource` runs two regular-expression replacements over the full source on each access.
4. A document-start script that matched the previous page stays registered until the next `onLoadStop`. So it also runs on the next page. Its `@match` is not tested again. This is a correctness bug, and it wastes work.

Fix, short term: run all end scripts first in one `evaluateJavascript`. Remove only the groups that are registered. Cache compiled patterns. Make `getCondSources` return a real list. Fix, long term: track B.

Confirm with: `probeStart` in the probe for a script with `@run-at document-end` and for one with `document-start`, in PDA and in Tampermonkey.

#### 1.7 Userscript network calls wait for the page to finish loading

This is verified. Each `PDA_http*` helper and `PDA_storage` awaits `window.__PDA_platformReadyPromise` (six places in `remote_snippets.dart`). That promise resolves on the plugin event `flutterInAppWebViewPlatformReady`. Android sends that event only in `onPageFinished`, after `load`. So a script such as FF Scouter cannot start its request until every image on the page is loaded. Under Tampermonkey the request starts at once.

The gate is not necessary. `callHandler` exists from document start, and the app registers its handlers in `onWebViewCreated`, before the first load.

There is also a correctness bug. If a script requests the same URL again within 2 seconds, each helper returns `undefined` (`remote_snippets.dart`, the `loadedPdaApiGetUrls` test). A second script that requests the same URL gets no response. The helper must return the first call's promise instead.

Fix: if `callHandler` exists, call it at once. If it does not exist, wait for the event. Share the in-flight promise for duplicate calls.

Confirm with: `bridge.byName.PDA_httpGet` timing and `nav.load` in the probe. The request start must move from after `load` to near `probeStart`.

### Tier 2: some pages, some settings

| Finding | When it applies | Status | Fix |
|---|---|---|---|
| On attack pages, every progress tick above 75 % does `getHtml` and a full parse, then throws the result away. The condition at `webview_full.dart:3891` can never be false once `_attackTriggered` is set. | Attack pages | Verified | Correct the condition. |
| Each JavaScript console line calls `TerminalProvider.notifyListeners`. `WebViewFull.build` listens to that provider (`webview_full.dart:843`), so every console line rebuilds every awake tab. The terminal text is an unbounded string that is copied on each line. | Pages or scripts that log | Verified | Use `listen: false` in `build`. Cap the buffer. |
| `launchShowCases` runs on every build of `WebViewFull` and schedules a 1-second timer each time. The stack view limits this to once a minute, but `WebViewFull` does not. | All loads, with 1.3 | Verified | Limit it, or run it once after the first frame. |
| With the cache turned off, `cacheMode` is `LOAD_NO_CACHE` and each new WebView clears the cache. | Users who turned the cache off, or the Remote Config value "off" | Verified, default is on | Ask users with slow loads to make sure that the cache is on. Look at `res.cacheRatio` in the probe. |
| The chat cache trim script reads every `localStorage` value on every Torn page (`js_handlers.dart`, near line 86). It runs at document start, before Torn's own scripts. | All users, cost grows with storage size | Verified | Measure once per session, or sample. |
| Chat highlight (on by default) injects CSS and starts a 500 ms polling loop on every `onLoadStop`, also on hash navigations. | Users with chat highlight on | Verified | Inject once per document. Use a shared observer (track A3). |
| `onScrollChanged` sends a channel message for every scroll offset change. The Dart side only stores the position for a later restore. | All scrolls | Verified | Read the scroll position only for a restore, or limit the message rate in the plugin. |

### Tier 3: background and startup

| Finding | Status | Fix |
|---|---|---|
| The 1x1 prewarm WebView stays mounted for the life of the app, because the Remote Config value `browser_engine_prewarm_unmount_after_load` is false by default (`drawer.dart:728`). This keeps a platform view in every frame, so native Flutter pages also run in merged Hybrid Composition mode. | Verified for the code default. The live Remote Config value is not known. | Set the value to true. |
| `WebViewProvider` has more than 60 `notifyListeners` calls. Each awake `WebViewFull` has a `Consumer<WebViewProvider>` around the whole tab, including the `InAppWebView`. The stack view, the drawer, the profile page and the loot page also listen to the whole provider. | Verified | Use `Selector` or `context.select` for the fields each widget needs (track C). |
| Each navigation calls `_saveTabs` twice. Each call encodes every tab and its history to JSON and writes to sembast. All preferences go through one sembast database behind one lock. Large values (spies, FF Scouter cache, war factions) are in the same database, so compaction rewrites them. | Verified. The compaction cost is suspected. | Delay `_saveTabs` by 2 seconds and merge calls. Move large values to their own files. |
| `ChainStatusController` calls `update()` with no IDs every second while a chain widget is active. This rebuilds the app border and the tab bar menu. | Verified | Use `GetBuilder` IDs. |
| The TCT clock and the loot page call `setState` every second. They also do this behind the browser. `IndexedStack` does not stop their tickers. | Verified | Wrap the drawer branch in `TickerMode(enabled: !browserShowInForeground)`. |
| API v2 creates a new `ChopperClient` for each call and decodes each response twice on the main thread. API v1 uses the top-level `http.get`, which opens a new connection for each call. Large responses are decoded on the main thread. | Verified | Share one client. Decode once. Use `Isolate.run` for large responses. |
| `main()` runs 14 awaits in sequence before `runApp`, including Sendbird, WorkManager, HomeWidget and the notification permission request. | Verified | Move the ones that the first frame does not need to after the first frame. |

## Questions about the design

The request was to question the basic assumptions, not only the details. These are the assumptions that the current design depends on, with a recommendation for each.

### Dart reads the DOM to learn what page it is on

The app copies the page HTML to Dart and parses it again. It does this to find the open section of Torn and to select the widgets to show. This is the root of findings 1.1, 1.2 and most of tier 2. The page already has a DOM and a fast selector engine.

Recommendation: replace this with one document-start script, registered once per tab. The script detects the section from `location`, the DOM and SPA events (`hashchange`, `pushState`, a `MutationObserver`). It extracts only the data that the Dart widgets need, such as trade rows, jail list, travel state or login errors. For each change of section, it posts one `callHandler('pdaPage', {...})` message. Dart then does no `getHtml`, `parse`, `getUrl` or `getTitle` in the hot path. This is track A2.

### Every navigation goes through Dart

Dart must approve each navigation only because userscripts are registered per navigation and because of a few special cases: external schemes, locked tabs, the mini-profile option that opens a new tab, and `.user.js` links. Most of these special cases can be detected without a round trip, from the URL alone or in page JavaScript.

Recommendation: after track B, let Torn URLs load without a Dart decision with `regexToAllowSyncUrlLoading`. Keep the Dart callback for non-Torn hosts and for locked tabs.

### Dart manages userscripts on each navigation

Tampermonkey registers scripts once and matches URLs in the page. PDA adds and removes scripts per navigation from Dart.

Recommendation: register one document-start loader. Register it again only after a change to the script set or the API key. The loader contains three things:

- the PDA handler bundle,
- a small list with the ID, match patterns and run time of each script,
- each enabled script, wrapped in a function.

At document start the loader matches `location.href`, and then does this:

- It runs `document-start` scripts at once.
- It runs `document-end` scripts on `DOMContentLoaded`. If the document is already past loading, it runs them at once.
- It runs `document-idle` scripts shortly after `DOMContentLoaded`, and no later than `load`.

This removes the per-navigation registration work, fixes finding 1.6 part 4 by design, and makes back and forward navigation work without the current probe. Do not use the plugin's native "document end" injection, because it waits for `load` on Android. This is track B.

### One 7,000-line widget is the browser

`WebViewFull` owns the platform view, the app bar, the panels, the progress bar and all section logic. Any `setState` rebuilds all of it.

Recommendation: create the `InAppWebView` widget once and keep the same instance, so that Flutter skips it on rebuild. Move the app bar, panels, progress bar and chain widget into small widgets that listen only to what they show. This is track C.

### Which Android composition mode to use

The analysis agents disagreed here. This is the recommendation after comparing their reasons.

- Legacy Hybrid Composition (current): smooth WebView scrolling, but Flutter raster work merges into the main thread.
- Texture Layer Hybrid Composition (`useHybridComposition: false`): the Flutter documentation calls it janky for fast scrolling of a web view. In this mode the plugin also adds a polling script for its context menu. Do not make it the default. You can test it behind Remote Config.
- HCPP (Hybrid Composition++): the forward path. It needs Android 14 (API 34) and Vulkan, and you turn it on with the manifest value `io.flutter.embedding.android.EnableHcpp`. It falls back by itself on other devices. It is experimental in Flutter 3.47, and the plugin does not use its API. After the plugin supports it, test it.

No mode removes Dart work from the main thread. Tracks A and C give more benefit than any mode change, so do them first.

The WebView hardware layer is a separate setting. With Hybrid Composition and `hardwareAcceleration: true`, the plugin calls `setLayerType(LAYER_TYPE_HARDWARE)`, which adds an offscreen pass. The name misleads: `false` does not mean software rendering. Upstream already has a Remote Config A/B test for this (`webViewHardwareLayerActive`). Ask the maintainer for the result of that test before you change it.

### A different engine or a native browser

- Custom Tabs and Trusted Web Activities cannot inject scripts. They are not an option.
- A native Android Activity browser, such as the plugin's `InAppBrowser`, removes the Flutter embedding. But the timers, chain widget and other Flutter overlays then need native versions or a second Flutter view. The effort is high.
- GeckoView with a bundled WebExtension can do what Firefox with Tampermonkey does. But it needs a new Flutter plugin and adds about 60 to 80 MB per ABI. It still runs under a composition mode, and it has no iOS version.

Recommendation: do not change the engine. Do tracks A to C first. Then use `InAppBrowser` with the same scripts as an A/B test, to measure how much of the remaining gap comes from the embedding.

## Work plan

The tracks are independent unless a dependency is stated. Each track has a metric from the measurement tools. Before you start, record a baseline on one device with the probe, the Dart trace and `adb-bench.sh`.

| Track | Content | Depends on | Can stay in the fork | Acceptance metric |
|---|---|---|---|---|
| A1. Dart hot path, quick fixes | Fix 1.1 (travel loop) and 1.3 (progress bar). Delete the `onLoadStart` parse. Fix the attack condition, the terminal listener and the show-case timer. Send the fixed per-load JavaScript in one call. | None | Yes. Each fix is small and easy to send upstream. | `counts.setState` under 10 per navigation. No `getHtml` on a plain page. `cb.onLoadStop.totalMs` down by more than 50 %. |
| A2. Section detection in JavaScript | One document-start orchestrator script. Replace `getHtml` and `parse` for all sections. Replace `useOnLoadResource` with filtered hooks. | A1 (smaller diff) | Large change. Needs maintainer agreement. | Zero `getHtml` calls in normal use. Zero `onLoadResource` messages. No change in features. |
| A3. Shared observer | One `MutationObserver` dispatcher for all built-in features, in place of separate observers and polling loops. | A2 makes it simpler | Yes | `hooks.moInjected` and `hooks.ivInjected` in the probe. Fewer long tasks. |
| B1. Userscript quick fixes | 1.7 platform-ready gate and duplicate promise, end scripts first in one call, remove only registered groups, cache patterns, real list from `getCondSources` | None | Yes | `PDA_httpGet` start time near `probeStart`. `cb.onLoadStop.totalMs`. |
| B2. Document-start loader | Register once, match in JavaScript, run end scripts on `DOMContentLoaded`. Then `regexToAllowSyncUrlLoading` for Torn URLs. | B1 | Large change. Needs maintainer agreement. | Script `probeStart` within 50 ms of Tampermonkey. `cb.shouldOverrideUrlLoading` gone for Torn URLs. |
| C. Widget isolation | Build `InAppWebView` once. Split the chrome into small widgets. Selectors in place of whole-provider listening. `TickerMode` for the drawer. `GetBuilder` IDs. | A1 (progress bar) | Medium. Touches many files. | `frames.uiOver16` in the Dart trace during loads and scrolls. `janky_pct` in `adb-bench.sh`. |
| D. Plugin fork patches | `pluginScriptsForMainFrameOnly: true`. If Dart has no listener, do not send scroll and console events. If nothing changed, skip the content-world script update. A batch API for scripts. Allow iframe navigations at once. | None | Plugin fork (Manuito83/flutter_inappwebview) | Platform channel message count per page. |
| E. API, storage and startup | Share HTTP clients and decode once. Use `Isolate.run` for large JSON. Delay `_saveTabs`. Move large values out of the preferences database. Start services that the first frame does not need later. Turn on the prewarm unmount. | None | Yes | Cold start to first page (`am start -W` plus `nav.load`). `frames.uiOver16` while idle in the browser. |

Do A1, B1 and the prewarm value first. They are small, they hit every user, and they make the later measurements clearer. Then do A2 and B2, which give the largest gains and need agreement from the maintainer. C can run in parallel with A2 and B2. D and E are independent.

## Questions for the maintainer

These items change behavior or depend on reasons that the code does not show. Ask the maintainer before you change them.

1. `PDA_http*` requests go through `dart:io`, without the WebView cookies. Tampermonkey's `GM_xmlhttpRequest` uses the browser network stack, with cookies, the HTTP cache and connection reuse. An in-page `fetch` for same-origin and CORS-enabled URLs is faster. Is the current design deliberate, for example for Torn's rules on scripts or for user safety?
2. What is the live Remote Config value for `browser_engine_prewarm_unmount_after_load`, and what did the hardware layer A/B test show?
3. Why does `onLoadStart` parse the HTML? Does any feature depend on the old document at that moment?
4. Is the Torn Chat engine on `develop` (a private module, only a stub in the public repo) on the hot path of page loads? This analysis did not have its source.

## Repository notes

- The fork's `master` branch (`xentac/master`) is about 620 lines behind upstream in `webview_full.dart`. The branch `fix/gm-handler-reinject` is already merged upstream in PR #480. Sync the fork with `origin/develop` and delete that branch.
- This work is on the branch `perf/analysis`, based on `origin/develop` at `fe76815d`. It is not pushed yet.
- The public config stubs (`lib/config/*.dart.example`) do not match `native_auth_provider` on upstream code. `flutter analyze` reports two errors about `requestTornRecurrentInitData` on clean upstream code. This is not related to this work.
