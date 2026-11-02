"""mitmproxy addon that answers PDA from anonymized recordings. Start it with replay.sh.

The addon never forwards a request. A request with no recorded answer gets a
502 with the header `x-pda-replay: miss`, and the miss goes to the miss log.
Live connections to hosts that match `pda_replay_guard` (torn.com by default)
are refused, so that a mistake in the configuration cannot reach Torn.
The host in BLANK_URL gets a fixed empty page. make-snapshot.sh leaves the
browser on it, so that no Torn page runs when a test starts.

Matching: method, host, path, the query without the ignored parameters, and the
body. Form bodies (URL-encoded and multipart) are compared field by field without
the ignored parameters, so that the random multipart boundary does not count. The same request
seen several times gets its recorded answers in order. After the last one, it
keeps getting the last one, so that a second visit to a page still works. The
replay never goes back in recorded time on one URL: if it already gave a later
answer for the same URL (other body), the request gets that answer, logged as
"state". A poll during a fight must see the fight, not a poll from before it.
A repeated request gets its next recorded answer only when the replay already
gave every answer that came between the two in the recording, on the same page
(host, path and Torn's "sid"). Otherwise it gets the previous answer again,
logged as "hold". So a list that the page polls changes only after the action
that changed it in the capture. If no
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
# PDA opens tornpda:// links as https://. The .invalid host can never be a real site.
BLANK_URL = "https://pda-replay.invalid/blank"
BLANK_PAGE = b"<!doctype html><title>Replay start</title><p>Replay start page. No Torn page is open.</p>"
DEFAULT_IGNORE = "rfcv,_,key,timestamp,t"


def _site(host: str) -> str:
    """The last two labels of a host name, for example torn.com for www.torn.com."""
    return ".".join(host.split(".")[-2:])


def _utc(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PdaReplay:
    def __init__(self):
        self.urls: dict[tuple, list[http.HTTPFlow]] = {}
        self.exact: dict[tuple, list[http.HTTPFlow]] = {}
        self.cursor: dict[tuple, int] = {}
        # The answer with the latest recorded time that the replay gave, per URL key.
        self.latest: dict[tuple, http.HTTPFlow] = {}
        # The recorded flows per page, with their match keys, and the ones given so far.
        self.pages: dict[tuple, list[tuple[float, tuple, str]]] = {}
        self.served: set[str] = set()
        self.guard: re.Pattern | None = None
        self.first_ts: float | None = None
        # Cookies that the recorded browser sent, per site, such as "torn.com".
        self.cookies: dict[str, dict[str, str]] = {}
        self.stats = {"hit": 0, "hold": 0, "loose": 0, "state": 0, "miss": 0, "blocked": 0}

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
            "pda_replay_cookies", bool, True, "Give the client the cookies that the recorded browser sent."
        )
        loader.add_option(
            "pda_replay_log_hits", bool, False, "Also log exact matches in the miss log, to see what a flow did."
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
        # Speculative prefetches (from Torn's speculation-rules header) and real loads
        # of the same URL get different answers. Cloudflare refuses the prefetches
        # with an empty 503, and a page load must not get that answer.
        prefetch = "prefetch" in (r.headers.get("sec-purpose", "") + r.headers.get("purpose", ""))
        return (r.method, r.pretty_host, r.path.split("?", 1)[0], tuple(q), prefetch)

    def _body_key(self, r: http.Request) -> str:
        if not r.raw_content:
            return ""
        form = r.urlencoded_form or r.multipart_form
        if form:
            ignore = self._ignore()
            if isinstance(next(iter(form.keys())), bytes):
                ignore = {k.encode() for k in ignore}
            return repr(sorted((k, v) for k, v in form.items(multi=True) if k not in ignore))
        return hashlib.sha256(r.get_content(strict=False) or b"").hexdigest()

    def _load(self, paths: str):
        self.urls.clear()
        self.exact.clear()
        self.cursor.clear()
        self.latest.clear()
        self.pages.clear()
        self.served.clear()
        self.cookies.clear()
        self.first_ts = None
        n = 0
        for path in [p.strip() for p in paths.split(",") if p.strip()]:
            with open(path, "rb") as f:
                for fl in io.FlowReader(f).stream():
                    if not isinstance(fl, http.HTTPFlow) or fl.response is None:
                        continue
                    # A replay starts with an empty browser cache, so "not modified" is no answer.
                    if fl.response.status_code == 304:
                        continue
                    jar = self.cookies.setdefault(_site(fl.request.pretty_host), {})
                    for name, value in fl.request.cookies.items(multi=True):
                        jar[name] = value
                    uk = self._url_key(fl.request)
                    self.urls.setdefault(uk, []).append(fl)
                    ek = (uk, self._body_key(fl.request))
                    self.exact.setdefault(ek, []).append(fl)
                    self.pages.setdefault(self._page(fl.request), []).append((fl.request.timestamp_start, ek, fl.id))
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

    @staticmethod
    def _page(r: http.Request) -> tuple:
        return (r.pretty_host, r.path.split("?", 1)[0], r.query.get("sid", ""))

    def _previous(self, ek) -> http.HTTPFlow | None:
        lst = self.exact.get(ek)
        i = self.cursor.get(("exact", ek), 0)
        return lst[i - 1] if lst and i > 0 else None

    def _next_exact(self, r: http.Request, ek) -> http.HTTPFlow | None:
        """The next exact answer, or None while the page has not caught up with the recording."""
        lst = self.exact.get(ek)
        if not lst:
            return None
        i = self.cursor.get(("exact", ek), 0)
        if 0 < i < len(lst):
            before = lst[i - 1].request.timestamp_start
            after = lst[i].request.timestamp_start
            for ts, k, fid in self.pages.get(self._page(r), []):
                if k != ek and before < ts < after and fid not in self.served:
                    return None
        return self._next(("exact", ek), lst)

    def find(self, r: http.Request) -> tuple[str, http.HTTPFlow | None]:
        uk = self._url_key(r)
        ek = (uk, self._body_key(r))
        kind = "hit"
        rec = self._next_exact(r, ek)
        if rec is None:
            kind = "hold"
            rec = self._previous(ek)
        if not rec:
            kind = "loose"
            rec = self._next(("url", uk), self.urls.get(uk))
        if not rec:
            return "miss", None
        latest = self.latest.get(uk)
        if latest and latest.request.timestamp_start > rec.request.timestamp_start:
            return "state", latest
        self.latest[uk] = rec
        self.served.add(rec.id)
        return kind, rec

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
        if r.pretty_url == BLANK_URL:
            flow.response = http.Response.make(200, BLANK_PAGE, {"content-type": "text/html", HEADER: "blank"})
            return
        kind, rec = self.find(r)
        if rec is None:
            self._answer_miss(flow, "miss")
            return
        self.stats[kind] += 1
        if kind in ("loose", "state") or ctx.options.pda_replay_log_hits:
            self._log(flow, kind)
        delay = self._delay(rec)
        if delay > 0:
            await asyncio.sleep(delay)
        resp = rec.response.copy()
        resp.headers[HEADER] = kind
        if ctx.options.pda_replay_cookies:
            self._add_missing_cookies(r, resp)
        resp.timestamp_start = time.time()
        resp.timestamp_end = resp.timestamp_start
        flow.response = resp

    def _add_missing_cookies(self, r: http.Request, resp: http.Response):
        """Sets the recorded cookies that the client does not have yet.

        Torn's scripts read the login cookies (uid, rfc_v) to build their requests.
        Without them the requests carry userID=0 and match nothing in the recording.
        The values are the anonymized ones, so they match the anonymized requests.
        """
        site = _site(r.pretty_host)
        have = set(r.cookies.keys())
        for name, value in self.cookies.get(site, {}).items():
            if name not in have:
                resp.headers.add("set-cookie", f"{name}={value}; Domain=.{site}; Path=/; Secure")

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
        form = flow.request.urlencoded_form or flow.request.multipart_form
        if form:
            # Field names, and the value of "step" (Torn's action name). Other values can hold keys.
            fields = [k.decode() if isinstance(k, bytes) else k for k in form.keys()]
            entry["fields"] = fields
            step = form.get("step") or form.get(b"step")
            if step:
                entry["step"] = step.decode() if isinstance(step, bytes) else step
        logging.info("pda-replay: %s %s %s", kind, flow.request.method, url)
        if path:
            with open(path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def done(self):
        logging.info("pda-replay: %s", json.dumps(self.stats))


addons = [PdaReplay()]
