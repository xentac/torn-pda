// ==UserScript==
// @name         PDA Perf Test Start Page
// @namespace    torn-pda-perf
// @version      1.0.0
// @description  Replay test script. Runs at document start on page.php only and records when it starts.
// @match        https://www.torn.com/page.php*
// @run-at       document-start
// @grant        none
// ==/UserScript==

// Writes window.__pdaPerfUs.startPage (ms from the navigation start). The page probe adds it to its record.
// A record of this script on another page means that a stale registration ran.
(function () {
  const r = ((window.__pdaPerfUs = window.__pdaPerfUs || {}).startPage = { start: Math.round(performance.now()) });
  r.href = location.pathname;
})();
