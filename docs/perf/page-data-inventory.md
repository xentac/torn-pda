# Torn PDA: inventory of reads from the WebView page

Line numbers are for branch perf/analysis at commit 5b467276 (origin/develop at fe76815d plus the PerfTrace instrumentation, which adds about 11 lines near the top of webview_full.dart). `WF` = lib/widgets/webviews/webview_full.dart.
Cost key: **GH** = getHtml (2 platform round trips: getSettings plus an outerHTML eval that serializes the full DOM on the page main thread). **P** = Dart `package:html` parse of the full document. **RT** = one platform-channel round trip. **EV** = evaluateJavascript whose result Dart uses.

## A. getHtml() + package:html parse + querySelector (Dart side)

| id | file:line | trigger | what it reads | consumer | cost | gating | fragility |
|---|---|---|---|---|---|---|---|
| A1 | WF:1757 | onLoadStart (every nav) | Full doc goes to `_assessGeneral` (WF:3769). Only `_assessOldLoaderRedirect` (WF:4949) uses the document, through `outerHtml.contains("Please use the new endpoints")`. The other assessors look only at `_currentUrl`. | loader.php to page.php redirect | 1 GH + 1 P per nav | **Every page.** The doc is only needed on loader.php. | At onLoadStart the DOM is the old or empty document, so the parse is nearly useless. |
| A2 | WF:1960 | onLoadStop (every nav, including hash re-fires) | `.content-title > h4`, `[class^='titleContainer___'] h4` (title). `_assessGeneral` again. Travel check. Login errors. | Tab title (`_reportPageTitle`), travel, error cases | 1 GH + 1 P | **Every page** | `titleContainer___` is a hashed-prefix class |
| A3 | travel_handler.dart:53-66 (from WF:1974) | onLoadStop, every page | `.travel-home, .travel-home-header-button` (abroad flag) | `_travelAbroad` (home icon), then A4 | Not abroad means the **retry loop runs 10× (200 ms each): 10 GH + 10 P per page load** | **Every page, no URL gate** | Retry loop. The raw getHtml goes through PerfTrace with tab=null. |
| A4 | travel_handler.dart:88-170 | Abroad: after A3 | `div[class*="stockTableWrapper"] div[class*="row___"]`. `img.torn-item` src gives item id. `span` text `$` gives cost, `stock` gives quantity. Country from `[class*='titleContainer'] h4` or `.content-title > h4` (first 3 chars). | ForeignStockOut upload to YATA and Prometheus (RC-gated). `_handleTravelUI` injects hideItemInfo / buyMax. | Up to 10 GH + 10 P (250 ms each) | Abroad only | Hashed `row___`, `stockTableWrapper`. Country comes from the first 3 letters of the title. 3 s submit throttle. |
| A5 | WF:2079 | onLoadResource: resource URL has `trade.php`, or on trade.php before the first trigger. 2 s throttle. | page title (h4) | `_assessTrades` (A6) | 1 GH + 1 P per trigger, and it re-fires on every trade.php resource | trade.php | iOS also calls getUrl (WF:2084) |
| A6 | WF:4196-4330 | From A5, A13, or `_decideIfCallTrades` (WF:4454) | If the title is empty: wait 1.5 s, then GH again. Always a **second GH** to check for "The trade was accepted by" (WF:4223). `.color1 .left…` sanity check, then a 1.5 s retry with GH. `#trade-container .left/.right .color1..4 .name` (money/items/property/shares). `.right .title-black` (seller name). `#trade-container .log li .desc a[href]` XID (seller id). URL `&ID=` (trade id). | TradesProvider.updateTrades. The provider then regex-parses `innerHtml` (trades_provider.dart:144-269). Trade Calculator widget. | 2-4 GH + P per trigger | trade.php plus `getTradeCalculatorEnabled` (default true) | Retries with delays. HTML regex in the provider. |
| A7 | WF:2101 + 4485-4555 | onLoadResource `properties.php` (2 s throttle). First call goes to `_assessVault`. Later calls wait 2 s, then `_reassessVault` (WF:4572, GH). | `ul.vault-trans-list > li:not(.title)`, **retry up to 10× at 500 ms with GH**. vault_widget.dart:239-266 reads `.date .transaction-date/-time`, `.user.name[title]`, `.type`, `li.amount`, `li.balance`. | VaultWidget (vault share) | Up to 11 GH + P | properties.php plus title has "properties". Vault pref default true. | Double activation guards (`_vaultTriggeredTime`). Dom elements are passed into the widget. |
| A8 | WF:2131-2149 | onLoadResource `jailview.php` (500 ms throttle) | `.users-list > li` (exists?). Retries ×2 at 1 s with GH. | JailWidget, then `jailJS` filters in-page (C8) | 1-3 GH + P | jailview.php | iOS calls getUrl as well. The document is only used for an existence check. |
| A9 | WF:2167-2185 | onLoadResource `bounties.php` | `.bounties-list > li` existence, ×2 retries | BountiesWidget, then `bountiesJS` (C9) | 1-3 GH + P | bounties.php | Same pattern as A8 |
| A10 | WF:3900-3920 | onProgressChanged >75 (each tick) → `_assessSectionsWithWidgets` (not awaited) | Title h4 (section gate), plus the doc for city/trade/vault/profile/jail/bounty | Quick items, Crimes, Gym, City, Trades-off, Vault-off, Profile/Attack check, Jail, Bounties | 1 GH + P per tick while a section flag flips | URL `contains` item/crimes/gym/city/trade/properties/jailview/bounties/profiles/attack | **Race**: flags are set only after the awaited GH, so several ticks can each GH. **Bug (WF:3890-3891)**: `(!contains(attackUrl) \|\| !contains(attackUrl2)) && _attackTriggered` is always true on attack pages, so there is a GH every tick. |
| A11 | WF:4223 | Inside A6 | Raw HTML `contains("The trade was accepted by")` | Hides the trade widget | 1 GH (no parse) | trade.php | String match |
| A12 | WF:4572-4580 | Vault options callback, 2 s after a vault resource | Title plus vault list | A7 | 1 GH + P | properties.php | n/a |
| A13 | WF:4465-4469 | `_decideIfCallTrades` from trade options / `_tradesPreferencesLoad` | getUrl + GH + title | A6 | RT + GH + P | trade | n/a |
| A14 | WF:2870-2925 `assessErrorCases` | onLoadStop (reuses the A2 doc) | `body.innerHtml.contains("Email address or password incorrect" / "multiple failures from your IP address")`. `[class*='logInWrap_']`. After a growing delay: **GH again** to check again. | Auto re-login (native auth), toasts | Re-serializes the full body innerHtml (string search). +1 GH on login page. | Every page (native login exists) | Hashed `logInWrap_`. English strings. |
| A15 | WF:4964-5000 + webview_utils.dart:29-44 | Profile with `profiles.php?NID=` (name URL) | `WebViewUtils.waitForElement('a.profile-image-wrapper[href*="XID="]')`: **up to 6 raw GH + P at 1 s** | ProfileAttackCheckWidget (user id) | Up to 6 GH | extraPlayerInformation (pref default true) | Raw `getHtml()` is **not counted by PerfTrace** |
| A16 | WF:5372-5390 | onLoadStart on travelagency.php / page.php?sid=travel (30 s throttle) | `h4` text == "Travel Agency", **5× at 500 ms with GH** | Energy/nerve/life waste warning (then an API call) | Up to 5 GH + P | Travel URLs. Settings default true. | English title text |
| A17 | WF:2655-2682 `_hitShouldOpenNewTab` | shouldOverrideUrlLoading to profiles.php with a honors image hit | `getHitTestResult()` (RT) then GH: `[class*='profile-mini-_wrapper_']` | Open in new tab | RT + GH + P | Mini-profile honors click | Hashed class |
| A18 | WF:6037-6046 `cancelChainingBrowser` | Chaining browser cancelled | Title | Tab title | GH + P | Chaining only | n/a |
| A19 | webview_simple_dialog.dart:266-292 | onLoadResource `favicon.ico` while `captchaWorkflow` | Raw HTML contains `"success"` (×2, 500 ms) | Captcha callback | 1-2 raw GH (not PerfTrace) | Captcha dialog only | String match |

## B. evaluateJavascript / callAsyncJavaScript whose RESULT Dart uses

| id | file:line | trigger | reads | consumer | cost | gating | fragility |
|---|---|---|---|---|---|---|---|
| B1 | WF:4620-4644 + remote_snippets.dart:195-290 (`highlightCityItemsJS`) | `_assessCity` (from A10) | `window.torn.map.lmap.eachLayer`. Ids come from `iconUrls[0]` `city_items/<id>/`. Returns a JSON id list or `NOT_READY`. It also installs a 2.5 s highlight interval. | CityWidget (items found, joined with the items API) | **Up to 30 EV polls at 1 s** | city.php, title "city" (not raceway), CityFinder pref default true | Leaflet internals. RC-overridable snippet. |
| B2 | WF:2809-2822 `_injectMissingDocumentStartScripts` | onLoadStart (`!_handlersInjected`) and **every onLoadStop** (page has userscripts) | `window.__pdaOnce` keys that are missing | Re-inject the handler bundle and start scripts | 1 EV | Pages with active userscripts | n/a |
| B3 | WF:3086 `showPendingChat` | Chat re-shown on a background tab | `!!document.querySelector('#chatRoot *')` | Reload decision | 1 EV | Chat toggling | n/a |
| B4 | WF:3527-3600 `probeBlankPage` + `_blankProbeJs` | `scheduleBlankCheck` after onLoadStop (visible tab, Android, ≥3 s after load) | `readyState`, `elementsFromPoint` colours at 10 points. A native pixel probe follows. | Blank-page recovery | 1 EV + native call | Android, www.torn.com, visible | Injects a style |
| B5 | quick_items_widget.dart:600 `quickItemPickerJS` | User toggles the picker | Returns `grid-mode` / `picker-disabled` (`.thumbnails-icon.active`) | Picker UI | 1 EV | item.php, user action | n/a |
| B6 | WF:6788 | Download headers | `navigator.userAgent` | HTTP download | 1 EV | Downloads | n/a |
| B7 | WF:2266 | onDownloadStarting with a `blob:` URL | `callAsyncJavaScript` `fetch(blob).text()` | File save | 1 RT plus payload | Blob downloads | n/a |
| B8 | dev_tools_network.dart:38 | DevTools (user) | `performance.getEntriesByType("resource")` | Dev tools | EV | User-initiated | Out of scope |

## C. Injected JS that reads the DOM / polls / observes (acts in-page, or pushes to D)

| id | file:line | injected when | reads / watches | cost | gating | fragility |
|---|---|---|---|---|---|---|
| C1 | chain_web.dart:7-250 `chainWebReader` (WF:1881-1884, 6272) | Every onLoadStop on torn (`_chainWebAllowed`) | React fiber → Redux `sidebar.bars.chain` (amount, max, timestampToUpdate, endCoolDownTimestamp). DOM fallback: `a[class*="chainBar___"]` `barValue___`/`barTimeLeft___`/`progress___`/`cooldown___`. On attack pages: `attack.attackerUser.chain/chainEnd`, `labelTitle___`. | **Whole-document MutationObserver (subtree + characterData, 100 ms debounce) + 1 s setInterval, permanent.** Pushes D1. | **Every torn page.** RC `webLiveAllowed` default true. If `__pdaChainShown` is set and the page is visible, it sends. | Hashed classes. Depends on React internals. |
| C2 | js_snippets.dart:512-562 `chatHighlightJS` (WF:3022) | onLoadStop | `#chatRoot` (500 ms × 20 poll), `[class*='virtualItem___'] [class*='box___']`, `sender___`, `message___` | 1 s interval + observer on chatRoot | **Every torn page**, highlightChat default true | Hashed classes |
| C3 | remote_snippets.dart:649-728 `barsDoubleClickRedirectJS` (WF:5083) | `_assessGeneral` (**twice per nav**) | `[class*="bar___"]` | 300 ms wait loop | **Every torn page** | Hashed |
| C4 | js_snippets.dart:1011-1080 exitFullScreen header | `_assessGeneral` | `#topHeaderBanner > div.header-wrapper-top`, 300 ms wait. Then D10. | Interval until found | Full-screen + setting (default true) | n/a |
| C5 | js_snippets.dart:449 `removeChatJS` (WF:3045 `hideChatOnLoad`) | onLoadStart, **every onProgressChanged tick**, onLoadStop | `[class*='chat-app-container_'], #chatRoot` | EV per tick | If chat is hidden | n/a |
| C6 | js_snippets.dart:58-160 `ensureMinDocumentHeightForKeyboardJS` | onProgress/Stop/History (once per URL) | Document height, resize | Debounced | browserExtendHeightForKeyboard default false | n/a |
| C7 | js_snippets.dart:279-430 `addOthersBazaarFillButtonsJS` | `_assessGeneral` on `bazaar.php?userId=` | `amountValue_`, `price___`, `#user-money`, `buyAmountInput_`, `buy___` | body MutationObserver + 1 s URL heartbeat | bazaar | Hashed |
| C8 | js_snippets.dart:576-787 `jailJS` | A8 / A10 | `.users-list > li`: `.level`, `.time`, `.user.name`, `.buy/.bye/.bust` | 300 ms checker | jailview.php | n/a |
| C9 | js_snippets.dart:804-870 `bountiesJS` | A9 | `.bounties-list > li:not(.clear)`: `.level`, `.user-red-status/.user-blue-status` | 300 ms checker | bounties.php | n/a |
| C10 | js_snippets.dart:876-1010 `ocNNB` (WF:5982) | `_assessOCnnb` on onUpdateVisitedHistory **and** every onProgressChanged >75 | jQuery: crimes table rows, `a[href*='profiles.php?XID=']`, `li.stat`/`li.act` | 100 ms interval. Yata/TS fetch in Dart. | factions.php?step=your…tab=crimes, not OCv2, NNB source default yata | n/a |
| C11 | js_snippets.dart:1098-1145 `ageToWordsOnProfile` | `_assessGeneral` on profiles.php (twice) | `div.box-name`, `ul.box-value` | 100 ms interval | Profiles | n/a |
| C12 | js_snippets.dart:1147-1200 `hospitalTimerJS` | Attack page after API status | `[class*="defender___"] [class*="title___"]` | 1 s interval + body observer | Attack and target in hospital | Hashed |
| C13 | remote_snippets.dart:296-330 `cityShopsPurchaseHookJS` | `_assessGeneral` on shops.php | XHR hook `shops.php step=buyShopItem` → D3 | XHR wrapper | shops.php + autoPause pref (default false) + Firestore flag | n/a |
| C14 | remote_snippets.dart:~335-575 `cityShopsBuy100JS` | `_assessGeneral` on shops/bigalgunshop | `#user-money`, `.item-desc .price/.stock`, `ul.item` | body observer | buyMax pref default true | n/a |
| C15 | remote_snippets.dart:~600-975 `buyMaxAbroadJS` | A3 abroad | `#user-money`, `[class*="itemsHeader___"]`, `li > div[class*="row___"]`, `tabletColC___`, `.messageContent___LhCmx`, `cell___`, `inlineStock___` | body observer | Abroad, pref default true | **Fully hashed `messageContent___LhCmx`** |
| C16 | remote_snippets `travelRemovePlaneJS` (WF:2462-2467) | **Every onProgressChanged tick** (getUrl each tick) | Plane element | RT per tick | removeAirplane default false | n/a |
| C17 | js_handlers.dart:60-146 `handler_tornChatCacheTrim` | Document-start, www.torn.com | **Enumerates all localStorage keys + values** (`getItem` each) → D4/D5 | O(localStorage size) per page | **Every torn page** | n/a |
| C18 | js_bank_vault.dart:4-144 `bankVaultScript` | Document-start (NativeChat.compiled) | `location.hash` `tab=controls&giveMoneyTo`. Then `input.input-money`, `[class*="form"] p span[class*="nowrap"]` balance, `[class*="ctaButton"]`, `[role=radiogroup]`. | hashchange listener. 30 s MutationObservers only on the give-money hash. Document `input` listener. | Every torn page (cheap until hash matches). No Dart push. | Hashed partials |
| C19 | js_quick_items.dart:217-375 (`installTempInterceptor`, `startTempDomCacheObserver`) | `runQuickItemJS` for a Temporary item | **Global `window.fetch` and XHR wrappers that clone and parse every later response (JSON.parse, or DOMParser on failure)**. Body MutationObserver for `li[data-item][data-category="Temporary"]`. → D7 | Permanent for the page's lifetime | After using a temporary quick item | n/a |
| C20 | js_quick_items.dart:1584-1760 `quickItemsMassCheckJS` | Quick items widget refresh (10 s cooldown), after picker add, single item use | XHR `item.php step=getSearchList&q=` → DOMParser `li[data-item]` (`data-sort`, `.name`, qty, `data-rowkey`, loaned) → D6 | 1 XHR per item name | Inventory check enabled (default true) | n/a |
| C21 | js_quick_items.dart:1226-1580 `quickItemPickerJS` | User | Item rows: id, name, category, qty, bonuses `i.damage/accuracy/defence`, armory id, `data-rowkey` → D8 | Observer adds buttons | item.php, user | n/a |
| C22 | js_snippets.dart:1764-1790 `changeLoadOutJS` | Quick-item loadout tap | XHR response text → D9 | n/a | Loadout use | n/a |
| C23 | ChatEngine.pageLoadJS / pageResumeJS (WF:1838, 832) | Every torn onLoadStop / resume | **Opaque** (private `lib/config/chat_engine.dart`, an empty stub in the public build) | ? | RC `browser_torn_page_refresh_allowed` default true | Must be inspected in the private build |
| C24 | js_snippets.dart:789-800 `miniProfiles()` | **Never called**. Calls `handlerMiniProfiles`, which is not registered. | n/a | n/a | Dead code | Removable |

## D. JS → Dart handlers

### D-i. PDA-injected JS pushing page data (replaceable)
| id | handler | file:line | source | payload | consumer |
|---|---|---|---|---|---|
| D1 | `PDA_chainWeb` | chain_web.dart:253, chain_mini_window.dart:355 | C1 | {current,max,timeout,cooldown,active,store,attack,ts} / {none} | ChainStatusController.applyWebChain |
| D2 | `PDA_chatProfileIcon` | chat_profile_icon.dart:66 | doc-start listener on Torn's `chat.openChannel` CustomEvent | userId | NativeChat DM window (returns bool) |
| D3 | `PDA_cityShopPurchase` | webview_handlers.dart:60 | C13 | {success,text,itemId,shopId,amount} | CityShopDailyLimit |
| D4 | `PDA_localStorageMeasured` | webview_handlers.dart:551 | C17 | total, chatBytes, top-3 keys | webViewProvider.recordLocalStorageMeasurement |
| D5 | `PDA_tornChatCacheTrimmed` | webview_handlers.dart:523 | C17 | total, freed, limit, reason | provider + analytics |
| D6 | `quickItemMassUpdate` | webview_handlers.dart:870 | C20 | {originalName,foundName,qty,rowKey,loaned} | QuickItemsProvider |
| D7 | `updateQuickItemInstanceId` | quick_items_widget.dart:531 | C19 | itemId, equipId | QuickItemsProvider |
| D8 | `quickItemPicker` / `quickItemPickerCleanup` | webview_handlers.dart:787, quick_items_widget.dart:518 | C21 | item scan data | QuickItemsProvider |
| D9 | `loadoutChangeHandler` | webview_handlers.dart:372 | C22 | XHR responseText (regex `"equippedSet":N`) | Toast |
| D10 | `tornPDAExitFullScreen` | webview_handlers.dart:715 | C4 | 'exit' | UI mode |

### D-ii. Torn site code / userscript API calling PDA (public contract, keep)
`isTornPDA`, `webThemeChange` (only Torn's own JS calls it), `scheduleNotification`/`cancelNotification`/`getNotification`, `setAlarm`, `setTimer`, `getPlatform`, `copyToClipboard`, `reloadPage`, `showToast`, `launchIntent`, `shareFile`, `PDA_getTabState` (pull), `PDA_httpGet/Post/Put/Delete/Patch`, `PDA_evaluateJavascript`, `PDA_storage`, `PDA_gmStorageQuota` (webview_handlers.dart:37-735). Outbound contract: `onChangeTornMode` CustomEvent (WF:7346), `chat.r(id)` (trades_widget.dart:1203), `__tornpda.tab.state` push (WF:6258).

## E. URL / title / history / native state used to infer page state

| id | file:line | trigger | reads | consumer | cost | gating |
|---|---|---|---|---|---|---|
| E1 | WF:1782 | **onProgressChanged, every tick >10** | getUrl | `_currentUrl`, `_reportUrlVisit` | RT per tick | Every page |
| E2 | WF:2462-2467 | Every progress tick | getUrl == travel | Remove plane | RT per tick | removeAirplane (default false) |
| E3 | WF:2041-2054 onUpdateVisitedHistory | SPA/hash nav | uri | `_reportUrlVisit`, `_assessOCnnb` | n/a | Every page |
| E4 | WF:2056-2210 onLoadResource | **Every resource** (`useOnLoadResource: true`, WF:639, plugin PerformanceObserver in all frames) | URL contains trade.php / properties.php / jailview.php / bounties.php / `factions.php` (xmlhttprequest) | A5, A7, A8, A9, faction armoury quick items (getUrl, `tab=armoury`) | 1 bridge message per resource | **Every page** |
| E5 | WF:3807-3999 `_assessSectionsWithWidgets` / `_resetSectionsWithWidgets` + *Triggered flags (WF:332-344) | progress >75 | URL `contains` plus h4 title (`_getPageTitle` WF:4031) as the section gate: 'items','crimes','gym','city','trade','properties' | All section widgets | See A10 | Every page (cheap unless a flag flips) |
| E6 | WF:4043 | If there is no h4: `_getPageTitle(showTitle)` | getTitle (split ' \|') | Tab title | RT | onLoadStop |
| E7 | WF:4004-4026 `_assessBackButtonBehavior` | `_assessGeneral` (twice per nav) | getCopyBackForwardList: was the previous entry trade.php? | Back button pops context | RT | vault/items/factions/companies URLs |
| E8 | WF:4955-5060 `_assessProfileAttack` | A10 | URL `XID=`, `&user2ID=` regex | ProfileAttackCheckWidget, hospital timer | API | extraPlayerInformation (default true) |
| E9 | WF:5319-5357 | onLoadStart gym.php / hunting | URL | Energy/chain warning (API) | API | warnAbout* default true |
| E10 | WF:2628-2652 | onLongPressHitTestResult | `requestFocusNodeHref()` | Long-press card | RT | User |
| E11 | WF:2000-2007 | onLoadStop | Cookie PHPSESSID (CookieManager) | Prefs session cookie | RT | restoreSessionCookie (default false) |
| E12 | WF:2218-2241 | onConsoleMessage | console text | Terminal provider | per message | Every page |
| E13 | WF:3053, 5192, 5211, 5223, 6113, 6151, webview_provider.dart:2214, quick_items_widget.dart:470, 499 | reload / URL dialog / park wake / resume revive / quick-item check / openWebChatDm | getUrl (null means a dead webview) | Various | RT | Event-driven |
| E14 | chat_link_window.dart:115, 258 | Separate chat link webview | getUrl / onUpdateVisitedHistory (bazaar fill) | Chat | RT | Chat only |
| E15 | webview_full_awh.dart:112-162 | n/a | **No reads** (only copyToClipboard handler) | n/a | n/a | n/a |

## F. Outside the main browser
- chain_mini_window.dart:328-370: its own InAppWebView on the bars page. Injects C1 at onLoadStop, then D1.
- webview_simple_dialog.dart: A19.
- chat_link_info.dart:296 `ChatLinkInfo.page`: html.parse of HTTP-fetched external pages (og: meta). **Not WebView.** Out of scope.
- TradesProvider and VaultWidget do more Dart-side DOM/regex parsing of the elements passed from A6/A7.
