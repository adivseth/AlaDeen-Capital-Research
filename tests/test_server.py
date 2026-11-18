"""Dashboard API: settings, research runs, archive, report downloads (offline demo, no AI calls)."""

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import aladeen.demo as demo_mod
from aladeen.server.app import create_app

KEY_ENVS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY")


@pytest.fixture
def client(tmp_path, monkeypatch):
    for k in KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    original = demo_mod.demo_runner
    monkeypatch.setattr(demo_mod, "demo_runner", lambda delay=0.0: original(0.0))  # no pacing in tests
    return TestClient(create_app(str(tmp_path / "home")))


def _finish(client, run_id):
    since = 0
    while True:
        res = client.get(f"/api/runs/{run_id}/events", params={"since": since, "wait": 5}).json()
        for e in res["events"]:
            assert e["seq"] == since
            since += 1
        if res["closed"]:
            break
    for _ in range(50):
        rec = client.get(f"/api/runs/{run_id}").json()
        if rec["status"] != "running":
            return rec, since
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_shell_and_static(client):
    assert client.get("/api/health").json()["app"] == "AlaDeen Capital Research"
    page = client.get("/")
    assert page.status_code == 200 and "/static/app.js" in page.text
    for f in ("app.js", "app.css"):
        assert client.get(f"/static/{f}").status_code == 200
    r = client.get("/api/roster").json()
    assert {a["id"] for a in r["agents"]} >= {"cio", "valuation", "bull", "bear", "risk", "council", "editor"}
    assert all(a["room"] in {x["id"] for x in r["rooms"]} for a in r["agents"])


def test_settings_roundtrip_and_key_masking(client):
    s = client.get("/api/settings").json()
    assert s["values"]["llm_provider"] == "anthropic"
    assert not s["keys"]["anthropic"]["set"]
    out = client.put("/api/settings", json={"values": {"llm_provider": "openai", "deep_think_llm": "m-deep",
                                                       "quick_think_llm": "m-quick", "cio_revision_rounds": 2,
                                                       "not_a_setting": 1},
                                            "api_keys": {"openai": "sk-secret-abcdefgh1234"}}).json()
    assert out["values"]["llm_provider"] == "openai" and out["values"]["cio_revision_rounds"] == 2
    assert out["keys"]["openai"] == {"set": True, "source": "dashboard", "masked": "sk-…1234"}
    assert "sk-secret" not in client.get("/api/settings").text
    path = out["paths"]["settings"]
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    saved = json.loads(Path(path).read_text())
    assert "not_a_setting" not in saved and saved["api_keys"]["openai"] == "sk-secret-abcdefgh1234"
    out = client.put("/api/settings", json={"clear_keys": ["openai"]}).json()
    assert not out["keys"]["openai"]["set"]


def test_backup_source_keys(client):
    s = client.get("/api/settings").json()
    assert [d["id"] for d in s["data_sources"]] == ["alphavantage", "firecrawl", "exa"]
    out = client.put("/api/settings", json={"api_keys": {"firecrawl": "fc-abcdefghijkl1234"}}).json()
    assert out["keys"]["firecrawl"]["set"] and "fc-abcdefghijkl" not in json.dumps(out)
    assert client.put("/api/settings", json={"api_keys": {"evil": "x"}}).status_code == 400


def test_bad_settings_rejected(client):
    assert client.put("/api/settings", json={"values": {"desks": ["astrology"]}}).status_code == 400
    assert client.put("/api/settings", json={"values": {"llm_provider": "nope"}}).status_code == 400
    assert client.get("/api/settings").json()["values"]["llm_provider"] == "anthropic"  # nothing was saved


def test_research_validation(client):
    assert client.post("/api/research", json={"ticker": ""}).status_code == 400
    assert client.post("/api/research", json={"ticker": "TCS", "as_of": "19-11-2026"}).status_code == 400


def test_demo_run_archive_and_downloads(client):
    run_id = client.post("/api/research", json={"demo": True}).json()["id"]
    rec, n_events = _finish(client, run_id)
    assert rec["status"] == "done", rec.get("error")
    assert rec["rating"] in ("BUY", "HOLD", "SELL") and rec["company"] and rec["demo"]
    assert n_events > 50
    replay = client.get(f"/api/runs/{run_id}/events", params={"since": 0, "wait": 0}).json()
    assert replay["closed"] and len(replay["events"]) == n_events

    assert [r["id"] for r in client.get("/api/runs").json()] == [run_id]
    report = client.get(f"/api/runs/{run_id}/report")
    assert report.status_code == 200 and "window.print" not in report.text
    assert "window.print" in client.get(f"/api/runs/{run_id}/report", params={"print": 1}).text
    dl = client.get(f"/api/runs/{run_id}/report", params={"download": 1})
    assert "attachment" in dl.headers["content-disposition"]
    for name in ("factpack.json", "research.json", "transcript.md", "events.json"):
        assert client.get(f"/api/runs/{run_id}/file/{name}").status_code == 200
    assert client.get(f"/api/runs/{run_id}/file/settings.json").status_code == 404
    assert "# " in client.get(f"/api/runs/{run_id}/transcript").text
    assert client.get("/api/calls").json()["rows"] == []  # demo runs are not logged

    out_dir = rec["out_dir"]
    assert os.path.isdir(out_dir)
    assert client.delete(f"/api/runs/{run_id}").json() == {"ok": True}
    assert not os.path.exists(out_dir)
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_missing_key_fails_fast_with_settings_hint(client):
    run_id = client.post("/api/research", json={"ticker": "TCS"}).json()["id"]
    rec, _ = _finish(client, run_id)
    assert rec["status"] == "error" and "Settings" in rec["error"]
    last = client.get(f"/api/runs/{run_id}/events", params={"since": 0, "wait": 0}).json()["events"][-1]
    assert last["type"] == "error"
