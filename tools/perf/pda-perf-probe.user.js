// ==UserScript==
// @name         PDA Perf Probe
// @namespace    torn-pda-perf
// @version      0.1.0
// @description  Records page-load, interaction and main-thread metrics on torn.com. Runs unchanged in Torn PDA and in Tampermonkey/Violentmonkey so the two can be compared.
// @match        https://www.torn.com/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

// How to read the output
// - A small badge appears bottom-left after each page load. Tap it to open the report.
// - The report has "Copy last", "Copy all" and "Clear" buttons. Results are kept in
//   localStorage (key "pdaPerfProbe.v1", last 200 page loads) so runs survive navigation.
// - Every record is also printed to the console with the prefix [PDA-PERF].
//
// What is measured (all times in ms, relative to the navigation start of the document)
// - nav: Navigation Timing L2 (ttfb, domInteractive, dcl, load).
// - paint: first-paint / first-contentful-paint and the last largest-contentful-paint.
// - probeStart: when this script began to run. In Tampermonkey this is true document-start.
//   In PDA it shows how early the WebView injection really happens.
// - res: resource count, bytes transferred, and how many came from the HTTP cache.
//   A cache ratio near 0 on repeat visits means the cache is disabled.
// - longTasks: count and total duration of main-thread tasks over 50 ms (Chromium only).
// - frames: rAF gaps over 50 ms during the first 10 s and during scrolls (all engines).
// - interactions: Event Timing entries (pointer/key) with duration >= 16 ms. Max and p75.
// - bridge: calls to window.flutter_inappwebview.callHandler, by handler name, with
//   round-trip times (PDA only).
// - hooks: MutationObservers, setInterval timers and their callback time, split into
//   "page" (stack contains a page-origin URL) and "injected" (everything else).
//   Set HOOKS = false to remove this instrumentation if you suspect its own overhead.
(function () {
  "use strict";
  if (window.__pdaPerfProbe) return;
  const HOOKS = true;
  const STORE_KEY = "pdaPerfProbe.v1";
  const MAX_RECORDS = 200;
  const t0 = performance.now();

  const isPDA = () => typeof window.flutter_inappwebview !== "undefined" || /TornPDA|com\.manuito/i.test(navigator.userAgent);

  const rec = {
    v: 1,
    url: location.href,
    path: location.pathname + location.search.replace(/([?&](rfcv|_)=)[^&]*/g, "$1x"),
    ts: Date.now(),
    ua: navigator.userAgent,
    env: null,
    probeStart: Math.round(t0),
    nav: {},
    paint: {},
    res: {},
    longTasks: { count: 0, total: 0, max: 0 },
    frames: { gaps50: 0, gaps100: 0, maxGap: 0, scrollFrames: 0, scrollGaps50: 0 },
    interactions: { count: 0, max: 0, p75: 0, slow: [] },
    bridge: { calls: 0, byName: {}, pendingAtReport: 0 },
    hooks: { moPage: 0, moInjected: 0, moCbMsPage: 0, moCbMsInjected: 0, moCbCount: 0, ivPage: 0, ivInjected: 0, ivCbMsPage: 0, ivCbMsInjected: 0 },
    spaNavs: 0,
  };
  window.__pdaPerfProbe = rec;

  // ---------- origin attribution (cheap heuristic) ----------
  // A stack frame with a URL on the page origin (a torn.com script file or an inline script of
  // the document) means the page created the hook. Code from evaluateJavascript, WKUserScript
  // or a Tampermonkey sandbox shows up without a page-origin URL.
  const fromPage = () => {
    const s = new Error().stack || "";
    const lines = s.split("\n").slice(3, 9).join("\n");
    return lines.indexOf(location.origin + "/") !== -1;
  };

  if (HOOKS) {
    const NativeMO = window.MutationObserver;
    if (NativeMO) {
      window.MutationObserver = function (cb) {
        const page = fromPage();
        page ? rec.hooks.moPage++ : rec.hooks.moInjected++;
        const wrapped = function () {
          const s = performance.now();
          try {
            return cb.apply(this, arguments);
          } finally {
            const d = performance.now() - s;
            rec.hooks.moCbCount++;
            page ? (rec.hooks.moCbMsPage += d) : (rec.hooks.moCbMsInjected += d);
          }
        };
        return new NativeMO(wrapped);
      };
      window.MutationObserver.prototype = NativeMO.prototype;
    }
    const nativeSI = window.setInterval;
    window.setInterval = function (fn, ms) {
      const page = fromPage();
      page ? rec.hooks.ivPage++ : rec.hooks.ivInjected++;
      if (typeof fn !== "function") return nativeSI.apply(window, arguments);
      const args = Array.prototype.slice.call(arguments, 2);
      return nativeSI.call(
        window,
        function () {
          const s = performance.now();
          try {
            return fn.apply(this, args);
          } finally {
            const d = performance.now() - s;
            page ? (rec.hooks.ivCbMsPage += d) : (rec.hooks.ivCbMsInjected += d);
          }
        },
        ms
      );
    };
  }

  // ---------- PDA bridge wrapping ----------
  // The PDA bridge object can appear after document-start, so poll briefly for it.
  let bridgeWrapped = false;
  const wrapBridge = () => {
    const b = window.flutter_inappwebview;
    if (!b || bridgeWrapped || typeof b.callHandler !== "function") return;
    bridgeWrapped = true;
    rec.env = "pda";
    const orig = b.callHandler.bind(b);
    b.callHandler = function (name) {
      rec.bridge.calls++;
      const e = (rec.bridge.byName[name] = rec.bridge.byName[name] || { n: 0, totalMs: 0, maxMs: 0 });
      e.n++;
      const s = performance.now();
      rec.bridge.pendingAtReport++;
      const p = orig.apply(null, arguments);
      const done = () => {
        rec.bridge.pendingAtReport--;
        const d = performance.now() - s;
        e.totalMs += d;
        if (d > e.maxMs) e.maxMs = d;
      };
      if (p && typeof p.then === "function") p.then(done, done);
      else done();
      return p;
    };
  };
  wrapBridge();
  let bridgePolls = 0;
  setTimeout(function poll() {
    wrapBridge();
    if (!bridgeWrapped && ++bridgePolls < 100) setTimeout(poll, 20);
  }, 0);

  // ---------- performance observers ----------
  const observe = (type, fn) => {
    try {
      new PerformanceObserver((l) => l.getEntries().forEach(fn)).observe({ type, buffered: true });
    } catch (_) {
      /* type unsupported in this engine */
    }
  };
  observe("paint", (e) => (rec.paint[e.name === "first-paint" ? "fp" : "fcp"] = Math.round(e.startTime)));
  observe("largest-contentful-paint", (e) => (rec.paint.lcp = Math.round(e.startTime)));
  observe("longtask", (e) => {
    rec.longTasks.count++;
    rec.longTasks.total += e.duration;
    if (e.duration > rec.longTasks.max) rec.longTasks.max = e.duration;
  });
  const durations = [];
  try {
    new PerformanceObserver((l) =>
      l.getEntries().forEach((e) => {
        if (!/pointer|click|key|touch/.test(e.name)) return;
        durations.push(e.duration);
        rec.interactions.count++;
        if (e.duration > rec.interactions.max) rec.interactions.max = e.duration;
        if (e.duration >= 200 && rec.interactions.slow.length < 10) {
          rec.interactions.slow.push({ type: e.name, dur: Math.round(e.duration), at: Math.round(e.startTime), procStart: Math.round(e.processingStart - e.startTime), procMs: Math.round(e.processingEnd - e.processingStart) });
        }
      })
    ).observe({ type: "event", buffered: true, durationThreshold: 16 });
  } catch (_) {
    /* Event Timing unsupported */
  }

  // ---------- rAF frame-gap sampler (works in every engine) ----------
  let last = performance.now();
  let scrolling = -1e9;
  addEventListener("scroll", () => (scrolling = performance.now()), { passive: true, capture: true });
  const frame = (now) => {
    const gap = now - last;
    last = now;
    const inScroll = now - scrolling < 300;
    if (inScroll) {
      rec.frames.scrollFrames++;
      if (gap > 50) rec.frames.scrollGaps50++;
    }
    if (now < 10000 || inScroll) {
      if (gap > 50) rec.frames.gaps50++;
      if (gap > 100) rec.frames.gaps100++;
      if (gap > rec.frames.maxGap) rec.frames.maxGap = Math.round(gap);
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  // ---------- SPA navigations (Torn uses hash routes on several pages) ----------
  addEventListener("hashchange", () => rec.spaNavs++);
  ["pushState", "replaceState"].forEach((m) => {
    const o = history[m];
    history[m] = function () {
      rec.spaNavs++;
      return o.apply(this, arguments);
    };
  });

  // ---------- report ----------
  const round = (o) => {
    for (const k in o) if (typeof o[k] === "number") o[k] = Math.round(o[k] * 10) / 10;
    return o;
  };
  const finalize = () => {
    const n = performance.getEntriesByType("navigation")[0];
    if (n) {
      rec.nav = round({
        type: n.type,
        ttfb: n.responseStart,
        respEnd: n.responseEnd,
        domInteractive: n.domInteractive,
        dcl: n.domContentLoadedEventEnd,
        load: n.loadEventEnd,
        docBytes: n.transferSize,
      });
    }
    const res = performance.getEntriesByType("resource");
    let bytes = 0;
    let cached = 0;
    let lastEnd = 0;
    const byType = {};
    res.forEach((r) => {
      bytes += r.transferSize || 0;
      if (r.transferSize === 0 && r.decodedBodySize > 0) cached++;
      if (r.responseEnd > lastEnd) lastEnd = r.responseEnd;
      byType[r.initiatorType] = (byType[r.initiatorType] || 0) + 1;
    });
    rec.res = { count: res.length, kb: Math.round(bytes / 1024), cached, cacheRatio: res.length ? Math.round((cached / res.length) * 100) / 100 : null, lastEnd: Math.round(lastEnd), byType };
    durations.sort((a, b) => a - b);
    rec.interactions.p75 = durations.length ? Math.round(durations[Math.floor(durations.length * 0.75)]) : 0;
    rec.longTasks.total = Math.round(rec.longTasks.total);
    rec.longTasks.max = Math.round(rec.longTasks.max);
    round(rec.hooks);
    Object.values(rec.bridge.byName).forEach(round);
    rec.env = rec.env || (isPDA() ? "pda" : typeof GM_info !== "undefined" ? "tm" : "browser");
    rec.domNodes = document.getElementsByTagName("*").length;
    rec.styleTags = document.querySelectorAll("style").length;
    rec.inlineScripts = document.querySelectorAll("script:not([src])").length;
    return rec;
  };

  const load = () => {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
    } catch (_) {
      return [];
    }
  };
  const save = (all) => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(all.slice(-MAX_RECORDS)));
    } catch (_) {
      /* storage full or blocked */
    }
  };

  // Report 10 s after load so late LCP, long tasks and the first interactions are captured.
  // A second, final write happens on pagehide so interaction data from the whole visit is kept.
  let reportedIdx = -1;
  const report = (final) => {
    const r = JSON.parse(JSON.stringify(finalize()));
    r.final = !!final;
    const all = load();
    if (reportedIdx >= 0 && all[reportedIdx] && all[reportedIdx].ts === r.ts) all[reportedIdx] = r;
    else {
      all.push(r);
      reportedIdx = Math.min(all.length, MAX_RECORDS) - 1;
    }
    save(all);
    if (!final) console.log("[PDA-PERF] " + JSON.stringify(r));
    return r;
  };

  addEventListener("load", () => setTimeout(() => (report(false), badge()), 10000));
  addEventListener("pagehide", () => report(true));

  // ---------- UI ----------
  const badge = () => {
    if (!document.body) return;
    const r = rec;
    const b = document.createElement("div");
    b.textContent = `${r.env} dcl ${r.nav.dcl | 0} load ${r.nav.load | 0} start ${r.probeStart} lt ${r.longTasks.count}/${r.longTasks.total}`;
    b.style.cssText = "position:fixed;left:4px;bottom:4px;z-index:2147483647;font:11px monospace;background:rgba(0,0,0,.75);color:#0f0;padding:3px 6px;border-radius:4px";
    b.onclick = panel;
    document.body.appendChild(b);
  };
  const copy = (txt) => {
    if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
      // PDA exposes a clipboard handler. navigator.clipboard is often blocked in WebViews.
      window.flutter_inappwebview.callHandler("copyToClipboard", txt);
    } else if (navigator.clipboard) navigator.clipboard.writeText(txt);
  };
  const panel = () => {
    const all = load();
    const p = document.createElement("div");
    p.style.cssText = "position:fixed;inset:10% 4px;z-index:2147483647;background:#111;color:#eee;font:11px monospace;overflow:auto;padding:8px;border:1px solid #0f0";
    const rows = all
      .slice(-30)
      .reverse()
      .map((r) => `${r.env.padEnd(4)} ${String(r.nav.dcl | 0).padStart(5)} ${String(r.nav.load | 0).padStart(5)} ${String(r.probeStart).padStart(5)} ${String(r.longTasks.total).padStart(5)} ${String(r.interactions.max | 0).padStart(4)} ${r.path.slice(0, 40)}`)
      .join("\n");
    p.innerHTML = "<div></div><pre></pre>";
    p.querySelector("pre").textContent = "env    dcl  load start ltMs inpMx path\n" + rows;
    const bar = p.querySelector("div");
    [
      ["Copy last", () => copy(JSON.stringify(all[all.length - 1]))],
      ["Copy all", () => copy(JSON.stringify(all))],
      ["Clear", () => (save([]), p.remove())],
      ["Close", () => p.remove()],
    ].forEach(([t, f]) => {
      const btn = document.createElement("button");
      btn.textContent = t;
      btn.style.cssText = "margin:0 6px 6px 0;font:12px sans-serif";
      btn.onclick = f;
      bar.appendChild(btn);
    });
    document.body.appendChild(p);
  };
})();
