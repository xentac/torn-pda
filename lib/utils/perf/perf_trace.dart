// Performance instrumentation for the browser. Compiled out unless the app is built with
// --dart-define=PDA_PERF=true (all entry points check the const [PerfTrace.enabled] first,
// so release builds without the flag carry no cost).
//
// What it records, per tab and per document (from onLoadStart to the next onLoadStart):
// - how many times each InAppWebView callback fired, its synchronous Dart time, and the wall
//   time until its Future completed (wall time includes awaited platform calls and delays)
// - named counters (setState on WebViewFull, getHtml calls, provider notifies, etc.)
// - main-isolate event-loop lag: a 16 ms timer measures how late it fires. This catches
//   work between frames (channel handlers, HTML parsing, storage) that frame timings miss
// - Flutter frame timings (UI build and raster)
//
// Callbacks that fire before onLoadStart for the same navigation (shouldOverrideUrlLoading)
// go to a per-tab pending record, which the next navStart adopts.
//
// Lag and frame numbers are process-wide. They are written only to the record of the tab
// that started the most recent navigation, so do not add them up across tabs.
//
// A summary record is logged with the prefix [PDA-PERF-DART] at onLoadStop + 10 s. Records of the
// page probe (tools/perf/pda-perf-probe.user.js, injected first in these builds) come from the
// console and are logged with the prefix [PDA-PERF-PROBE]. See [PerfTrace.emit] for the format.
//
// Platform-channel traffic is not counted here. Build with the flag in profile mode and
// Flutter's own `debugProfilePlatformChannels` is turned on as well (see [PerfTrace.install]),
// which logs per-channel and per-method message counts and bytes.
import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

class PerfTrace {
  static const bool enabled = bool.fromEnvironment('PDA_PERF');

  static final Map<String, _NavTrace> _byTab = {};
  static final Map<String, _NavTrace> _pending = {};
  static final Map<String, _NavTrace> _late = {};
  static final _FrameStats _frames = _FrameStats();
  static final _LagStats _lag = _LagStats();
  static String? _lastTab;
  static bool _installed = false;

  /// Call once at startup (main.dart). No-op without the flag.
  static void install() {
    if (!enabled || _installed) return;
    _installed = true;
    if (!kReleaseMode) debugProfilePlatformChannels = true;
    SchedulerBinding.instance.addTimingsCallback(_frames.add);
    _lag.start();
  }

  static int _emitted = 0;
  // Characters per line. Up to 3 bytes each in UTF-8, under the limit of about 1024 bytes.
  static const int _chunk = 300;

  /// Writes a record to the developer log (DevTools) and to logcat. `developer.log` does not reach
  /// logcat, and Flutter cuts logcat lines at about 1 KB, so the logcat copy is split into lines of
  /// the form `[PREFIX] <id> <part>/<parts> <text>`. Join the parts of one id in order.
  static void emit(String prefix, String text) {
    if (!enabled) return;
    developer.log('[$prefix] $text', name: 'PERF');
    final id = ++_emitted;
    final chunks = <String>[];
    for (var start = 0; start < text.length;) {
      var end = start + _chunk < text.length ? start + _chunk : text.length;
      // Do not split a surrogate pair
      if (end < text.length && (text.codeUnitAt(end - 1) & 0xFC00) == 0xD800) end--;
      chunks.add(text.substring(start, end));
      start = end;
    }
    for (var i = 0; i < chunks.length; i++) {
      debugPrintSynchronously('[$prefix] $id ${i + 1}/${chunks.length} ${chunks[i]}');
    }
  }

  /// A new document began loading in [tab]. Flushes the previous record if not yet reported.
  static void navStart(String tab, String url) {
    if (!enabled) return;
    if (url.startsWith('about:')) return;
    final prev = _byTab[tab];
    if (prev != null && !prev.reported) _report(tab, prev, reason: 'next-nav');
    final t = _NavTrace(url, _frames.snapshot(), _lag.snapshot());
    final pending = _pending.remove(tab);
    if (pending != null) t.adopt(pending);
    _byTab[tab] = t;
    _lastTab = tab;
  }

  /// The page finished loading. Reports 10 s later so late callbacks are included.
  static void navStop(String tab) {
    if (!enabled) return;
    final t = _byTab[tab];
    if (t == null || t.stopAt != null) return;
    t.stopAt = t.sw.elapsedMilliseconds;
    Timer(const Duration(seconds: 10), () {
      if (identical(_byTab[tab], t) && !t.reported) _report(tab, t, reason: 'stop+10s');
    });
  }

  static void count(String tab, String name, [int n = 1]) {
    if (!enabled) return;
    final t = _byTab[tab];
    if (t == null || t.reported) return;
    t.counts[name] = (t.counts[name] ?? 0) + n;
  }

  /// Counter that is not tied to a tab (providers, controllers, handlers without a tab id).
  /// Goes to the tab that started the most recent navigation.
  static void countGlobal(String name, [int n = 1]) {
    if (!enabled || _lastTab == null) return;
    count(_lastTab!, name, n);
  }

  /// Counts and forwards a getHtml call. Use in place of `controller.getHtml()`.
  /// [site] names the caller, counted as `getHtml.<site>` next to the total.
  static Future<String?> getHtml(String? tab, InAppWebViewController? c, [String site = '?']) {
    if (enabled) {
      tab == null ? countGlobal('getHtml') : count(tab, 'getHtml');
      tab == null ? countGlobal('getHtml.$site') : count(tab, 'getHtml.$site');
    }
    return c?.getHtml() ?? Future.value(null);
  }

  /// Wraps a callback body. Measures synchronous time and time until the Future completes.
  /// Set [preNav] for callbacks that fire before onLoadStart of the navigation they belong to.
  static Future<T> cb<T>(String tab, String name, Future<T> Function() body, {bool preNav = false}) {
    if (!enabled) return body();
    final sw = Stopwatch()..start();
    final Future<T> f = body();
    final syncUs = sw.elapsedMicroseconds;
    return f.whenComplete(() => _record(tab, name, preNav, syncUs, sw.elapsedMicroseconds));
  }

  /// Synchronous variant of [cb].
  static T cbSync<T>(String tab, String name, T Function() body) {
    if (!enabled) return body();
    final sw = Stopwatch()..start();
    try {
      return body();
    } finally {
      final us = sw.elapsedMicroseconds;
      _record(tab, name, false, us, us);
    }
  }

  static void _record(String tab, String name, bool preNav, int syncUs, int totalUs) {
    _NavTrace? t;
    if (preNav) {
      t = _pending.putIfAbsent(tab, () => _NavTrace('(pending)', const [], const []));
    } else {
      t = _byTab[tab];
      if (t == null) return;
      if (t.reported) {
        // Arrived after the 10 s report (polling pages do this all the time). Counted, and written
        // as `latePrev` with the next record of the tab. One log line per callback would add main
        // thread work to the measurement.
        t = _late.putIfAbsent(tab, () => _NavTrace('(late)', const [], const []));
      }
    }
    final s = t.cbs.putIfAbsent(name, () => _CbStat());
    s.n++;
    s.syncUs += syncUs;
    s.totalUs += totalUs;
    if (totalUs > s.maxUs) s.maxUs = totalUs;
  }

  static void _report(String tab, _NavTrace t, {required String reason}) {
    t.reported = true;
    final late = _late.remove(tab);
    final processWide = identical(_byTab[_lastTab], t);
    final m = <String, dynamic>{
      'tab': tab,
      'url': t.url,
      'reason': reason,
      'stopMs': t.stopAt,
      'cb': _cbMap(t),
      'counts': t.counts,
      if (late != null) 'latePrev': _cbMap(late),
      if (processWide) 'frames': _frames.since(t.frames0),
      if (processWide) 'lag': _lag.since(t.lag0),
    };
    emit('PDA-PERF-DART', jsonEncode(m));
  }
}

class _CbStat {
  int n = 0;
  int syncUs = 0;
  int totalUs = 0;
  int maxUs = 0;
}

Map<String, dynamic> _cbMap(_NavTrace t) => {
      for (final e in t.cbs.entries)
        e.key: {
          'n': e.value.n,
          'syncMs': (e.value.syncUs / 1000).toStringAsFixed(1),
          'wallMs': (e.value.totalUs / 1000).toStringAsFixed(1),
          'maxWallMs': (e.value.maxUs / 1000).toStringAsFixed(1),
        },
    };

class _NavTrace {
  _NavTrace(this.url, this.frames0, this.lag0);
  final String url;
  final List<int> frames0;
  final List<int> lag0;
  final Stopwatch sw = Stopwatch()..start();
  final Map<String, _CbStat> cbs = {};
  final Map<String, int> counts = {};
  int? stopAt;
  bool reported = false;

  void adopt(_NavTrace other) {
    for (final e in other.cbs.entries) {
      cbs['${e.key}(preNav)'] = e.value;
    }
    other.counts.forEach((k, v) => counts[k] = (counts[k] ?? 0) + v);
  }
}

class _LagStats {
  // Cumulative counters, read as differences per navigation.
  static const _periodUs = 16000;
  int samples = 0;
  int over16 = 0;
  int over50 = 0;
  int over100 = 0;
  int lagUsTotal = 0;
  int lagUsMax = 0;

  void start() {
    final sw = Stopwatch()..start();
    var last = 0;
    Timer.periodic(const Duration(microseconds: _periodUs), (_) {
      final now = sw.elapsedMicroseconds;
      final lag = now - last - _periodUs;
      last = now;
      samples++;
      if (lag <= 0) return;
      lagUsTotal += lag;
      if (lag > lagUsMax) lagUsMax = lag;
      if (lag > 16000) over16++;
      if (lag > 50000) over50++;
      if (lag > 100000) over100++;
    });
  }

  List<int> snapshot() => [samples, over16, over50, over100, lagUsTotal];

  Map<String, dynamic> since(List<int> s) => {
    'samples': samples - s[0],
    'over16': over16 - s[1],
    'over50': over50 - s[2],
    'over100': over100 - s[3],
    'totalMs': ((lagUsTotal - s[4]) / 1000).toStringAsFixed(1),
    'maxMsEver': (lagUsMax / 1000).toStringAsFixed(1),
  };
}

class _FrameStats {
  // Cumulative counters. A navigation keeps a snapshot and reports the difference.
  int frames = 0;
  int uiOver16 = 0;
  int rasterOver16 = 0;
  int uiUsTotal = 0;
  int rasterUsTotal = 0;
  int uiUsMax = 0;
  int rasterUsMax = 0;

  void add(List<FrameTiming> timings) {
    for (final t in timings) {
      final ui = t.buildDuration.inMicroseconds;
      final raster = t.rasterDuration.inMicroseconds;
      frames++;
      uiUsTotal += ui;
      rasterUsTotal += raster;
      if (ui > 16000) uiOver16++;
      if (raster > 16000) rasterOver16++;
      if (ui > uiUsMax) uiUsMax = ui;
      if (raster > rasterUsMax) rasterUsMax = raster;
    }
  }

  List<int> snapshot() => [frames, uiOver16, rasterOver16, uiUsTotal, rasterUsTotal];

  Map<String, dynamic> since(List<int> s) {
    final n = frames - s[0];
    return {
      'n': n,
      'uiOver16': uiOver16 - s[1],
      'rasterOver16': rasterOver16 - s[2],
      'uiAvgMs': n == 0 ? 0 : ((uiUsTotal - s[3]) / n / 1000).toStringAsFixed(2),
      'rasterAvgMs': n == 0 ? 0 : ((rasterUsTotal - s[4]) / n / 1000).toStringAsFixed(2),
      // Max values are process-wide since start, not per navigation.
      'uiMaxMsEver': (uiUsMax / 1000).toStringAsFixed(1),
      'rasterMaxMsEver': (rasterUsMax / 1000).toStringAsFixed(1),
    };
  }
}
