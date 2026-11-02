"""Anonymize a PDA capture for replay.

    python3 pda_anonymize.py --identity identity.json --map idmap.json raw.mitm anon.mitm

The tool reads the raw recording twice. The first pass collects the values to
replace: API keys (the `key` parameter and `Authorization: ApiKey ...`), cookie
values, and the IDs and names of players and factions that appear in Torn's
usual places (`XID=`, `profiles.php`, `"player_id"`, `Name [123]`, member
lists). The second pass rewrites URLs, headers, text bodies and websocket
messages.

The map file keeps real-to-fake pairs between runs, so that one real ID always
becomes the same fake ID in every recording. The map and the identity file hold
real data. Keep them outside the repository, like the raw recordings.

At the end, the tool searches the output for every original secret. If it finds
one, it prints where, writes nothing, and exits with status 1.

identity.json (all fields optional except player_id and player_name):

    {
      "player_id": 1234567,
      "player_name": "MyName",
      "faction_id": 12345,
      "faction_name": "My Faction",
      "emails": ["me@example.org"],
      "strings": {"My real street address": "1 Example Street"}
    }

Known limits: names of other players in free text (chat, forum posts, event
messages without a profile link) stay as they are. Binary bodies are not
rewritten, only searched.
"""

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import urllib.parse

from mitmproxy import http, io

TEXT_TYPES = ("text/", "json", "javascript", "xml", "x-www-form-urlencoded", "multipart/form-data")
# Cookie values shorter than this are flags like "1" or "en", not secrets.
MIN_COOKIE_LEN = 8
# Other players' IDs are replaced outside their usual places only when they are
# this long, so that small numbers in the page do not change by accident.
MIN_FREE_ID_LEN = 5
# Numbers shorter than this after "ID=" and similar are page or item numbers more
# often than player IDs, and a same-length fake has too few choices. They stay as they are.
MIN_MAPPED_ID_LEN = 4

ID_CONTEXTS = [
    r"XID=",
    r"[?&;]ID=",
    r"[?&;]userID=",
    r"[?&;]user2ID=",
    r"[?&;]target=",
    r"/user/",
    r"/faction/",
    r'"(?:player_id|user_id|userID|userId|faction_id|factionID|factionId|attacker_id|defender_id|target_id)"\s*:\s*"?',
    r"data-(?:id|user|player|uid)=\"",
    r'name="(?:userID|user2ID|XID|targetID|playerID)"\r\n\r\n',
]
FACTION_CONTEXTS = [r"factions\.php\?step=profile&(?:amp;)?ID=", r"/faction/", r'"(?:faction_id|factionID|factionId)"\s*:\s*"?']
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
# Form and query fields whose values are credentials, whatever their format.
# Torn's crimes page, for example, posts a 32-character "apiKey" that is not the API key.
SECRET_FIELD_RE = re.compile(r"(?i)^(api_?key|key|token|access_?token|secret|password|passwd|auth)$")
SECRET_JSON_RE = re.compile(r'"(?i:api_?key|access_?token|secret|password)"\s*:\s*"([^"\\]{8,200})"')
ID_FIELDS = {"userID", "user2ID", "XID", "targetID", "playerID", "user_id", "target_id"}
API_KEY_RE = re.compile(r"(?:[?&]key=|ApiKey\s+|\"key\"\s*:\s*\")([A-Za-z0-9]{16})(?![A-Za-z0-9])")
NAME_BEFORE_ID_RE = re.compile(r"([A-Za-z0-9_-]{1,20}) \[(\d{1,8})\]")
NAME_IN_PROFILE_LINK_RE = re.compile(r"(profiles\.php\?XID=(\d{1,8})[^>]*>)([A-Za-z0-9_-]{1,20})(<)")
NAME_KEYS = ("name", "playername", "player_name", "username")
PLAYER_ID_KEYS = ("player_id", "user_id", "userID", "playerID", "userId")
# Keys that player objects have and item or faction objects do not.
PLAYER_HINT_KEYS = ("last_action", "level")
B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class IdMap:
    """Real-to-fake pairs, stable across runs through a secret salt."""

    def __init__(self, path: str):
        self.path = path
        data = {}
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        self.salt = bytes.fromhex(data.get("salt") or secrets.token_hex(32))
        self.tables: dict[str, dict[str, str]] = {
            k: dict(data.get(k, {})) for k in ("ids", "factions", "names", "keys", "cookies", "emails", "ips")
        }
        # Every real and fake value, so that a new fake never equals an existing value.
        self._used: set[str] = set()
        for t in self.tables.values():
            self._used.update(t.keys())
            self._used.update(t.values())

    def save(self):
        data = {"salt": self.salt.hex(), **self.tables}
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def _digest(self, kind: str, real: str) -> bytes:
        return hmac.new(self.salt, f"{kind}:{real}".encode(), hashlib.sha256).digest()

    def _get(self, table: str, real: str, make) -> str:
        t = self.tables[table]
        if real not in t:
            self._used.add(real)
            for n in range(10_000):
                fake = make(self._digest(table, f"{real}#{n}"))
                if fake not in self._used:
                    break
            else:
                raise RuntimeError(f"no free fake value for a {len(real)}-character {table} entry")
            t[real] = fake
            self._used.add(fake)
        return t[real]

    def number(self, table: str, real: str, force: bool = False) -> str:
        """A fake number with the same digit count, so that layout and parsers are unchanged.

        Numbers shorter than MIN_MAPPED_ID_LEN stay as they are, unless force is set.
        """
        digits = len(real)
        if digits < MIN_MAPPED_ID_LEN and not force and real not in self.tables[table]:
            return real

        def make(d: bytes) -> str:
            v = int.from_bytes(d, "big")
            if digits == 1:
                return str(1 + v % 9)
            lo = 10 ** (digits - 1)
            return str(lo + v % (9 * lo))

        return self._get(table, real, make)

    def token(self, table: str, real: str, prefix: str = "") -> str:
        """A fake value with the same length, made from the same kind of characters."""

        def make(d: bytes) -> str:
            v = int.from_bytes(d * 4, "big")
            out = []
            for ch in real[len(prefix) :]:
                if ch.isdigit():
                    alphabet = "0123456789"
                elif ch.isalpha():
                    alphabet = B62[10:]
                else:
                    out.append(ch)
                    continue
                out.append(alphabet[v % len(alphabet)])
                v //= len(alphabet)
            return prefix + "".join(out)

        return self._get(table, real, make)

    def name(self, real: str) -> str:
        return self._get("names", real, lambda d: "Player" + str(int.from_bytes(d[:4], "big") % 10**6))

    def email(self, real: str) -> str:
        return self._get("emails", real, lambda d: f"user{int.from_bytes(d[:3], 'big')}@example.com")

    def ip(self, real: str) -> str:
        # Documentation ranges (RFC 5737), never routed.
        nets = ("192.0.2.", "198.51.100.", "203.0.113.")
        return self._get("ips", real, lambda d: nets[d[0] % 3] + str(1 + d[1] % 254))


def _text_of(msg: http.Message) -> str | None:
    ctype = msg.headers.get("content-type", "").lower()
    if ctype and not any(t in ctype for t in TEXT_TYPES):
        return None
    if not msg.raw_content:
        return None
    try:
        return msg.get_text(strict=True)
    except ValueError:
        return None


def _messages(flow: http.HTTPFlow):
    yield flow.request
    if flow.response:
        yield flow.response


def _all_text(flow: http.HTTPFlow):
    """Every piece of text in a flow that can hold personal data."""
    yield flow.request.url
    for msg in _messages(flow):
        for k, v in msg.headers.items(multi=True):
            yield f"{k}: {v}"
        t = _text_of(msg)
        if t is not None:
            yield t
    if flow.websocket:
        for m in flow.websocket.messages:
            if m.is_text:
                yield m.text


def _private_ip(s: str) -> bool:
    try:
        a = ipaddress.ip_address(s)
    except ValueError:
        return True  # Not an address, for example a version number like 300.1.2.3.
    return not a.is_global


class Anonymizer:
    def __init__(self, identity: dict, idmap: IdMap):
        self.m = idmap
        self.own_id = str(identity["player_id"])
        self.own_name = identity["player_name"]
        self.faction_id = str(identity["faction_id"]) if identity.get("faction_id") else None
        self.faction_name = identity.get("faction_name")
        self.literals: dict[str, str] = dict(identity.get("strings", {}))
        for e in identity.get("emails", []):
            self.literals[e] = self.m.email(e)
        self.m.number("ids", self.own_id, force=True)
        self.m.tables["names"][self.own_name] = self.m.tables["names"].get(self.own_name, "PdaTester")
        self.m._used.update((self.own_name, self.m.tables["names"][self.own_name]))
        if self.faction_id:
            self.m.number("factions", self.faction_id, force=True)
        if self.faction_name:
            self.literals[self.faction_name] = "Example Faction"
        self._compiled = None

    # Pass 1 -------------------------------------------------------------------

    def collect(self, flow: http.HTTPFlow):
        for msg in _messages(flow):
            for v in msg.headers.get_all("cookie"):
                for part in v.split(";"):
                    if "=" in part:
                        self._cookie(part.split("=", 1)[1].strip())
            for v in msg.headers.get_all("set-cookie"):
                first = v.split(";", 1)[0]
                if "=" in first:
                    self._cookie(first.split("=", 1)[1].strip())
        r = flow.request
        fields = list(r.query.items(multi=True))
        if r.urlencoded_form:
            fields += list(r.urlencoded_form.items(multi=True))
        if r.multipart_form:
            fields += [(k.decode(errors="replace"), v.decode(errors="replace")) for k, v in r.multipart_form.items(multi=True)]
        for name, value in fields:
            if SECRET_FIELD_RE.match(name) and len(value) >= MIN_COOKIE_LEN:
                self.m.token("keys", value)
            elif name in ID_FIELDS and value.isdigit():
                self.m.number("ids", value)
        for text in _all_text(flow):
            for k in API_KEY_RE.findall(text):
                self.m.token("keys", k)
            for k in SECRET_JSON_RE.findall(text):
                self.m.token("keys", k)
            for e in EMAIL_RE.findall(text):
                if not e.lower().endswith(("@example.com", ".png", ".jpg", ".gif", ".svg", ".webp")):
                    self.m.email(e)
            for ctx_re in ID_CONTEXTS:
                for real in re.findall(f"(?:{ctx_re})(\\d{{1,8}})", text):
                    self.m.number("ids", real)
            for ctx_re in FACTION_CONTEXTS:
                for real in re.findall(f"(?:{ctx_re})(\\d{{1,8}})", text):
                    self.m.number("factions", real)
            for name, pid in NAME_BEFORE_ID_RE.findall(text):
                self.m.number("ids", pid)
                self._other_name(name)
            for _pre, pid, name, _post in NAME_IN_PROFILE_LINK_RE.findall(text):
                self.m.number("ids", pid)
                self._other_name(name)
        for msg in _messages(flow):
            if "json" in msg.headers.get("content-type", "").lower():
                t = _text_of(msg)
                try:
                    data = json.loads(t) if t else None
                except ValueError:
                    data = None
                self._json_players(data, None)

    def _json_players(self, obj, key):
        """Collect names from objects that look like players, such as faction member lists."""
        if isinstance(obj, list):
            for v in obj:
                self._json_players(v, None)
            return
        if not isinstance(obj, dict):
            return
        pid = next((str(obj[k]) for k in PLAYER_ID_KEYS if isinstance(obj.get(k), (int, str))), None)
        if pid is None and key is not None and str(key).isdigit() and any(k in obj for k in PLAYER_HINT_KEYS):
            pid = str(key)
        name = next((obj[k] for k in NAME_KEYS if isinstance(obj.get(k), str)), None)
        if pid and pid.isdigit():
            self.m.number("ids", pid)
            if name:
                self._other_name(name)
        for k, v in obj.items():
            self._json_players(v, k)

    def _cookie(self, value: str):
        value = urllib.parse.unquote(value)
        if len(value) < MIN_COOKIE_LEN:
            return
        # Digit-only values are counters or timestamps, and replacing them everywhere would move times.
        if value.isdigit() and len(value) < 16:
            return
        self.m.token("cookies", value)

    def _other_name(self, name: str):
        if name != self.own_name and len(name) >= 3:
            self.m.name(name)

    # Pass 2 -------------------------------------------------------------------

    def _build(self):
        lit = dict(self.literals)
        lit.update(self.m.tables["keys"])
        lit.update(self.m.tables["cookies"])
        lit.update(self.m.tables["emails"])
        lit[self.own_name] = self.m.tables["names"][self.own_name]
        ordered = sorted(lit, key=len, reverse=True)
        lit_re = re.compile("|".join(re.escape(x) for x in ordered)) if ordered else None

        other = {k: v for k, v in self.m.tables["names"].items() if k != self.own_name}
        # One generic pattern and a dict lookup. An alternation of thousands of names
        # would be tried at every position of every body.
        names_re = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{3,20})(?=\s*\[\d|</a>|\")") if other else None
        id_ctx = "|".join(f"(?:{c})" for c in ID_CONTEXTS)
        fac_ctx = "|".join(f"(?:{c})" for c in FACTION_CONTEXTS)
        free = {k: v for k, v in self.m.tables["ids"].items() if len(k) >= MIN_FREE_ID_LEN}
        free.update({k: v for k, v in self.m.tables["factions"].items() if len(k) >= MIN_FREE_ID_LEN})
        free[self.own_id] = self.m.tables["ids"][self.own_id]
        if self.faction_id:
            free[self.faction_id] = self.m.tables["factions"][self.faction_id]
        self._free = free
        self._compiled = (
            lit_re,
            lit,
            names_re,
            other,
            re.compile(f"({fac_ctx})(\\d{{1,8}})(?!\\d)"),
            re.compile(f"({id_ctx})(\\d{{1,8}})(?!\\d)"),
            re.compile(r"(?<![\dA-Za-z])(\d{1,8})(?![\dA-Za-z])"),
        )

    def rewrite(self, text: str) -> str:
        if self._compiled is None:
            self._build()
        lit_re, lit, names_re, other, fac_re, id_re, free_re = self._compiled
        ids, facs = self.m.tables["ids"], self.m.tables["factions"]
        if lit_re:
            text = lit_re.sub(lambda mo: lit[mo.group(0)], text)
        if names_re:
            text = names_re.sub(lambda mo: other.get(mo.group(1), mo.group(1)), text)
        text = fac_re.sub(lambda mo: mo.group(1) + facs.get(mo.group(2), mo.group(2)), text)
        text = id_re.sub(lambda mo: mo.group(1) + ids.get(mo.group(2), mo.group(2)), text)
        free = self._free
        text = free_re.sub(lambda mo: free.get(mo.group(1), mo.group(1)), text)
        text = IPV4_RE.sub(lambda mo: mo.group(0) if _private_ip(mo.group(0)) else self.m.ip(mo.group(0)), text)
        return text

    def apply(self, flow: http.HTTPFlow):
        r = flow.request
        r.url = self._rewrite_url(r.url)
        for msg in _messages(flow):
            for k in list(msg.headers.keys()):
                vals = msg.headers.get_all(k)
                new = [self._rewrite_header(v) for v in vals]
                if new != vals:
                    msg.headers.set_all(k, new)
            t = _text_of(msg)
            if t is not None:
                nt = self.rewrite(t)
                if nt != t:
                    msg.text = nt
        if flow.websocket:
            for m in flow.websocket.messages:
                if m.is_text:
                    m.text = self.rewrite(m.text)
        flow.comment = ""
        flow.metadata.clear()

    def _rewrite_url(self, url: str) -> str:
        # Values in URLs can be percent-encoded, so rewrite the decoded form too.
        out = self.rewrite(url)
        dec = urllib.parse.unquote(out)
        if dec != out and self.rewrite(dec) != dec:
            parts = urllib.parse.urlsplit(out)
            q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            q = [(k, self.rewrite(v)) for k, v in q]
            out = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))
        return out

    def _rewrite_header(self, v: str) -> str:
        out = self.rewrite(v)
        dec = urllib.parse.unquote(out)
        if dec != out:
            # Cookie values are often percent-encoded. Replace the encoded secrets as well.
            for real, fake in self.m.tables["cookies"].items():
                enc = urllib.parse.quote(real, safe="")
                if enc in out:
                    out = out.replace(enc, urllib.parse.quote(fake, safe=""))
        return out

    # Leak check ---------------------------------------------------------------

    def secrets(self) -> list[str]:
        out = [self.own_name, *self.literals, *self.m.tables["keys"], *self.m.tables["cookies"], *self.m.tables["emails"]]
        out = [s for s in out if s]
        return sorted(set(out), key=len, reverse=True)

    def leaks(self, flow: http.HTTPFlow, secret_list: list[str]) -> list[str]:
        found = []
        id_re = re.compile(r"(?<![\dA-Za-z])" + re.escape(self.own_id) + r"(?![\dA-Za-z])")
        blobs = list(_all_text(flow))
        for msg in _messages(flow):
            if _text_of(msg) is None and msg.raw_content:
                try:
                    content = msg.get_content(strict=True) or b""
                except ValueError:
                    found.append("a body that cannot be decoded, so it was not checked")
                    content = msg.raw_content
                blobs.append(content.decode("latin-1"))
        for b in blobs:
            for s in secret_list:
                if s in b or urllib.parse.quote(s, safe="") in b:
                    found.append(_redact(s))
            if id_re.search(b):
                found.append("own player_id")
        return sorted(set(found))


def _redact(s: str) -> str:
    return s[:2] + "*" * max(0, len(s) - 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--identity", required=True, help="Private JSON with your player ID, name and other values.")
    ap.add_argument("--map", required=True, help="Private JSON of real-to-fake pairs. Created if missing.")
    ap.add_argument("input", help="Raw recording (.mitm).")
    ap.add_argument("output", help="Anonymized recording to write.")
    a = ap.parse_args(argv)

    with open(a.identity) as f:
        identity = json.load(f)
    idmap = IdMap(a.map)
    anon = Anonymizer(identity, idmap)

    with open(a.input, "rb") as f:
        flows = [fl for fl in io.FlowReader(f).stream() if isinstance(fl, http.HTTPFlow)]
    for fl in flows:
        anon.collect(fl)
    for fl in flows:
        anon.apply(fl)

    secret_list = anon.secrets()
    problems = []
    for i, fl in enumerate(flows):
        for leak in anon.leaks(fl, secret_list):
            problems.append(f"flow {i} {fl.request.method} {anon.rewrite(fl.request.pretty_url)[:120]}: {leak}")
    idmap.save()
    if problems:
        print("Leak check failed. Nothing was written. Add the values to identity.json or fix the rules:", file=sys.stderr)
        for p in problems[:50]:
            print("  " + p, file=sys.stderr)
        if len(problems) > 50:
            print(f"  ... and {len(problems) - 50} more", file=sys.stderr)
        return 1

    tmp = a.output + ".tmp"
    with open(tmp, "wb") as f:
        w = io.FlowWriter(f)
        for fl in flows:
            w.add(fl)
    os.replace(tmp, a.output)
    own_keys = sorted(set(idmap.tables["keys"].values()))
    print(f"Wrote {len(flows)} flows to {a.output}.")
    print(f"Fake player ID {idmap.tables['ids'][anon.own_id]}, name {idmap.tables['names'][anon.own_name]}.")
    if own_keys:
        print("Fake API keys to enter in PDA for replay: " + ", ".join(own_keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
