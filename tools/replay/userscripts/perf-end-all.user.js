// ==UserScript==
// @name         PDA Perf Test End All
// @namespace    torn-pda-perf
// @version      1.0.0
// @description  Replay test script. Runs at document end and records when it starts.
// @match        https://www.torn.com/*
// @run-at       document-end
// @grant        none
// ==/UserScript==

// Writes window.__pdaPerfUs.endAll (ms from the navigation start). The page probe adds it to its record.
// - start: the script runs. links: a small DOM read, as most scripts do.
// - callAt and answerAt: a PDA_httpGet call after the page load.
(function () {
  const now = () => Math.round(performance.now());
  const r = ((window.__pdaPerfUs = window.__pdaPerfUs || {}).endAll = { start: now() });
  r.links = document.querySelectorAll("a").length;
  if (typeof window.PDA_httpGet === "function") {
    r.callAt = now();
    window.PDA_httpGet("https://pda-replay.invalid/echo.json?from=end").then(
      () => (r.answerAt = now()),
      () => (r.answerAt = -1),
    );
  }
})();
