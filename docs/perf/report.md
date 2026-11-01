# Torn PDA browser performance: analysis and plan

## Summary

Chromium is not the cause of the slow Torn PDA browser. The Android System WebView is the same engine that Chrome uses. The cause is the work that Torn PDA does around the engine, and the thread on which it does that work.

Since Flutter 3.29, Dart code runs on the Android main thread, and in Flutter 3.47 you cannot turn this off. The app embeds each WebView with legacy Hybrid Composition. In that mode, Flutter also rasterizes on the main thread, and every touch on the WebView goes through Dart before the WebView receives it. So Dart work on the main thread delays taps, the start of scrolls, navigation decisions and bridge replies.

Torn PDA does a lot of that work on each page load. A plain Torn page with the default settings causes:

- about 12 full copies of the page HTML, each parsed in Dart (10 of them from one travel check that runs on every page),
- 25 or more Dart-to-WebView round trips, and more with userscripts,
- one bridge message for each subresource,
- many rebuilds of the 7,500-line browser widget,
- two injected scripts that watch the whole page for its full life.

Firefox with Tampermonkey does none of this work.

The app reads data from the page in about 75 places, with six different methods. This report recommends one page data layer in place of all of them. It is the largest single change in the plan. The other changes are smaller and independent. Each one has a metric from the measurement tools in `tools/perf/`.

The user prompt that started this work was cut off at "a similar app that". This report reads it as "a similar app that is as fast as Firefox with Tampermonkey, with the same features".

## Scope and evidence

Read this section before you use any number in this report.

- Nobody ran the app for this report. No Android device was available. Every count comes from reading the code. Every millisecond figure is an estimate.
- The tools in `tools/perf/` and `lib/utils/perf/` replace the estimates with numbers. `docs/perf/measurement.md` tells you how to use them. Each finding names the metric that proves or disproves it.
- The analysis covers upstream `origin/develop` at `fe76815d`. Line numbers are for the branch `perf/analysis` at commit `549025d1`. That branch adds the measurement hooks, which move most lines in `webview_full.dart` down by about 11.
- The plugin is the Manuito83 fork of `flutter_inappwebview` at `765d75b6`, as pinned in `pubspec.yaml`. Engine statements refer to the Flutter 3.47.9 source.
- Two adversarial reviews tested the first version of this report against the code. This version includes their corrections.
- "Verified" means that the code path was read and found to work as described. "Suspected" means that the mechanism is clear but the size of the cost is not known.
- The full list of page reads is in `docs/perf/page-data-inventory.md`.

## The central problem: one thread does everything

Four facts combine. All four are verified in the source.

1. Flutter 3.29 and later run the Dart UI isolate on the Android platform thread. In Flutter 3.47, the opt-out flag `DisableMergedPlatformUIThread` only throws an exception (`FlutterEngineFlags.java`). On Android, an engine start without the merge stops with a check failure (`switches.cc`).
2. The app uses legacy Hybrid Composition for every WebView. The plugin default for `useHybridComposition` is true, and the app does not change it. When a frame contains a platform view in this mode, the raster thread merges into the platform thread (`AndroidExternalViewEmbedder::PostPrerollAction`). Flutter also draws its whole UI through a `FlutterImageView` while the platform view is on screen (`PlatformViewsController.convertToImageView`).
3. In this mode, every touch on the WebView goes through Dart. `FlutterMutatorView.onInterceptTouchEvent` returns true, so the event goes to the Dart gesture arena. Dart sends it back over the platform views channel, and only then does `PlatformViewsController.onTouch` call `dispatchTouchEvent` on the WebView.
4. Android WebView runs the browser side of Chromium on the app main thread. `WebViewClient` callbacks, `evaluateJavascript` results, and `callHandler` replies (posted to the WebView looper) all wait for that thread.

So while Dart parses a 300 KB page or rebuilds the browser widget, these things wait:

- every tap, and every touch-move sample, including the start of a scroll,
- navigation decisions (`shouldOverrideUrlLoading`, `onPageStarted`, `onPageFinished`),
- replies to userscript calls through the bridge,
- results of `evaluateJavascript`.

These things do not wait, because they run in the renderer process: the network, HTML parsing and the page's own JavaScript. For a fling that is already in progress, the effect is not known. Android WebView can pace renderer frames from the app UI thread. Measure this with Perfetto: compare main-thread slices with the WebView frame timeline.

In Firefox, the equivalent thread is mostly idle. This changes how to judge each fix. The goal is less Dart main-thread work during page loads and interactions. A different composition mode alone does not remove that work.

## Findings

A tier 1 finding is on by default, happens on every navigation, and has a large cost. A "tier 1, conditional" finding is large but applies only to some users. A tier 2 finding applies only to some pages or settings. A tier 3 finding is background or startup cost.

### Tier 1: every user, every page

#### 1.1 The travel check copies and parses the page 10 more times after each load

In `onLoadStop`, the app calls `_travelHandler?.assessTravel(document)` on every page (`webview_full.dart:1974`). Each tab gets a travel handler in `onWebViewCreated`, and there is no URL gate. The call is not awaited.

In `travel_handler.dart:53-66`, the function looks for a `.travel-home` element. If the page has no such element, the function loops 10 times. Each loop waits 200 ms, calls `getHtml()`, and parses the result with `package:html`. A page has no such element unless you are abroad, so the loop runs on almost every page.

Each `getHtml()` costs more than one copy of the page:

- It first calls `getSettings()`. Native code builds the full settings map, and Dart then runs `InAppWebViewSettings.fromMap` over about 200 fields.
- Then it evaluates `outerHTML`, which blocks the page's own main thread while it serializes the DOM.
- If `outerHTML` returns empty, it downloads the page again over HTTP, without cookies.

After the loop, the function calls `onTravelStatusChanged(false)`, which is one more `setState`. So each page load causes 20 round trips, 10 DOM serializations and 10 Dart parses in the 2 seconds after load. You often tap the next link in those 2 seconds. The abroad stock check in the same file (`travel_handler.dart:103`) has a second loop of the same type.

Fix: query `.travel-home` in the page, with a short-lived `MutationObserver` and a timeout, and post the result once. The element can appear late, so a single query is not enough. Run this only where travel is possible. The page data layer (below) does this by design.

Measure with: `counts.getHtml` per navigation and `lag.over50` in the Dart trace.

#### 1.2 The app reads the page in many places, with many methods

The inventory in `docs/perf/page-data-inventory.md` lists about 75 places where the app reads page data:

| Method | Count |
|---|---|
| `getHtml()` and a Dart `package:html` parse | 19 sites, 6 of them with retry loops of 5 to 30 attempts |
| `evaluateJavascript` calls whose result Dart uses | 8 |
| Injected JavaScript that reads, polls or observes the DOM | 24 (9 `MutationObserver`s, about 14 `setInterval` loops) |
| Injected JavaScript that pushes page data to Dart | 10 handlers |
| URL, title, history and resource URL tests | 15 groups |

On every page, by default:

- `onLoadStart` copies and parses the page (`webview_full.dart:1757`). Only one assessor uses that document, and only on `loader.php`. At that moment the new document has barely started to parse, so the copy is nearly empty.
- `onLoadStop` copies and parses it again (`webview_full.dart:1960`) for the title, the travel check and the login error test. The login error test serializes `body.innerHtml` again for a string search.
- `_assessGeneral` runs at both `onLoadStart` and `onLoadStop`, so some scripts are injected twice per navigation.
- Section tests in `onProgressChanged` can start more copies before the first one finishes, because the trigger flags are set only after the awaited copy.

Each parse runs on the main thread. A `package:html` parse of a 200 to 400 KB page takes an estimated 20 to 80 ms on a mid-range phone. Many reads also wait with fixed delays and retry, which costs time and is fragile.

Fix: the page data layer (below).

#### 1.3 The progress bar rebuilds the whole browser widget on each frame

`_onProgressAnimationUpdate` calls `setState` on each animation tick (`webview_full.dart:7457`). `_animateProgressTo` restarts a 300 ms animation on each `onProgressChanged` event. The load bar setting only hides the bar, so the animation also runs with the bar turned off.

Each rebuild runs the full `WebViewFull.build` and creates a new `InAppWebView` widget. The plugin's `build()` then runs `initialSettings.toMap()` over about 200 fields. The native view is reused, but the Dart work happens on each frame. That is up to 18 rebuilds per progress event at 60 Hz, and up to 36 at 120 Hz. Tabs in `Offstage` that load also do this, because `Offstage` does not stop their tickers.

Each `WebViewProvider.notifyListeners` call also rebuilds every awake tab through the `Consumer<WebViewProvider>` at `webview_full.dart:912`. Each navigation causes at least two of these calls (`reportTabLoadUrl` and `reportTabPageTitle`), and each of them also runs `_saveTabs`.

Fix: drive the bar from a `ValueNotifier` or an `AnimatedBuilder` that wraps only the 2 px bar. If the bar is off or the tab is not visible, skip the animation. Track C removes the rebuild of the platform view in general.

Measure with: `counts.setState` and `counts.WebViewProvider.notify` per navigation in the Dart trace.

#### 1.4 Link navigations are cancelled, sent to Dart, and started again

The app sets `useShouldOverrideUrlLoading: true` (`webview_full.dart:640`). In the plugin, the Android client returns "cancel" for each renderer-initiated main-frame GET navigation and waits for Dart (`InAppWebViewClientCompat.java`). This includes each hop of a server redirect. If Dart allows the navigation, the client calls `loadUrl` again. The network request does not start until the Dart callback finishes. Form POSTs, back and forward, reload and same-document navigations do not go through this path.

Before the Dart callback answers, it does this work:

- an optional hit test. With `hitInMiniProfileOpensNewTab` on, mini-profile links also get a full `getHtml` and parse,
- userscript matching (see 1.7),
- `_addUserScriptsAvoidDuplicates`: parallel `removeUserScriptsByGroupName` calls, then `addUserScripts`. The plugin adds the scripts one at a time, each with the full source. The remove-then-add order defeats the plugin's own duplicate test, so every call goes to native code.

`onLoadStart` then registers the same document-start scripts a second time, and `_injectMissingDocumentStartScripts` runs at both `onLoadStart` and `onLoadStop`. Each run rebuilds the large handler bundle strings and sends a probe `evaluateJavascript`.

Two smaller problems are in the same callback:

- For iframe navigations, Dart runs this work with the iframe URL, but the plugin ignores the answer.
- For `http://` URLs, the callback starts an `https` load and also returns "allow". So two navigations race.

Fix, short term: return "allow" at once for iframes. If the set of matching scripts did not change, do not change the registration. Register document-start scripts once per navigation, not twice. Fix the `http` race. Fix, long term: track B, then set `regexToAllowSyncUrlLoading` to `https://www\.torn\.com/.*` so that Torn navigations do not go through Dart. The plugin uses a full match, so the pattern must end with `.*`. This setting is for Android only.

Measure with: `tap.tapToNavStart` in the probe, for PDA and for Firefox, and `cb.shouldOverrideUrlLoading(preNav)` in the Dart trace.

#### 1.5 Each subresource sends a message through the bridge

The app sets `useOnLoadResource: true` (`webview_full.dart:639`). The plugin then injects a `PerformanceObserver` into every frame. For each resource, the observer calls `callHandler`. The message goes as JSON through a synchronous Java bridge call, then to the main looper, then over the method channel to Dart. An `evaluateJavascript` call then resolves the promise. The plugin setting `pluginScriptsForMainFrameOnly` is false by default, so iframes also get the observer.

The Dart side of `onLoadResource` does real work only on a few pages: trades, vault, jail, bounties, properties and factions. All other resources pay the bridge cost for nothing. Torn pages load about 100 resources, and polling requests keep the messages going after load.

Fix: do not patch XHR or `fetch` for this, because many Torn userscripts patch them too. Instead, patch the plugin's observer script to call the handler only for URLs that match a pattern from Dart. This keeps the same mechanism on iOS and removes about 99 % of the messages. The page data layer then removes the remaining uses. The code comment near the settings says that AJAX interception broke `onLoadResource` on iOS, so test on iOS first.

Measure with: `bridge.byName.onLoadResource.n` in the probe.

#### 1.6 Injected scripts watch the whole page for its full life

Three injected features run on every Torn page by default:

- `chainWebReader` is on by default (Remote Config `webLiveAllowed`). On every `onLoadStop` (`webview_full.dart:1883`), it starts a `MutationObserver` on the whole document with `subtree` and `characterData`, plus a 1-second interval. It reads the chain bar from Torn's React and Redux state.
- Chat highlight (`highlightChat`, default true, `webview_full.dart:3021`) polls for `#chatRoot` 20 times at 500 ms. Then it runs a permanent 1-second `markAll` interval and a `subtree` and `characterData` observer. `injectCSSCode` adds one more `<style>` element on every `onLoadStop`. On pages with no chat root, it writes a `console.warn`, which rebuilds every awake tab (see tier 2).
- The chat cache trim script reads every `localStorage` key and value at document start, before Torn's own scripts run. Then it sends a `PDA_localStorageMeasured` message to Dart (`js_handlers.dart`, near line 86).

Observers with `subtree` and `characterData` run on every DOM change. Torn's DOM changes often (timers, chat, bars).

Fix: one shared observer in the page data layer, with work batched per animation frame. Measure the storage size once per session, not on each page.

Measure with: `hooks.moInjected`, `hooks.moCbMsInjected` and `hooks.ivCbMsInjected` in the probe, with the probe's hooks injected first (see "Track 0").

### Tier 1, conditional: large, but only for some users

#### 1.7 Userscripts run late and cost Dart work on every navigation

This cost applies to users with userscripts. It grows with the number of scripts installed. There are four parts, all verified.

1. `@run-at document-end` scripts run from `onLoadStop` with `evaluateJavascript`, one at a time. `onLoadStop` fires after the window `load` event, which waits for every image. Tampermonkey runs these scripts at `DOMContentLoaded`. On Torn's image-heavy pages, the difference can be seconds. The plugin's own native "document end" option also waits for `load` on Android, so a switch to that option does not help.
2. Before the first end script runs, `onLoadStop` awaits many `removeUserScriptsByGroupName` calls in sequence (`webview_full.dart:1913`). It makes one call for each script that does not match the page, including disabled scripts. With 40 installed scripts and 3 matches, that is 37 round trips. On iOS, each removal rebuilds the whole `WKUserContentController` and sends every script source to the web content process again. It does this also for a removal that matched nothing.
3. `getCondSources` in `userscripts_provider.dart` returns an `UnmodifiableListView` over a lazy `where` and `map`. Each `length` or index access runs the whole chain again, so a loop over the result is quadratic. `matchesTarget` in `userscript_model.dart` compiles new `RegExp` objects for each `@match` pattern on every call. `adaptSource` runs regular-expression replacements over the full source on each access.
4. A document-start script that matched the previous page stays registered until the next `onLoadStop`. So it also runs on the next page, and its `@match` is not tested again. This is a correctness bug, and it wastes work.

Fix, short term: run all end scripts first, in one `evaluateJavascript`. Remove only the groups that are registered. Cache compiled patterns. Make `getCondSources` return a real list. Fix, long term: track B.

Measure with: `probeStart` of a `document-end` copy of the probe, in PDA and in Tampermonkey.

#### 1.8 Userscript network calls wait for the page to finish loading

Each `PDA_http*` helper, `PDA_storage` and `PDA_evaluateJavascript` awaits `window.__PDA_platformReadyPromise` (six places in `remote_snippets.dart`, and `js_handlers.dart`). That promise resolves on the plugin event `flutterInAppWebViewPlatformReady`. Android sends that event only in `onPageFinished`, after `load`. So a script such as FF Scouter cannot start its request until every image on the page is loaded. Under Tampermonkey the request starts at once.

The gate exists because the first load can start before Dart registers the handlers. The native view starts its first load before Dart's `onWebViewCreated` runs, and that callback can first await `clearAllCache`. So the handlers are not certain to exist at document start. But the plugin event is a much later signal than necessary.

There is also a correctness bug. If a script requests the same URL again within 2 seconds, each helper returns `undefined` (`remote_snippets.dart`, the `loadedPdaApiGetUrls` test). A second script that requests the same URL gets no response.

Fix: set a "handlers registered" flag from Dart at the end of handler registration. Gate the helpers on that flag, not on the plugin event. Keep the 2-second deduplication, but return the first call's promise. Read the history of the gate first (`git log -S __PDA_platformReadyPromise`), and test the early call on iOS.

Measure with: `bridge.firstAt` in the probe. It must move from after `nav.load` to near `probeStart`.

#### 1.9 With web chat hidden, each subresource first makes a blocking HEAD request

If the native chat module is compiled in and the user hides Torn's web chat, the app sets `contentBlockers` to `[tchatBundleBlocker]` (`webview_full.dart:682`). The plugin then sends each request through `shouldInterceptRequest` to `ContentBlockerHandler.checkUrl`. Before it tests any rule, `checkUrl` calls `getResourceTypeFromUrl`, which makes a blocking `HttpURLConnection` HEAD request for every `http` and `https` URL. The request has no cookies and a 15-second timeout. So every subresource waits for one more full network round trip.

The public repository has only a stub of the chat engine, so the public build does not do this. Official builds for users who hide web chat do.

Fix: patch the plugin so that it skips the HEAD request for rules without a `resourceType` trigger. Or block the chat bundle with a document-start script.

Measure with: `res.lastEnd` and `nav.load` in the probe, with chat hidden and shown.

### Tier 2: some pages, some settings

| Finding | When it applies | Fix |
|---|---|---|
| On attack pages, every progress tick above 75 % does `getHtml` and a full parse, then discards the result. The condition at `webview_full.dart:3891` is always true once `_attackTriggered` is set. The flag stays set until a section page clears it. | Attack pages, with `extraPlayerInformation` (default true) | Correct the condition. |
| Each JavaScript console line calls `TerminalProvider.notifyListeners`. `WebViewFull.build` listens to that provider (`webview_full.dart:843`), so every console line rebuilds every awake tab. The terminal text is an unbounded string that is copied on each line. | Pages or scripts that log, and see 1.6 | Use `listen: false` in `build`. Cap the buffer. |
| `launchShowCases` runs on each build of `WebViewFull` and schedules a 1-second timer each time. The stack view limits this to once a minute, but `WebViewFull` does not. | All loads, with 1.3 | Limit it, or run it once after the first frame. |
| `onProgressChanged` makes a `getUrl()` round trip on each event above 10 % (`webview_full.dart:1782`). With `removeAirplane` on, it makes a second one. Above 75 % it also calls `endRefreshing()` on each event. | All loads | Use the URL from `onLoadStart` and `onUpdateVisitedHistory`. Call `endRefreshing()` once. |
| Section reads use retry loops. Trades make 2 to 4 copies per trigger, on every `trade.php` resource. The vault makes up to 11 copies. Jail and bounties make 1 to 3 copies, only to test that a list exists. City items poll up to 30 times. A profile by name makes up to 6 copies, and the travel agency makes 5. | These pages | The page data layer. |
| With the cache turned off, `cacheMode` is `LOAD_NO_CACHE` and each new WebView clears the cache. | Users who turned the cache off, or the Remote Config value "off" | Ask users with slow loads to make sure that the cache is on. Look at `res.cacheRatio` in the probe. |
| The Temporary quick items feature installs permanent global `fetch` and XHR wrappers that clone and parse every later response. | Users of that feature | Parse only the responses of the endpoint it needs. |
| `onScrollChanged` sends a channel message for each scroll offset change. Dart only stores the position for a later restore. | All scrolls | Read the scroll position only for a restore. |

### Tier 3: background and startup

| Finding | Fix |
|---|---|
| After the first browser open, the 1x1 prewarm WebView stays mounted under all content in the root `Stack`. The Remote Config value `browser_engine_prewarm_unmount_after_load` is false in the code default (`drawer.dart:728`). The live value is not known. While it is mounted, every frame contains a platform view. So native Flutter pages also run in merged Hybrid Composition mode and draw through `FlutterImageView`. | Ask the maintainer for the live value. Change the code default to true in the fork for tests. |
| Each awake `WebViewFull` has a `Consumer<WebViewProvider>` around the whole tab, including the `InAppWebView`. The stack view, the drawer, the profile page and the loot page also listen to the whole provider. `WebViewProvider` has more than 60 `notifyListeners` calls. | Use `Selector` or `context.select` for the fields each widget needs (track C). |
| Each navigation calls `_saveTabs` twice. Each call encodes every tab and its history to JSON and writes to sembast. All preferences go through one sembast database behind one lock. Large values (spies, FF Scouter cache, war factions) are in the same database, so compaction rewrites them. The compaction cost is suspected. | Delay `_saveTabs` by 2 seconds and merge calls. Move large values to their own files. |
| `ChainStatusController` calls `update()` with no IDs every second while a chain widget is active. This rebuilds the app border and the tab bar menu. | Use `GetBuilder` IDs. |
| The TCT clock, the loot page and several chat widgets (roster, player cards, faction operations) call `setState` from 1-second timers. They also do this behind the browser, because `Offstage` and `IndexedStack` do not stop timers or tickers. | Gate the timers on the browser state. Wrap hidden branches in `TickerMode(enabled: false)`. |
| API v2 creates a new `ChopperClient` for each call and decodes each response twice on the main thread. API v1 uses the top-level `http.get`, which opens a new connection for each call. Except for faction crimes, large responses are decoded on the main thread. | Share one client. Decode once. Use `Isolate.run` for large responses. |
| `main()` runs about 14 awaits in sequence before `runApp`, including WorkManager, HomeWidget and the notification permission request. | Move the ones that the first frame does not need to after the first frame. |

## The page data layer

This section answers a direct question: is one high-performance interface to the game page better than many separate reads? Yes. The inventory shows why.

### What is wrong with the current reads

- They copy the whole DOM to Dart to read a few values. That moves hundreds of KB through the bridge and parses them on the main thread.
- They guess the time at which data is ready. Many use fixed delays and retry loops (5 to 30 attempts).
- They run at fixed callbacks (`onLoadStart`, `onProgressChanged`, `onLoadStop`, `onLoadResource`), not at changes of the data. So they run too early, too late, or too often, and they miss single-page route changes.
- They are spread over a 7,500-line file. About 25 fragile selectors use Torn's hashed class names (`row___`, `titleContainer___`, `logInWrap_` and more). If Torn changes a class, the fix is in many places.
- The same fact is computed many times. For example, the page title is read in several callbacks and serves as both the tab title and a section gate.

### Design

One JavaScript module, registered once per tab as a document-start script. It replaces every Dart-side read and every page-reading snippet.

1. Detection. At document start, the module finds the section from `location`. After the DOM is ready, it tests the section against the DOM. It follows `hashchange`, `pushState` and `popstate` for single-page routes.
2. Extractors. Each section has one extractor that reads only the fields that features need. One shared `MutationObserver` on the document runs the extractors for the active section, batched per animation frame. An extractor reports a fact only after a change of its value.
3. Network facts. Where Torn loads data with XHR or `fetch` (trades, vault, jail, bounties, armoury, item search), the module reads the response, not the DOM. It uses the filtered `PerformanceObserver` from 1.5 to learn which request finished, and reads the result once.
4. Transport. The module sends typed events to Dart through one handler, `pdaPage`, for example `{type: "section", section: "trade"}` or `{type: "travel", abroad: true, country: "mex", stock: [...]}`. Dart keeps the latest facts per tab in a `PageFacts` object. Features listen to the facts that they need.
5. Selectors in one place. All selectors are in one table in the module. Remote Config can replace the table, so a Torn class change does not need an app release.
6. Actions stay separate. Features that change the page (buttons, fills, highlights) keep their own scripts, but they run on page facts, not on their own polling.

The schema of facts follows from the inventory:

| Group | Facts | Main consumers |
|---|---|---|
| page | URL parts, section, title, ready state | Tab title, all section gates |
| auth | login form present, login error, legacy loader notice | Automatic login, `page.php` redirect |
| travel | abroad, country, stock list, money on hand | Home icon, stock upload, buy-max |
| chain | current, max, timeout, cooldown, active | Chain widgets (already pushed by `chainWebReader`) |
| profile and attack | target user ID, defender title, profile fields | Profile check, hospital timer, age to words |
| trade | trade ID, seller, finished, left and right lists | Trade calculator |
| vault | transactions | Vault share |
| jail and bounties | lists | Jail and bounty widgets and filters |
| city and shops | map item IDs, purchase results | City items, shop helpers |
| items and faction | item lists, armoury tab, crimes rows, give-money balance | Quick items, natural nerve bar, bank vault |

### Rules for the layer

- Keep the public JavaScript handlers unchanged. Torn's own site code and userscripts call `isTornPDA`, `webThemeChange`, the notification and timer handlers, `PDA_http*`, `PDA_storage`, `PDA_evaluateJavascript` and `PDA_getTabState`. The inventory lists about 22 of these.
- The chain mini window has its own WebView and its own copy of the chain reader. Use the same module there.
- Run the module in shadow mode first. In development builds, run it next to the current Dart reads and log every difference. This finds problems that test fixtures miss.
- Without changes, the module must cost almost nothing. The shared observer must do no work for sections that are not active.

### Expected effect

On a plain page, the layer removes about 12 `getHtml` calls and all Dart parses. It removes the fixed-delay retries. It uses one observer instead of several. It sends a few small `pdaPage` messages instead of one message per subresource. On section pages, data arrives as soon as Torn renders it, not after a retry delay.

Measure with: `counts.getHtml` equals 0, `lag.over50` in the Dart trace, and `bridge.byName` in the probe.

## Questions about the design

### Every navigation goes through Dart

Dart must approve each navigation because userscripts are registered per navigation and because of a few special cases: external schemes, locked tabs, the mini-profile option that opens a new tab, and `.user.js` links. Most of these cases can be decided from the URL alone, without a round trip.

Recommendation: after track B, let Torn URLs load without a Dart decision with `regexToAllowSyncUrlLoading`. That setting bypasses locked tabs, the mini-profile option and `.user.js` install links. Move those tests into page JavaScript, or keep those URLs out of the pattern.

### Dart manages userscripts on each navigation

Tampermonkey registers scripts once and matches URLs in the page. PDA adds and removes scripts from Dart on each navigation.

Recommendation: register one document-start loader. Register it again only after a change to the script set or the API key. The loader contains three things:

- the PDA handler bundle,
- a small list with the ID, match patterns and run time of each script,
- each enabled script, wrapped in a function.

At document start the loader matches `location.href`, and then does this:

- It runs `document-start` scripts at once.
- It runs `document-end` scripts on `DOMContentLoaded`. If the document is already past loading, it runs them at once.
- It runs `document-idle` scripts shortly after `DOMContentLoaded`, and no later than `load`.

This removes the per-navigation registration work. It fixes 1.7 part 4 by design, and it makes back and forward navigation work without the current probe. Do not use the plugin's native "document end" injection, because it waits for `load` on Android.

Three risks apply. A function wrapper changes the scope of top-level `var` declarations, which some PDA-only scripts can depend on. Tampermonkey has the same behavior, so most scripts already accept it. A large loader adds parse time to every document, so measure it with 40 scripts. Port the `@match` test cases from `test/models/userscript_model_test.dart` to the JavaScript matcher.

### One 7,500-line widget is the browser

`WebViewFull` owns the platform view, the app bar, the panels, the progress bar and all section logic. Any `setState` rebuilds all of it.

Recommendation: create the `InAppWebView` widget once and keep the same instance, so that Flutter skips it on rebuild. Today some settings reach the WebView through a rebuild (cache mode, the hardware layer value). Send those through `setSettings` instead. Move the app bar, panels, progress bar and chain widget into small widgets that listen only to what they show. This is track C.

### Which Android composition mode to use

- Legacy Hybrid Composition (current): the WebView scrolls in its own surface, but Flutter raster work merges into the main thread, and touches go through Dart.
- Texture Layer Hybrid Composition (`useHybridComposition: false`): the Flutter documentation calls it janky for fast scrolling of a web view. Do not make it the default. You can test it behind Remote Config.
- HCPP (Hybrid Composition++): the forward path. It removes the raster thread merge (`AndroidExternalViewEmbedder2::PostPrerollAction` returns success). It needs Android 14 (API 34) and Impeller with Vulkan, and you turn it on with the manifest value `io.flutter.embedding.android.EnableHcpp`. On other devices it falls back by itself. It is experimental in Flutter 3.47, and the plugin does not use its API yet. After the plugin supports it, test it.

No mode removes Dart work from the main thread. The page data layer and tracks A and C give more benefit than any mode change, so do them first.

The WebView hardware layer is a separate setting. With Hybrid Composition and `hardwareAcceleration: true`, the plugin calls `setLayerType(LAYER_TYPE_HARDWARE)`, which adds an offscreen pass. The name misleads: `false` does not mean software rendering. Upstream already has a Remote Config A/B test for this (`webViewHardwareLayerActive`). Ask the maintainer for the result of that test before you change it.

### Too many awake tabs

All WebViews of the app share one renderer process. So the polling, chat and userscripts of background tabs run on the same renderer main thread as the visible tab. Each awake tab also adds rebuilds and tickers in Dart. The app already has controls for this: `browser_max_live_tabs_default`, `browser_tab_sleep_minutes_default`, `browser_park_background_tabs_default` and hidden-tab loading.

Recommendation: before you write code, measure one live tab against the default, and parking on against off. Also set `rendererPriorityPolicy` to `WAIVED` for hidden tabs.

### A different engine or a native browser

- Custom Tabs and Trusted Web Activities cannot inject scripts. They are not an option.
- A native Android Activity browser, such as the plugin's `InAppBrowser`, removes the Flutter embedding. But the timers, chain widget and other Flutter overlays then need native versions or a second Flutter view. The effort is high.
- GeckoView with a bundled WebExtension can do what Firefox with Tampermonkey does. But it needs a new Flutter plugin and adds about 60 to 80 MB per ABI. It still runs under a composition mode, and it has no iOS version.

Recommendation: do not change the engine. Do the page data layer and tracks A to C first. Then compare the app with a minimal `flutter_inappwebview` app (see "Track 0") to measure how much of the remaining gap comes from the embedding.

### Ideas with little value here

These were considered and are not recommended, so that nobody needs to ask again. Dart AOT has no profile-guided optimization. R8 is already configured and does not touch Dart. Impeller is already the default in Flutter 3.47. The WebView HTTP cache size cannot be configured. Preconnect does little, because almost everything is on one host.

## Work plan

### Order

1. Track 0: measurement and preparation. Nothing else starts before the baseline exists.
2. A1 and B1: small fixes, one pull request per fix. They hit every user and make later measurements clearer.
3. R: the split of `webview_full.dart` into part files (see below).
4. P, B2 and C in parallel, after R. D and E at any time.

### Tracks

| Track | Content | Depends on | Acceptance metric |
|---|---|---|---|
| 0. Measurement | Inject the probe's hook wrappers first in `PDA_PERF` builds, so that PDA's own document-start code is counted. Build a minimal `flutter_inappwebview` app with the same plugin pin, as a control. Record the baseline on one device: PDA, the control app, and Firefox with Tampermonkey. Record the WebView and Firefox versions. Send `perf_trace.dart` upstream as a developer tool with no release cost. | None | A baseline file for each subject. |
| A1. Dart hot path, quick fixes | Fix 1.1 (travel check, with an observer and a timeout) and 1.3 (progress bar). Fix the attack condition, the terminal listener, the show-case timer and the `getUrl` per progress event. From 1.4: add the iframe fast path, fix the `http` race, and register document-start scripts once per navigation. Delete the `onLoadStart` copy after the maintainer says that nothing needs it. | 0 | `counts.getHtml` at most 2 on a plain page. `counts.setState` under 10 per navigation. `lag.over50` lower than baseline. |
| B1. Userscript quick fixes | 1.8 gate and duplicate promise, end scripts first in one call, remove only registered groups, cache patterns, a real list from `getCondSources` | 0 | `bridge.firstAt` near `probeStart`. `cb.onLoadStop.wallMs` lower than baseline. |
| R. Split `webview_full.dart` | Move code into `part of` files without changes: navigation callbacks, resource callbacks, section reads, userscripts, build. Each callback becomes a one-line call to a named method. Agree this with the maintainer and do it right after a release. | A1 merged (smaller conflicts) | No behavior change. The diff is moves only. |
| P. Page data layer | The design above, with shadow mode first, then one section at a time behind a Remote Config flag. Includes the filtered resource observer from 1.5 and the shared observer from 1.6. | R | `counts.getHtml` equals 0. No `onLoadResource` messages on plain pages. No feature differences in shadow mode. |
| B2. Document-start loader | Register once, match in JavaScript, run end scripts on `DOMContentLoaded`. Then `regexToAllowSyncUrlLoading` for Torn URLs. | B1, R | Script `probeStart` within 50 ms of Tampermonkey. `tap.tapToNavStart` within 50 ms of the control app. |
| C. Widget isolation | Build `InAppWebView` once. Split the browser chrome into small widgets. Selectors in place of whole-provider listening. `TickerMode` for hidden tabs and the drawer. `GetBuilder` IDs. Settings through `setSettings`. | A1 (progress bar), R | `frames.uiOver16` and `lag.over50` during loads and scrolls. `janky_pct` in `adb-bench.sh`. |
| D. Plugin fork patches | Filter the `onLoadResource` observer by URL. Skip the content blocker HEAD request (1.9). Send scroll and console events only to a listener. A batch API for scripts. Make `pluginScriptsForMainFrameOnly: true` an option behind Remote Config, because it removes the bridge from iframes and can break scripts there. | None | Platform channel message count per page. `nav.load` with chat hidden. |
| E. API, storage and startup | Share HTTP clients and decode once. Use `Isolate.run` for large JSON. Delay `_saveTabs`. Move large values out of the preferences database. Start services that the first frame does not need later. Test the prewarm unmount. | None | Time from process start to the first `loadEventEnd`. `lag.over50` while idle in the browser. |

### Regression testing

The existing tests in `test/` cover models, chat and parts of `WebViewProvider`. They do not cover the injected JavaScript, the WebView callbacks or the section reads. Use this strategy:

1. Fixtures. Save the HTML and the key XHR responses for about 30 page states. Include trades, vault, properties, city items, jail, bounties, item market, bazaar and quick items. Also include faction and chain, attack, hospital, travel (home, flying, abroad with stock), logged out and login error. Remove personal data. Keep the fixtures private.
2. The current Dart reads as the reference. Write Dart golden tests that run the current section reads on each fixture. Run the new JavaScript extractors on the same fixtures in headless Chromium, with a stub for `callHandler`, and compare the results. For this, move the injected JavaScript from Dart strings to asset files.
3. Loader tests. Run the B2 loader in headless Chromium with popular real scripts, such as FF Scouter. Test the run order, the timing against `DOMContentLoaded`, the `GM_*` and `PDA_*` APIs, and `@match` and `@exclude`.
4. Shadow mode on the live site, as described for the page data layer.
5. A manual checklist, made from the `_assess*` functions, the `*Triggered` flags and the `onLoadResource` branches. Run it on Android with each new Remote Config flag on and off. iOS needs the maintainer or a tester.

Keep automated runs on the live site few and at human speed, because of Torn's rules for scripts. The fixtures carry most of the testing.

### Getting changes accepted upstream

- Send the measurement hooks first. Then every later claim is a number that the maintainer can reproduce.
- Send A1 and B1 as one fix per pull request. Give each one before and after numbers and a short list of the features that you tested. The correctness bugs are the easiest to accept: the stale document-start script, the `undefined` duplicate response, the attack condition and the `http` race.
- For P, B2 and C, open an issue with the baseline first. Put each new path behind a Remote Config flag and a user setting, off by default, and keep the old path. `webViewHardwareLayerMode` and the tab parking flags are the pattern to copy.
- Expect resistance to: removing `onLoadResource` without an iOS plan, in-page `fetch` for `PDA_http*`, changed defaults of user settings, engine changes, and changes to the private chat module.
- Upstream `develop` changes fast. 17 of its last 74 commits touched `webview_full.dart`. Rebase each track on `develop` every week, and keep the measurement hooks in their own commit.

## Questions for the maintainer

These items change behavior or depend on reasons that the code does not show. Ask the maintainer before you change them.

1. `PDA_http*` requests go through `dart:io`, without the WebView cookies. Tampermonkey's `GM_xmlhttpRequest` uses the browser network stack, with cookies, the HTTP cache and connection reuse. An in-page `fetch` for same-origin and CORS-enabled URLs is faster. Is the current design deliberate, for example for API key safety or for Torn's rules on scripts?
2. What is the live Remote Config value for `browser_engine_prewarm_unmount_after_load`, and what did the hardware layer A/B test show?
3. Does any feature depend on the HTML copy in `onLoadStart`?
4. What does the private `ChatEngine.pageLoadJS` do on each page load, and how much does it cost? Only that file and `torn_chat_source` are stubs. The rest of the chat code is public.
5. Is the 2-second deduplication in the `PDA_http*` helpers a deliberate limit for the Torn API?

## Repository notes

- The fork's `master` branch (`xentac/master`) is about 620 lines behind upstream in `webview_full.dart`. The branch `fix/gm-handler-reinject` is already merged upstream in PR #480. Sync the fork with `origin/develop` and delete that branch.
- This work is on the branch `perf/analysis`, based on `origin/develop` at `fe76815d`. It is not pushed yet.
- The public stub for `native_auth_provider` does not match upstream code. `flutter analyze` reports two errors about `requestTornRecurrentInitData` on clean upstream code. This is not related to this work.
