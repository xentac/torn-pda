// ==UserScript==
// @name         PDA Perf Test Churn
// @namespace    torn-pda-perf
// @version      1.0.0
// @description  Replay test script. Changes a page area many times each second and times the changes.
// @match        https://www.torn.com/profiles.php*
// @run-at       document-end
// @grant        none
// ==/UserScript==

// Writes window.__pdaPerfUs.churn. The page probe adds it to its record 10 s after load.
// - Each visit takes the next rate from RATES (a counter in localStorage), so a flow that opens
//   the page 3 times tests each rate once.
// - It waits for PDA's chain reader (window.__pdaChainReader), then runs 6 blocks of 1.2 s in the
//   order none, global, narrow, narrow, global, none (visits 1 to 3), or global, narrow, none,
//   none, narrow, global (visits 4 to 6). blocks has the total time of each block. "global" adds an empty observer on the whole
//   document, as the chain reader has. "narrow" adds one on the chain bar only. "none" adds none.
// - A tick (every 50 ms) does rate/20 changes in a box in the main content: even ones set the
//   text of a timer node (characterData), odd ones add a message and remove the oldest (childList).
// - loop: the time of the changes. total: from the start of the changes until a promise queued
//   after them runs, so it includes the delivery of the records to all observers.
(function () {
  const RATES = [20, 200, 2000];
  const ORDERS = [
    ["none", "global", "narrow", "narrow", "global", "none"],
    ["global", "narrow", "none", "none", "narrow", "global"],
  ];
  const BLOCK_MS = 1200;
  const TICK_MS = 50;
  const KEY = "pdaPerfChurn.visit";
  const now = () => performance.now();
  let visit = 0;
  try {
    visit = +localStorage.getItem(KEY) || 0;
    localStorage.setItem(KEY, String(visit + 1));
  } catch (_) {}
  const rate = RATES[visit % RATES.length];
  const MODES = ORDERS[Math.floor(visit / RATES.length) % ORDERS.length];
  const r = ((window.__pdaPerfUs = window.__pdaPerfUs || {}).churn = { visit, rate, order: MODES.join(","), start: null, end: null, reader: false, blocks: [] });

  const box = document.createElement("div");
  box.id = "pda-perf-churn";
  box.style.cssText = "font:10px monospace;height:120px;overflow:hidden";
  const timers = [];
  const row = document.createElement("div");
  for (let i = 0; i < 20; i++) {
    const s = document.createElement("span");
    s.textContent = "00:00 ";
    timers.push(s.firstChild);
    row.appendChild(s);
  }
  const chat = document.createElement("div");
  box.append(row, chat);
  for (let i = 0; i < 20; i++) chat.appendChild(message(i));
  (document.querySelector(".content-wrapper") || document.body).prepend(box);

  function message(n) {
    const m = document.createElement("div");
    const who = document.createElement("b");
    who.textContent = "Player" + (n % 7) + ": ";
    m.append(who, document.createTextNode("message " + n));
    return m;
  }

  const OPTS = { subtree: true, childList: true, characterData: true };
  function observerFor(mode) {
    if (mode === "none") return null;
    const target = mode === "global" ? document.documentElement : document.querySelector('a[class*="chainBar___"]') || document.createElement("div");
    const o = new MutationObserver(() => {});
    o.observe(target, OPTS);
    return o;
  }

  const stats = {};
  let n = 0;
  function tick(s) {
    const per = Math.max(1, Math.round(rate / (1000 / TICK_MS)));
    const t0 = now();
    for (let i = 0; i < per; i++, n++) {
      if (i % 2 === 0) {
        timers[n % timers.length].data = String(n % 60).padStart(2, "0") + ":" + String(n % 100).padStart(2, "0") + " ";
      } else {
        chat.firstChild.remove();
        chat.appendChild(message(n));
      }
    }
    const t1 = now();
    Promise.resolve().then(() => {
      s.loop.push(t1 - t0);
      s.total.push(now() - t0);
    });
  }

  function runBlock(b) {
    if (b >= MODES.length) return finish();
    const mode = MODES[b];
    const s = (stats[mode] = stats[mode] || { loop: [], total: [] });
    const o = observerFor(mode);
    const from = s.total.length;
    const end = now() + BLOCK_MS;
    const step = () => {
      if (now() >= end) {
        if (o) o.disconnect();
        // The last tick's promise ran before this timer
        r.blocks.push([mode, r1(sum(s.total.slice(from)))]);
        return setTimeout(() => runBlock(b + 1), TICK_MS);
      }
      tick(s);
      setTimeout(step, TICK_MS);
    };
    step();
  }

  function sum(a) {
    return a.reduce((x, y) => x + y, 0);
  }
  function pct(a, p) {
    const b = a.slice().sort((x, y) => x - y);
    return b.length ? b[Math.min(b.length - 1, Math.floor(b.length * p))] : 0;
  }
  const r1 = (x) => Math.round(x * 100) / 100;
  function finish() {
    r.end = Math.round(now());
    for (const mode in stats) {
      const s = stats[mode];
      r[mode] = { ticks: s.loop.length, loopSum: r1(sum(s.loop)), loopMed: r1(pct(s.loop, 0.5)), loopP95: r1(pct(s.loop, 0.95)), totalSum: r1(sum(s.total)), totalMed: r1(pct(s.total, 0.5)), totalP95: r1(pct(s.total, 0.95)) };
    }
  }

  // The chain reader comes from onLoadStop, as this script does. Wait up to 3 s for it.
  const waitStart = now();
  (function wait() {
    if (window.__pdaChainReader || now() - waitStart > 3000) {
      r.reader = !!window.__pdaChainReader;
      r.start = Math.round(now());
      return runBlock(0);
    }
    setTimeout(wait, 50);
  })();
})();
