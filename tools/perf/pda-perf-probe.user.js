// ==UserScript==
// @name         PDA Perf Probe
// @namespace    torn-pda-perf
// @version      0.3.0
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
// - tap: time from the last tap or click on the previous page to this document's navigation
//   start (tapToNavStart), first byte (tapToTtfb) and DOMContentLoaded (tapToDcl). This includes
//   any delay before the request starts, for example a native app that holds the navigation.
// - bridge: calls to window.flutter_inappwebview.callHandler, by handler name, with
//   round-trip times and the time of the first call (PDA only). The plugin's own
//   onLoadResource messages show up here as byName.onLoadResource. byName.X.firstAt is the
//   time of the first call of handler X.
// - us: what the replay's test userscripts (tools/replay/userscripts/) wrote into
//   window.__pdaPerfUs, for example when their first PDA_httpGet answer came.
// - segments: for each hash or history route change, long tasks, bridge calls and frame gaps
//   in the 3 s after the change (single-page parts of Torn).
// - hooks: MutationObservers, setInterval timers and their callback time, split into
//   "page" (stack contains a page-origin URL) and "injected" (everything else).
//   Set HOOKS = false to remove this instrumentation if you suspect its own overhead.
//   In PDA, code registered before this script runs first, so observers it creates at document
//   start are not counted. A PDA_PERF build injects this script itself, before the PDA handler
//   bundle, so only the plugin's own scripts run earlier there. Then do not also install it as a
//   userscript.
(function () {
  "use strict";
  if (window.__pdaPerfProbe) return;
  // PDA_PERF builds inject this script on every page, without the @match header.
  if (location.hostname !== "www.torn.com") return;
  const HOOKS = true;
  const STORE_KEY = "pdaPerfProbe.v1";
  const MAX_RECORDS = 50;
  const TAP_KEY = "pdaPerfProbe.lastTap";
  const t0 = performance.now();

  const isPDA = () => typeof window.flutter_inappwebview !== "undefined" || /TornPDA|com\.manuito/i.test(navigator.userAgent);

  const rec = {
    v: 1,
    url: location.href,
    path: location.pathname + location.search.replace(/([?&](rfcv|_)=)[^&]*/g, "$1x"),
    ts: Date.now(),
    timeOrigin: Math.round(performance.timeOrigin),
    ua: navigator.userAgent.replace(/^Mozilla\/5\.0 /, "").slice(0, 160),
    env: null,
    probeStart: Math.round(t0),
    nav: {},
    paint: {},
    res: {},
    longTasks: { count: 0, total: 0, max: 0 },
    frames: { gaps50: 0, gaps100: 0, maxGap: 0, scrollFrames: 0, scrollGaps50: 0 },
    interactions: { count: 0, max: 0, p75: 0, slow: [] },
    tap: null,
    bridge: { calls: 0, firstAt: null, byName: {}, pendingAtReport: 0 },
    segments: [],
    hooks: { moPage: 0, moInjected: 0, moCbMsPage: 0, moCbMsInjected: 0, moCbCount: 0, ivPage: 0, ivInjected: 0, ivCbMsPage: 0, ivCbMsInjected: 0 },
    spaNavs: 0,
  };
  window.__pdaPerfProbe = rec;

  // ---------- origin attribution (cheap heuristic) ----------
  // A stack frame with a URL on the page origin (a torn.com script file or an inline script of
  // the document) means the page created the hook. Code from evaluateJavascript, WKUserScript
  // or a Tampermonkey sandbox shows up without a page-origin URL.
  // The probe's own frames contain "pdaProbe" (named functions below). The first frame after
  // them is the code that created the hook. This works for Chromium and Gecko stack formats.
  const fromPage = function pdaProbeFromPage() {
    const lines = (new Error().stack || "").split("\n").filter((l) => l.trim() && !/^Error/.test(l) && l.indexOf("pdaProbe") === -1);
    return !!lines[0] && lines[0].indexOf(location.origin + "/") !== -1;
  };

  if (HOOKS) {
    const NativeMO = window.MutationObserver;
    if (NativeMO) {
      window.MutationObserver = function pdaProbeMO(cb) {
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
      if (window.WebKitMutationObserver) window.WebKitMutationObserver = window.MutationObserver;
    }
    const nativeSI = window.setInterval;
    window.setInterval = function pdaProbeSI(fn, ms) {
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
      if (rec.bridge.firstAt === null) rec.bridge.firstAt = Math.round(performance.now());
      if (seg) seg.bridge++;
      const e = (rec.bridge.byName[name] = rec.bridge.byName[name] || { n: 0, totalMs: 0, maxMs: 0, firstAt: Math.round(performance.now()) });
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

  // ---------- tap to navigation ----------
  // The previous page stores the time of the last tap. A tap older than 15 s is ignored.
  let seg = null;
  try {
    const last = Number(sessionStorage.getItem(TAP_KEY));
    sessionStorage.removeItem(TAP_KEY);
    if (last && performance.timeOrigin - last < 15000 && performance.timeOrigin >= last) rec.tap = { tapToNavStart: Math.round(performance.timeOrigin - last) };
  } catch (_) {
    /* sessionStorage blocked */
  }
  const storeTap = () => {
    try {
      sessionStorage.setItem(TAP_KEY, String(Date.now()));
    } catch (_) {
      /* sessionStorage blocked */
    }
  };
  addEventListener("pointerdown", storeTap, { capture: true, passive: true });
  addEventListener("click", storeTap, { capture: true, passive: true });

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
    if (seg && e.startTime >= seg.at) (seg.lt++, (seg.ltMs += e.duration));
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
    if (seg && now - seg.at < 3000 && gap > 50) seg.gaps50++;
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
  const spaNav = (kind) => {
    rec.spaNavs++;
    if (rec.segments.length >= 20) return;
    seg = { kind, at: Math.round(performance.now()), path: location.pathname + location.hash.slice(0, 40), lt: 0, ltMs: 0, bridge: 0, gaps50: 0 };
    rec.segments.push(seg);
  };
  addEventListener("hashchange", () => spaNav("hash"));
  ["pushState", "replaceState"].forEach((m) => {
    const o = history[m];
    history[m] = function pdaProbeHistory() {
      const r = o.apply(this, arguments);
      if (m === "pushState") spaNav("push");
      return r;
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
      if (rec.tap) {
        rec.tap.tapToTtfb = Math.round(rec.tap.tapToNavStart + n.responseStart);
        rec.tap.tapToDcl = Math.round(rec.tap.tapToNavStart + n.domContentLoadedEventEnd);
      }
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
    rec.segments.forEach((x) => (x.ltMs = Math.round(x.ltMs)));
    rec.env = rec.env || (isPDA() ? "pda" : typeof GM_info !== "undefined" ? "tm" : "browser");
    if (window.__pdaPerfUs) rec.us = window.__pdaPerfUs;
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
  // If the page is left before the 10 s report, the pagehide write goes to the console instead.
  let reportedIdx = -1;
  let logged = false;
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
    if (!logged) console.log("[PDA-PERF] " + JSON.stringify(r));
    logged = true;
    return r;
  };

  const schedule = () => setTimeout(() => (report(false), badge()), 10000);
  // The probe can be injected after load (for example by a late re-injection). Report anyway.
  if (document.readyState === "complete") schedule();
  else addEventListener("load", schedule);
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
