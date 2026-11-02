// ==UserScript==
// @name         PDA Perf Test Start
// @namespace    torn-pda-perf
// @version      1.0.0
// @description  Replay test script. Calls PDA_httpGet at document start and records when the answer comes.
// @match        https://www.torn.com/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

// Writes window.__pdaPerfUs.start. The page probe adds it to its record as "us".
// All times are ms from the navigation start.
// - start: the script runs. apiAt: PDA_httpGet exists. callAt: the call.
// - readyAt: __PDA_platformReadyPromise resolves. answerAt: the answer comes.
(function () {
  const now = () => Math.round(performance.now());
  const r = ((window.__pdaPerfUs = window.__pdaPerfUs || {}).start = { start: now() });
  const call = () => {
    r.apiAt = now();
    if (window.__PDA_platformReadyPromise) window.__PDA_platformReadyPromise.then(() => (r.readyAt = now()));
    r.callAt = now();
    window.PDA_httpGet("https://pda-replay.invalid/echo.json?from=start").then(
      (resp) => {
        r.answerAt = now();
        r.status = resp && resp.status;
      },
      () => {
        r.answerAt = now();
        r.status = -1;
      },
    );
  };
  let polls = 0;
  (function poll() {
    if (typeof window.PDA_httpGet === "function") call();
    else if (++polls < 500) setTimeout(poll, 10);
  })();
})();
