// Performance instrumentation for the browser. Compiled out unless the app is built with
// --dart-define=PDA_PERF=true (all entry points check the const [PerfTrace.enabled] first,
// so release builds without the flag carry no cost).
//
// What it records, per tab and per navigation (from onLoadStart to the next onLoadStart):
// - how many times each InAppWebView callback fired and the Dart time spent inside it
//   (time until the returned Future completes, so awaited platform calls are included)
// - named counters (setState on WebViewFull, notifyListeners on providers, etc.)
// - Flutter frame timings (UI build and raster) while the browser is in the foreground
//
// A summary line is logged with the prefix [PDA-PERF-DART] at onLoadStop + 10 s, and the
// last 100 summaries are kept in memory ([PerfTrace.history]) for the dev tools.
//
// Platform-channel traffic is not counted here. Build with the flag and Flutter's own
// `debugProfilePlatformChannels` is turned on as well (see [PerfTrace.install]), which logs
// per-channel and per-method message counts and bytes.
import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

class PerfTrace {
  static const bool enabled = bool.fromEnvironment('PDA_PERF');

  static final Map<String, _NavTrace> _byTab = {};
  static final List<Map<String, dynamic>> history = [];
  static final _FrameStats _frames = _FrameStats();
  static bool _installed = false;

  /// Call once at startup (main.dart). No-op without the flag.
  static void install() {
    if (!enabled || _installed) return;
    _installed = true;
    if (!kReleaseMode) debugProfilePlatformChannels = true;
    SchedulerBinding.instance.addTimingsCallback(_frames.add);
  }

  /// A new top-level navigation began in [tab]. Flushes the previous one if not yet reported.
  static void navStart(String tab, String url) {
    if (!enabled) return;
    final prev = _byTab[tab];
    if (prev != null && !prev.reported) _report(tab, prev, reason: 'next-nav');
    _byTab[tab] = _NavTrace(url, _frames.snapshot());
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
    if (t == null) return;
    t.counts[name] = (t.counts[name] ?? 0) + n;
  }

  /// Counter that is not tied to a tab (providers, controllers).
  static void countGlobal(String name, [int n = 1]) {
    if (!enabled) return;
    for (final t in _byTab.values) {
      if (!t.reported) t.counts[name] = (t.counts[name] ?? 0) + n;
    }
  }

  /// Wraps a callback body. Measures synchronous time and time until the Future completes.
  static Future<T> cb<T>(String tab, String name, Future<T> Function() body) {
    if (!enabled) return body();
    final t = _byTab[tab];
    final sw = Stopwatch()..start();
    final Future<T> f = body();
    final syncUs = sw.elapsedMicroseconds;
    return f.whenComplete(() {
      if (t == null) return;
      final s = t.cbs.putIfAbsent(name, () => _CbStat());
      s.n++;
      s.syncUs += syncUs;
      final us = sw.elapsedMicroseconds;
      s.totalUs += us;
      if (us > s.maxUs) s.maxUs = us;
    });
  }

  /// Synchronous variant of [cb].
  static T cbSync<T>(String tab, String name, T Function() body) {
    if (!enabled) return body();
    final t = _byTab[tab];
    final sw = Stopwatch()..start();
    try {
      return body();
    } finally {
      if (t != null) {
        final s = t.cbs.putIfAbsent(name, () => _CbStat());
        final us = sw.elapsedMicroseconds;
        s.n++;
        s.syncUs += us;
        s.totalUs += us;
        if (us > s.maxUs) s.maxUs = us;
      }
    }
  }

  static void _report(String tab, _NavTrace t, {required String reason}) {
    t.reported = true;
    final f = _frames.since(t.frames0);
    final m = <String, dynamic>{
      'tab': tab,
      'url': t.url,
      'reason': reason,
      'stopMs': t.stopAt,
      'cb': {
        for (final e in t.cbs.entries)
          e.key: {
            'n': e.value.n,
            'syncMs': (e.value.syncUs / 1000).toStringAsFixed(1),
            'totalMs': (e.value.totalUs / 1000).toStringAsFixed(1),
            'maxMs': (e.value.maxUs / 1000).toStringAsFixed(1),
          },
      },
      'counts': t.counts,
      'frames': f,
    };
    history.add(m);
    if (history.length > 100) history.removeAt(0);
    developer.log('[PDA-PERF-DART] ${jsonEncode(m)}', name: 'PERF');
  }
}

class _CbStat {
  int n = 0;
  int syncUs = 0;
  int totalUs = 0;
  int maxUs = 0;
}

class _NavTrace {
  _NavTrace(this.url, this.frames0);
  final String url;
  final List<int> frames0;
  final Stopwatch sw = Stopwatch()..start();
  final Map<String, _CbStat> cbs = {};
  final Map<String, int> counts = {};
  int? stopAt;
  bool reported = false;
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
