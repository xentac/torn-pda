// ==UserScript==
// @name         PDA Perf Test Back Once
// @namespace    torn-pda-perf
// @version      1.0.0
// @description  Replay test script. Goes back once from the attack page with history.back().
// @match        https://www.torn.com/page.php?sid=attack*
// @run-at       document-end
// @grant        none
// ==/UserScript==

// Android does not tell the app about a history step that the page starts, so the start scripts of
// the attack page stay registered on the page before it. With perf-start-page and perf-start-profile,
// the probe records of the next page show which start scripts ran there.
(function () {
  if (sessionStorage.getItem("pdaPerfBackOnce")) return;
  sessionStorage.setItem("pdaPerfBackOnce", "1");
  setTimeout(() => history.back(), 1500);
})();
