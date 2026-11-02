// ==UserScript==
// @name         PDA Perf Test End Profile
// @namespace    torn-pda-perf
// @version      1.0.0
// @description  Replay test script. Runs at document end and records when it starts.
// @match        https://www.torn.com/profiles.php*
// @run-at       document-end
// @grant        none
// ==/UserScript==

// Writes window.__pdaPerfUs.endProfile (ms from the navigation start). The page probe adds it to its record.
// - start: the script runs. links: a small DOM read, as most scripts do.
(function () {
  const now = () => Math.round(performance.now());
  const r = ((window.__pdaPerfUs = window.__pdaPerfUs || {}).endProfile = { start: now() });
  r.links = document.querySelectorAll("a").length;
})();
