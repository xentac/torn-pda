"""Tests for the capture, anonymize and replay tools. All data here is made up.

    python3 -m pytest tools/replay

Needs Python with mitmproxy and pytest (see README.md).
"""

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mitmproxy import certs, flowfilter, http, io
from mitmproxy.addons import save
from mitmproxy.connection import Server
from mitmproxy.proxy.server_hooks import ServerConnectionHookData
from mitmproxy.test import taddons, tflow

sys.path.insert(0, str(Path(__file__).parent))
import pda_anonymize  # noqa: E402
import pda_capture  # noqa: E402
import pda_replay  # noqa: E402

KEY = "AbCdEfGh12345678"
OWN_ID = "1234567"
OWN_NAME = "RealName"
OTHER_ID = "2345678"
OTHER_NAME = "OtherGuy"
FACTION_ID = "45678"
SESSION = "s3ss10nAbCdEf9876543210"
EMAIL = "real.person@mail.example.org"


def flow(method, url, *, req_body=b"", req_headers=None, status=200, body=b"", headers=None, ts=1_760_000_000.0):
    req = http.Request.make(method, url, req_body, req_headers or {})
    req.timestamp_start = ts
    req.timestamp_end = ts
    resp = http.Response.make(status, body, headers or {})
    resp.timestamp_start = ts + 0.05
    resp.timestamp_end = ts + 0.1
    return tflow.tflow(req=req, resp=resp)


def recording():
    page = (
        f'<div class="name">{OWN_NAME}</div>'
        f'<a href="/profiles.php?XID={OTHER_ID}">{OTHER_NAME}</a>'
        f"<span>{OTHER_NAME} [{OTHER_ID}]</span>"
        f'<a href="factions.php?step=profile&ID={FACTION_ID}">My Faction</a>'
        f"<p>Contact {EMAIL} from 8.8.4.4, router 10.0.0.1, version 1.2.3</p>"
        "<li>Xanax</li>"
    ).encode()
    return [
        flow(
            "GET",
            f"https://api.torn.com/user/?selections=basic&key={KEY}",
            body=json.dumps({"player_id": int(OWN_ID), "name": OWN_NAME, "level": 30}).encode(),
            headers={"content-type": "application/json"},
        ),
        flow(
            "GET",
            "https://api.torn.com/v2/faction/members",
            req_headers={"Authorization": f"ApiKey {KEY}"},
            body=json.dumps(
                {
                    "members": {
                        OTHER_ID: {"name": OTHER_NAME, "level": 50, "last_action": {"status": "Online"}},
                        OWN_ID: {"name": OWN_NAME, "level": 30, "last_action": {"status": "Online"}},
                    },
                    "items": [{"name": "Xanax", "type": "Drug"}],
                }
            ).encode(),
            headers={"content-type": "application/json"},
            ts=1_760_000_001.0,
        ),
        flow(
            "GET",
            "https://www.torn.com/index.php",
            req_headers={"Cookie": f"PHPSESSID={SESSION}; lang=en; uid={OWN_ID}"},
            body=page,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "gzip",
                "set-cookie": f"PHPSESSID={SESSION}; path=/; secure",
            },
            ts=1_760_000_002.0,
        ),
    ]


def write(path, flows):
    with open(path, "wb") as f:
        w = io.FlowWriter(f)
        for fl in flows:
            w.add(fl)


def read(path):
    with open(path, "rb") as f:
        return list(io.FlowReader(f).stream())


def everything(flows) -> str:
    out = []
    for fl in flows:
        out.extend(pda_anonymize._all_text(fl))
    return "\n".join(out)


@pytest.fixture
def files(tmp_path):
    identity = tmp_path / "identity.json"
    identity.write_text(
        json.dumps(
            {
                "player_id": int(OWN_ID),
                "player_name": OWN_NAME,
                "faction_id": int(FACTION_ID),
                "faction_name": "My Faction",
                "emails": [EMAIL],
            }
        )
    )
    raw = tmp_path / "raw.mitm"
    write(raw, recording())
    return {"identity": identity, "map": tmp_path / "idmap.json", "raw": raw, "anon": tmp_path / "anon.mitm"}


def run_anonymize(f):
    return pda_anonymize.main(
        ["--identity", str(f["identity"]), "--map", str(f["map"]), str(f["raw"]), str(f["anon"])]
    )


def test_anonymize_removes_secrets(files):
    assert run_anonymize(files) == 0
    text = everything(read(files["anon"]))
    for secret in (KEY, OWN_NAME, OWN_ID, OTHER_ID, OTHER_NAME, FACTION_ID, SESSION, EMAIL, "8.8.4.4", "My Faction"):
        assert secret not in text, secret
    # Not personal, so unchanged.
    assert "Xanax" in text
    assert "10.0.0.1" in text and "version 1.2.3" in text
    assert "lang=en" in text


def test_anonymize_keeps_structure_and_is_stable(files):
    assert run_anonymize(files) == 0
    m = json.loads(files["map"].read_text())
    fake_id = m["ids"][OWN_ID]
    assert len(fake_id) == len(OWN_ID) and fake_id.isdigit()
    fake_key = m["keys"][KEY]
    assert len(fake_key) == 16 and fake_key.isalnum()
    flows = read(files["anon"])
    assert f"key={fake_key}" in flows[0].request.url
    assert flows[1].request.headers["authorization"] == f"ApiKey {fake_key}"
    members = json.loads(flows[1].response.text)["members"]
    assert m["ids"][OTHER_ID] in members and members[m["ids"][OTHER_ID]]["name"] == m["names"][OTHER_NAME]
    # The page body is still gzip and still decodes.
    assert flows[2].response.headers["content-encoding"] == "gzip"
    assert f"XID={m['ids'][OTHER_ID]}" in flows[2].response.text
    # A second run with the same map gives the same fake values.
    files["anon"].unlink()
    assert run_anonymize(files) == 0
    assert json.loads(files["map"].read_text())["ids"][OWN_ID] == fake_id


def test_anonymize_handles_many_ids_quickly(files):
    """A faction page has hundreds of IDs and many short numbers after ID=. This once never finished."""
    import time

    rows = "".join(
        f'<a href="/profiles.php?XID={3000000 + i}">Member{i}</a> <a href="page.php?ID={i}">x</a>' for i in range(2000)
    )
    many = recording()
    many.append(flow("GET", "https://www.torn.com/factions.php", body=rows.encode(), headers={"content-type": "text/html"}))
    write(files["raw"], many)
    start = time.monotonic()
    assert run_anonymize(files) == 0
    assert time.monotonic() - start < 20
    page = read(files["anon"])[-1].response.text
    # Short numbers are not player IDs and stay. Player IDs and names change.
    assert 'page.php?ID=7"' in page and 'page.php?ID=999"' in page
    assert "XID=3000007" not in page and ">Member7<" not in page


def test_anonymize_multipart_forms(files):
    """Torn's crimes page posts multipart forms with the player ID and a separate 32-character key."""
    web_key = "Q" * 8 + "w3bK3yW3bK3y0123456789ab"
    boundary = "----WebKitFormBoundaryAbC"
    body = "".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
        for k, v in [("userID", OWN_ID), ("typeID", "3"), ("apiKey", web_key)]
    ) + f"--{boundary}--\r\n"
    multi = recording()
    multi.append(
        flow(
            "POST",
            "https://www.torn.com/crimesHubApi.php",
            req_body=body.encode(),
            req_headers={"content-type": f"multipart/form-data; boundary={boundary}"},
            body=b'{"success": true}',
            headers={"content-type": "application/json"},
        )
    )
    write(files["raw"], multi)
    assert run_anonymize(files) == 0
    req = read(files["anon"])[-1].request
    form = {k.decode(): v.decode() for k, v in req.multipart_form.items()}
    assert form["typeID"] == "3"
    assert form["userID"] != OWN_ID and len(form["userID"]) == len(OWN_ID)
    assert form["apiKey"] != web_key and len(form["apiKey"]) == len(web_key)


def test_anonymize_refuses_to_write_a_leak(files):
    leak = recording()
    leak.append(
        flow(
            "GET",
            "https://www.torn.com/image.php",
            body=f"PNG....{OWN_NAME}....".encode(),
            headers={"content-type": "image/png"},
        )
    )
    write(files["raw"], leak)
    assert run_anonymize(files) == 1
    assert not files["anon"].exists()


def test_anonymize_refuses_bodies_it_cannot_read(files):
    bad = recording()
    broken = flow("GET", "https://www.torn.com/x.php", headers={"content-type": "text/html"})
    broken.response.headers["content-encoding"] = "gzip"
    broken.response.raw_content = b"not gzip " + OWN_NAME.encode()
    bad.append(broken)
    write(files["raw"], bad)
    assert run_anonymize(files) == 1
    assert not files["anon"].exists()


# Replay -----------------------------------------------------------------------


@pytest.fixture
def replay(tmp_path):
    flows = [
        flow("GET", "https://www.torn.com/page.php?sid=a&rfcv=111", req_headers={"Cookie": "uid=3246819; rfc_v=abc"}, body=b"first"),
        flow("GET", "https://www.torn.com/page.php?sid=a&rfcv=222", body=b"second", ts=1_760_000_005.0),
        flow(
            "POST",
            "https://www.torn.com/trade.php",
            req_body=b"step=view&rfcv=111",
            req_headers={"content-type": "application/x-www-form-urlencoded"},
            body=b"trade",
        ),
    ]
    flows.insert(
        0,
        flow(
            "GET",
            "https://www.torn.com/factions.php?step=your",
            req_headers={"Sec-Purpose": "prefetch"},
            status=503,
            ts=1_759_999_999.0,
        ),
    )
    flows.append(flow("GET", "https://www.torn.com/factions.php?step=your", body=b"faction page"))
    flows.append(flow("GET", "https://www.torn.com/css/main.css", status=304))
    rec = tmp_path / "rec.mitm"
    write(rec, flows)
    addon = pda_replay.PdaReplay()
    with taddons.context(addon) as tctx:
        tctx.configure(addon, pda_replay=str(rec), pda_replay_misses=str(tmp_path / "misses.jsonl"))
        yield addon, tctx, tmp_path


async def ask(addon, method, url, body=b"", headers=None):
    f = tflow.tflow(req=http.Request.make(method, url, body, headers or {}))
    await addon.request(f)
    return f.response


async def test_replay_order_and_last_answer_repeats(replay):
    addon, _, _ = replay
    r1 = await ask(addon, "GET", "https://www.torn.com/page.php?sid=a&rfcv=999")
    r2 = await ask(addon, "GET", "https://www.torn.com/page.php?rfcv=x&sid=a")
    r3 = await ask(addon, "GET", "https://www.torn.com/page.php?sid=a")
    assert (r1.content, r2.content, r3.content) == (b"first", b"second", b"second")
    assert r1.headers[pda_replay.HEADER] == "hit"


async def test_replay_form_body_ignores_rfcv_and_falls_back(replay):
    addon, _, tmp = replay
    form = {"content-type": "application/x-www-form-urlencoded"}
    r = await ask(addon, "POST", "https://www.torn.com/trade.php", b"rfcv=abc&step=view", form)
    assert r.content == b"trade" and r.headers[pda_replay.HEADER] == "hit"
    r = await ask(addon, "POST", "https://www.torn.com/trade.php", b"step=other", form)
    assert r.content == b"trade" and r.headers[pda_replay.HEADER] == "loose"
    assert '"loose"' in (tmp / "misses.jsonl").read_text()


async def test_replay_keeps_prefetches_apart_from_page_loads(replay):
    addon, _, _ = replay
    r = await ask(addon, "GET", "https://www.torn.com/factions.php?step=your")
    assert r.status_code == 200 and r.content == b"faction page"
    r = await ask(addon, "GET", "https://www.torn.com/factions.php?step=your", headers={"Sec-Purpose": "prefetch"})
    assert r.status_code == 503


async def test_replay_skips_not_modified_answers(replay):
    addon, _, _ = replay
    r = await ask(addon, "GET", "https://www.torn.com/css/main.css")
    assert r.status_code == 502


async def test_replay_gives_the_client_the_recorded_cookies(replay):
    addon, _, _ = replay
    r = await ask(addon, "GET", "https://www.torn.com/page.php?sid=a", headers={"Cookie": "rfc_v=abc"})
    assert r.headers.get_all("set-cookie") == ["uid=3246819; Domain=.torn.com; Path=/; Secure"]
    r = await ask(addon, "GET", "https://www.torn.com/page.php?sid=a", headers={"Cookie": "uid=3246819; rfc_v=abc"})
    assert r.headers.get_all("set-cookie") == []


async def test_replay_misses_never_forward(replay):
    addon, _, tmp = replay
    r = await ask(addon, "GET", f"https://api.torn.com/user/?key={KEY}")
    assert r.status_code == 502 and r.headers[pda_replay.HEADER] == "miss"
    r = await ask(addon, "GET", "https://www.torn.com/ws", headers={"Upgrade": "websocket"})
    assert r.status_code == 502 and r.headers[pda_replay.HEADER] == "websocket"
    log = (tmp / "misses.jsonl").read_text()
    assert KEY not in log and "REDACTED" in log


def test_replay_refuses_live_torn_connections(replay):
    addon, _, _ = replay
    data = ServerConnectionHookData(server=Server(address=("www.torn.com", 443)), client=tflow.tclient_conn())
    addon.server_connect(data)
    assert data.server.error
    other = ServerConnectionHookData(server=Server(address=("example.com", 443)), client=tflow.tclient_conn())
    addon.server_connect(other)
    assert not other.server.error


def test_replay_backdates_certificates(replay):
    ca = certs.CertStore.from_store(replay[2] / "ca", "mitmproxy", 2048)
    entry = ca.get_cert("www.torn.com", [])
    start = entry.cert.notbefore
    assert start < datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=399)
    assert entry.cert.notafter > datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=150)


def default_save_filter() -> str:
    out = subprocess.run(
        ["bash", "-c", f'. "{Path(__file__).parent / "common.sh"}"; printf %s "$PDA_SAVE"'],
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": "/nonexistent", "PATH": os.environ.get("PATH", "")},
    )
    return out.stdout


def test_capture_default_filter_saves_torn_hosts_only():
    f = flowfilter.parse(default_save_filter())
    hosts = {"www.torn.com": True, "api.torn.com": True, "nottorn.com": False, "torn.com.example": False}
    for host, saved in hosts.items():
        assert bool(f(flow("GET", f"https://{host}/x"))) is saved, host


# Capture ----------------------------------------------------------------------


async def test_capture_marks_are_answered_locally(tmp_path):
    addon = pda_capture.PdaCapture()
    manifest = tmp_path / "rec.json"
    with taddons.context(save.Save(), addon) as tctx:
        tctx.configure(addon, pda_manifest=str(manifest), save_stream_filter=default_save_filter())
        f = tflow.tflow(req=http.Request.make("GET", "https://www.torn.com/pda-mark/trade%20open"))
        addon.request(f)
        assert f.response.status_code == 204
        addon.response(flow("GET", "https://www.torn.com/index.php"))
        addon.response(flow("GET", "https://example.com/x"))
        addon.done()
    data = json.loads(manifest.read_text())
    assert data["marks"][0]["label"] == "trade-open"
    assert data["hosts"]["www.torn.com"] == {"saved": 1, "unsaved": 0}
    assert data["hosts"]["example.com"] == {"saved": 0, "unsaved": 1}
