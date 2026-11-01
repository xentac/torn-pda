"""mitmproxy addon that answers PDA from anonymized recordings. Start it with replay.sh.

The addon never forwards a request. A request with no recorded answer gets a
502 with the header `x-pda-replay: miss`, and the miss goes to the miss log.
Live connections to hosts that match `pda_replay_guard` (torn.com by default)
are refused, so that a mistake in the configuration cannot reach Torn.

Matching: method, host, path, the query without the ignored parameters, and the
body. Form bodies are compared without the ignored parameters. The same request
seen several times gets its recorded answers in order. After the last one, it
keeps getting the last one, so that a second visit to a page still works. If no
recording has the same body, the addon uses a recording with the same URL and
logs a "loose" match.

Time: start the device clock at the recording time (emu-clock.sh, and the
addon prints the command at startup). The certificates that mitmproxy makes
are normally valid from two days before now, which is too late for a device
clock in the past. The addon moves their start back `pda_replay_cert_days`.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import re
import time
import urllib.parse

from mitmproxy import certs, ctx, http, io

HEADER = "x-pda-replay"
DEFAULT_IGNORE = "rfcv,_,key,timestamp"


def _utc(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PdaReplay:
    def __init__(self):
        self.urls: dict[tuple, list[http.HTTPFlow]] = {}
        self.exact: dict[tuple, list[http.HTTPFlow]] = {}
        self.cursor: dict[tuple, int] = {}
        self.guard: re.Pattern | None = None
        self.first_ts: float | None = None
        self.stats = {"hit": 0, "loose": 0, "miss": 0, "blocked": 0}

    def load(self, loader):
        loader.add_option("pda_replay", str, "", "Comma-separated anonymized recordings to answer from.")
        loader.add_option("pda_replay_ignore", str, DEFAULT_IGNORE, "Query and form parameters to ignore when matching.")
        loader.add_option("pda_replay_misses", str, "", "Path of the JSON Lines miss log.")
        loader.add_option(
            "pda_replay_guard", str, r"(^|\.)torn\.com$", "Hosts that must never get a live connection (regex)."
        )
        loader.add_option(
            "pda_replay_latency", str, "0", "Delay per answer: 0, a number of milliseconds, or 'recorded'."
        )
        loader.add_option(
            "pda_replay_cert_days", int, 400, "Days before now that generated certificates become valid."
        )

    def configure(self, updated):
        days = ctx.options.pda_replay_cert_days
        # dummy_cert() reads these module values on each call.
        certs.CERT_VALIDITY_OFFSET = datetime.timedelta(days=-days)
        certs.CERT_EXPIRY = datetime.timedelta(days=days + 199)
        g = ctx.options.pda_replay_guard
        self.guard = re.compile(g) if g else None
        if "pda_replay" in updated or "pda_replay_ignore" in updated:
            self._load(ctx.options.pda_replay)

    def running(self):
        # A live connection opened before the request (to copy the server's
        # certificate) would reach the real server. Turn both behaviors off.
        if ctx.options.connection_strategy != "lazy" or ctx.options.upstream_cert:
            ctx.options.update(connection_strategy="lazy", upstream_cert=False)
        if self.first_ts:
            logging.warning("pda-replay: set the device clock first: tools/replay/emu-clock.sh %s", _utc(self.first_ts))

    # Loading and matching -----------------------------------------------------

    def _ignore(self) -> set[str]:
        return {p for p in ctx.options.pda_replay_ignore.split(",") if p}

    def _url_key(self, r: http.Request) -> tuple:
        ignore = self._ignore()
        q = sorted((k, v) for k, v in r.query.items(multi=True) if k not in ignore)
        return (r.method, r.pretty_host, r.path.split("?", 1)[0], tuple(q))

    def _body_key(self, r: http.Request) -> str:
        if not r.raw_content:
            return ""
        if r.urlencoded_form:
            ignore = self._ignore()
            return repr(sorted((k, v) for k, v in r.urlencoded_form.items(multi=True) if k not in ignore))
        return hashlib.sha256(r.get_content(strict=False) or b"").hexdigest()

    def _load(self, paths: str):
        self.urls.clear()
        self.exact.clear()
        self.cursor.clear()
        self.first_ts = None
        n = 0
        for path in [p.strip() for p in paths.split(",") if p.strip()]:
            with open(path, "rb") as f:
                for fl in io.FlowReader(f).stream():
                    if not isinstance(fl, http.HTTPFlow) or fl.response is None:
                        continue
                    uk = self._url_key(fl.request)
                    self.urls.setdefault(uk, []).append(fl)
                    self.exact.setdefault((uk, self._body_key(fl.request)), []).append(fl)
                    ts = fl.request.timestamp_start
                    self.first_ts = ts if self.first_ts is None else min(self.first_ts, ts)
                    n += 1
        if paths:
            logging.info("pda-replay: loaded %d answers for %d URLs", n, len(self.urls))

    def _next(self, cursor_key, lst) -> http.HTTPFlow | None:
        if not lst:
            return None
        i = self.cursor.get(cursor_key, 0)
        self.cursor[cursor_key] = i + 1
        return lst[min(i, len(lst) - 1)]

    def find(self, r: http.Request) -> tuple[str, http.HTTPFlow | None]:
        uk = self._url_key(r)
        ek = (uk, self._body_key(r))
        rec = self._next(("exact", ek), self.exact.get(ek))
        if rec:
            return "hit", rec
        rec = self._next(("url", uk), self.urls.get(uk))
        if rec:
            return "loose", rec
        return "miss", None

    # Hooks --------------------------------------------------------------------

    def server_connect(self, data):
        host = data.server.address[0] if data.server.address else ""
        if self.guard and self.guard.search(host):
            self.stats["blocked"] += 1
            data.server.error = f"pda-replay: live connection to {host} refused"
            logging.error("pda-replay: refused a live connection to %s", host)

    async def request(self, flow: http.HTTPFlow):
        r = flow.request
        if r.headers.get("upgrade", "").lower() == "websocket":
            self._answer_miss(flow, "websocket")
            return
        kind, rec = self.find(r)
        if rec is None:
            self._answer_miss(flow, "miss")
            return
        self.stats[kind] += 1
        if kind == "loose":
            self._log(flow, "loose")
        delay = self._delay(rec)
        if delay > 0:
            await asyncio.sleep(delay)
        resp = rec.response.copy()
        resp.headers[HEADER] = kind
        resp.timestamp_start = time.time()
        resp.timestamp_end = resp.timestamp_start
        flow.response = resp

    def _delay(self, rec: http.HTTPFlow) -> float:
        opt = ctx.options.pda_replay_latency
        if opt == "recorded":
            start, end = rec.request.timestamp_start, rec.response.timestamp_end
            return max(0.0, min((end or start) - start, 10.0))
        try:
            return float(opt) / 1000
        except ValueError:
            return 0.0

    def _answer_miss(self, flow: http.HTTPFlow, kind: str):
        self.stats["miss"] += 1
        self._log(flow, kind)
        flow.response = http.Response.make(
            502, f"pda-replay: no recording for {flow.request.method} {flow.request.pretty_url}\n", {HEADER: kind}
        )

    def _log(self, flow: http.HTTPFlow, kind: str):
        path = ctx.options.pda_replay_misses
        url = flow.request.pretty_url
        # The app may still send a real key. Keep it out of the log.
        url = re.sub(r"([?&]key=)[^&]+", r"\1REDACTED", url)
        entry = {"t": _utc(time.time()), "kind": kind, "method": flow.request.method, "url": url}
        logging.info("pda-replay: %s %s %s", kind, flow.request.method, url)
        if path:
            with open(path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def done(self):
        logging.info("pda-replay: %s", json.dumps(self.stats))


addons = [PdaReplay()]
