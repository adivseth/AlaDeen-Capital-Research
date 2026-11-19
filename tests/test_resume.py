"""A failed research can be tried again, and the same research continues from where it stopped."""

import time
from pathlib import Path

import pytest
import typer
from fastapi.testclient import TestClient

import aladeen.demo as demo_mod
from aladeen.cli import _failed_id
from aladeen.config import PROVIDER_KEY_ENV
from aladeen.demo import DEMO_DATE, demo_responder, demo_runner, synthetic_factpack
from aladeen.firm.events import EventLog
from aladeen.firm.journal import JOURNAL_FILE, JournalRunner
from aladeen.firm.orchestrator import ResearchRun
from aladeen.firm.schemas import FinalCall
from aladeen.llm import OfflineRunner
from aladeen.server.app import create_app


def _flaky(fail_on: str, state: dict):
    """A scripted firm whose ``fail_on`` agent fails once (the model is 'unavailable'), then works."""

    def responder(name, schema, system, user):
        if name == fail_on and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("model unavailable")
        return demo_responder(name, schema, system, user)

    return responder


# ---------------------------------------------------------------------------- the journal
def test_journal_replays_answers_without_asking_the_model_again(tmp_path):
    inner = OfflineRunner(lambda name, schema, system, user: demo_responder(name, schema, system, user))
    path = tmp_path / JOURNAL_FILE
    j = JournalRunner(inner, path)
    text = j.text("sys", "question", tier="quick", name="fundamentals")
    final = j.structured("sys", "decide", FinalCall, tier="deep", name="cio_decision")
    assert len(inner.calls) == 2 and j.replayed == 0

    again = JournalRunner(OfflineRunner(lambda *a: pytest.fail("the model must not be asked again")), path)
    assert again.restored == 2
    assert again.text("sys", "question", tier="quick", name="fundamentals") == text
    assert again.structured("sys", "decide", FinalCall, tier="deep", name="cio_decision") == final
    assert again.replayed == 2


def test_journal_asks_a_different_question_for_real(tmp_path):
    inner = OfflineRunner(lambda name, schema, system, user: "answer")
    j = JournalRunner(inner, tmp_path / JOURNAL_FILE)
    j.text("sys", "question one", name="a")
    j.text("sys", "question two", name="a")
    assert len(inner.calls) == 2


def test_the_same_question_asked_twice_gets_its_own_answer_each_time(tmp_path):
    """A recheck asks an identical question and may deserve a new answer; a retry must keep them apart."""
    answers = iter(["first answer", "second answer"])
    path = tmp_path / JOURNAL_FILE
    j = JournalRunner(OfflineRunner(lambda *a: next(answers)), path)
    assert [j.text("s", "u", name="a"), j.text("s", "u", name="a")] == ["first answer", "second answer"]
    again = JournalRunner(OfflineRunner(lambda *a: pytest.fail("not asked again")), path)
    assert [again.text("s", "u", name="a"), again.text("s", "u", name="a")] == ["first answer", "second answer"]


def test_journal_survives_a_half_written_last_line(tmp_path):
    path = tmp_path / JOURNAL_FILE
    JournalRunner(OfflineRunner(lambda *a: "kept"), path).text("s", "u", name="a")
    with path.open("a", encoding="utf-8") as f:
        f.write('{"key": "abc", "kind": "te')  # the app was killed mid-write
    j = JournalRunner(OfflineRunner(lambda *a: pytest.fail("not asked again")), path)
    assert j.restored == 1 and j.text("s", "u", name="a") == "kept"


def test_a_failed_call_is_not_remembered(tmp_path):
    state = {"failed": False}

    def once(name, schema, system, user):
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("rate limited")
        return "fine"

    path = tmp_path / JOURNAL_FILE
    j = JournalRunner(OfflineRunner(once), path)
    with pytest.raises(RuntimeError):
        j.text("s", "u", name="a")
    assert not path.exists() or path.read_text() == ""
    assert j.text("s", "u", name="a") == "fine"


# ---------------------------------------------------------------------------- the research
def test_failed_research_continues_where_it_stopped(cfg, tmp_path):
    loads = []

    def loader(ticker, day):
        loads.append(ticker)
        return synthetic_factpack(day)

    out = tmp_path / "out"
    first = OfflineRunner(_flaky("cio_decision", {"failed": False}))
    with pytest.raises(RuntimeError, match="model unavailable"):
        ResearchRun(cfg, "DEMO", DEMO_DATE, runner=first, events=EventLog(), factpack_loader=loader,
                    out_dir=out).run()
    asked_before = len(first.calls)
    assert (out / JOURNAL_FILE).exists() and (out / "factpack.json").exists()

    second, ev = demo_runner(), EventLog()
    state = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=second, events=ev, factpack_loader=loader, out_dir=out,
                        resume=True).run()

    redone = [c["agent"] for c in second.calls]
    assert loads == ["DEMO"], "the data is collected once, not again on the retry"
    for finished in ("cio_mandate", "fundamentals", "business", "governance", "bull_r0", "bear_r0", "risk"):
        assert finished not in redone, f"{finished} was already done and paid for"
    assert "cio_decision" in redone  # the step that failed is the one that runs again
    assert len(redone) < asked_before
    assert state["final"]["rating"] == state["valuation"]["band_rating"]
    assert Path(state["paths"]["report"]).exists()

    events = ev.all()
    assert events[-1]["type"] == "done" and events[-1]["reused_calls"] >= 10
    assert any("Continuing the earlier research" in e.get("text", "") for e in events)


def test_resumed_research_matches_an_uninterrupted_one(cfg, tmp_path):
    whole = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=demo_runner(), events=EventLog(),
                        factpack_loader=lambda t, d: synthetic_factpack(d), out_dir=tmp_path / "whole").run()
    out = tmp_path / "broken"
    with pytest.raises(RuntimeError):
        ResearchRun(cfg, "DEMO", DEMO_DATE, runner=OfflineRunner(_flaky("risk", {"failed": False})),
                    events=EventLog(), factpack_loader=lambda t, d: synthetic_factpack(d), out_dir=out).run()
    resumed = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=demo_runner(), events=EventLog(),
                          factpack_loader=lambda t, d: synthetic_factpack(d), out_dir=out, resume=True).run()
    for k in ("final", "valuation", "memos", "debate"):
        assert resumed[k] == whole[k], k


def test_a_fresh_run_never_reuses_an_old_journal(cfg, tmp_path):
    def run():
        runner = demo_runner()
        ResearchRun(cfg, "DEMO", DEMO_DATE, runner=runner, events=EventLog(),
                    factpack_loader=lambda t, d: synthetic_factpack(d), out_dir=tmp_path / "out").run()
        return runner

    assert len(run().calls) == len(run().calls) > 10


# ---------------------------------------------------------------------------- the dashboard
@pytest.fixture
def client(tmp_path, monkeypatch):
    for env in PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    return TestClient(create_app(str(tmp_path / "home")))


def _wait(client, run_id):
    since = 0
    while True:
        res = client.get(f"/api/runs/{run_id}/events", params={"since": since, "wait": 5}).json()
        since += len(res["events"])
        if res["closed"]:
            break
    for _ in range(100):
        rec = client.get(f"/api/runs/{run_id}").json()
        if rec["status"] != "running":
            return rec
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_try_again_continues_a_failed_research(client, monkeypatch):
    runners, state = [], {"failed": False}

    def factory(delay=0.0):
        runners.append(OfflineRunner(_flaky("cio_decision", state)))
        return runners[-1]

    monkeypatch.setattr(demo_mod, "demo_runner", factory)

    run_id = client.post("/api/research", json={"demo": True}).json()["id"]
    failed = _wait(client, run_id)
    assert failed["status"] == "error" and "model unavailable" in failed["error"]

    assert client.post(f"/api/runs/{run_id}/retry").json() == {"id": run_id}
    done = _wait(client, run_id)
    assert done["status"] == "done" and done["error"] is None and done["rating"] in ("BUY", "HOLD", "SELL")
    assert [r["id"] for r in client.get("/api/runs").json()] == [run_id]  # the same research, not a new one

    assert len(runners) == 2
    assert len(runners[1].calls) < len(runners[0].calls)  # only what was left was run
    events = client.get(f"/api/runs/{run_id}/events", params={"since": 0, "wait": 0}).json()["events"]
    assert events[-1]["type"] == "done" and events[-1]["reused_calls"] >= 10
    assert client.get(f"/api/runs/{run_id}/report").status_code == 200


def test_try_again_is_only_for_failed_research(client, monkeypatch):
    original = demo_mod.demo_runner
    monkeypatch.setattr(demo_mod, "demo_runner", lambda delay=0.0: original(0.0))
    run_id = client.post("/api/research", json={"demo": True}).json()["id"]
    assert _wait(client, run_id)["status"] == "done"
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 409  # nothing to continue
    assert client.post("/api/runs/does-not-exist/retry").status_code == 404


def test_try_again_after_the_app_was_closed(client, monkeypatch):
    """A research cut off by closing the dashboard is marked failed and can be continued too."""
    state = {"failed": False}
    monkeypatch.setattr(demo_mod, "demo_runner", lambda delay=0.0: OfflineRunner(_flaky("risk", state)))
    run_id = client.post("/api/research", json={"demo": True}).json()["id"]
    assert _wait(client, run_id)["status"] == "error"
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 200
    assert _wait(client, run_id)["status"] == "done"


# ---------------------------------------------------------------------------- the command line
def test_retry_command_picks_the_latest_failed_research():
    runs = [{"id": "c", "status": "done"}, {"id": "b", "status": "error"}, {"id": "a", "status": "error"}]
    assert _failed_id(None, runs) == "b"  # the archive is newest first
    assert _failed_id("a", runs) == "a"
    with pytest.raises(typer.Exit):
        _failed_id(None, [{"id": "c", "status": "done"}])
