"""mitmproxy addon for capture sessions. Start it with capture.sh, not by hand.

A person plays Torn in a capture build of PDA. This addon only listens. It adds:

- Marks: open https://www.torn.com/pda-mark/<label> in the PDA browser to label
  the moment (for example "trade-open"). The proxy answers it locally with 204,
  so the request never reaches Torn. The mark goes into the manifest with its
  time. Replay and tests use the marks
  to find page states.
- A manifest next to the recording (<recording>.json): start and end time in UTC,
  the mitmproxy version, the CA fingerprint, the marks, and per-host counts of
  saved and unsaved flows. Hosts that were seen but not saved show what the
  save filter left out.

Saving itself is done by mitmproxy (-w and save_stream_filter), see capture.sh.
"""

import datetime
import json
import logging
import os
import re
import urllib.parse

from mitmproxy import ctx, flowfilter, http, version

MARK_HOST = "www.torn.com"
MARK_PREFIX = "/pda-mark/"


def _is_mark(flow: http.HTTPFlow) -> bool:
    return flow.request.pretty_host == MARK_HOST and flow.request.path.startswith(MARK_PREFIX)


def _utc(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).isoformat().replace("+00:00", "Z")


class PdaCapture:
    def __init__(self):
        self.started = datetime.datetime.now(datetime.UTC).timestamp()
        self.marks: list[dict] = []
        self.hosts: dict[str, dict[str, int]] = {}
        self._filter = None

    def load(self, loader):
        loader.add_option("pda_manifest", str, "", "Path of the manifest JSON to write.")

    def configure(self, updated):
        if "save_stream_filter" in updated:
            expr = ctx.options.save_stream_filter
            self._filter = flowfilter.parse(expr) if expr else None

    def request(self, flow: http.HTTPFlow):
        if not _is_mark(flow):
            return
        label = urllib.parse.unquote(flow.request.path[len(MARK_PREFIX) :]) or "mark"
        label = re.sub(r"[^A-Za-z0-9_.-]+", "-", label)[:60]
        self.marks.append({"t": _utc(flow.request.timestamp_start), "label": label})
        logging.info("pda-capture: mark %s", label)
        flow.response = http.Response.make(204)
        self._write()

    def response(self, flow: http.HTTPFlow):
        self._count(flow)

    def error(self, flow: http.HTTPFlow):
        self._count(flow)

    def _count(self, flow: http.HTTPFlow):
        if _is_mark(flow):
            return
        host = flow.request.pretty_host
        saved = self._filter is None or bool(self._filter(flow))
        h = self.hosts.setdefault(host, {"saved": 0, "unsaved": 0})
        h["saved" if saved else "unsaved"] += 1

    def done(self):
        self._write()

    def _ca_fingerprint(self) -> str:
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes

            path = os.path.join(os.path.expanduser(ctx.options.confdir), "mitmproxy-ca-cert.pem")
            with open(path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            return cert.fingerprint(hashes.SHA256()).hex()
        except Exception as e:  # The manifest is still useful without it.
            return f"unknown ({e})"

    def _write(self):
        path = ctx.options.pda_manifest
        if not path:
            return
        data = {
            "started": _utc(self.started),
            "ended": _utc(datetime.datetime.now(datetime.UTC).timestamp()),
            "mitmproxy": version.VERSION,
            "ca_sha256": self._ca_fingerprint(),
            "save_filter": ctx.options.save_stream_filter,
            "marks": self.marks,
            "hosts": dict(sorted(self.hosts.items())),
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)


addons = [PdaCapture()]
