"""A decision-changing conflict pauses the research for the firm owner, and the owner's ruling resumes it."""
import json

import pytest

from aladeen.demo import DEMO_DATE, demo_responder, synthetic_factpack
from aladeen.firm.events import EventLog
from aladeen.firm.orchestrator import QUESTIONS_FILE, ResearchRun, open_questions, record_rulings
from aladeen.firm.schemas import DeskReviewSet
from aladeen.llm import OfflineRunner
from tests.test_authority import disputed

CONFLICT = "The revised company presentation puts fuel-cell revenue at one figure; the concall transcript at another."


class Recorder(OfflineRunner):
    """The demo agents, with the CIO raising a conflict and every prompt kept for inspection."""

    def __init__(self, conflict: str | None = CONFLICT):
        self.prompts: list[tuple[str, str]] = []

        def responder(name, schema, system, user):
            self.prompts.append((name, user))
            out = demo_responder(name, schema, system, user)
            if schema is DeskReviewSet and conflict and "firm owner's rulings" not in user:
                out.unresolved_material_conflicts = [conflict]
            return out

        super().__init__(responder)


def run(cfg, tmp_path, runner, fp=None, resume=False, events=None):
    loader = (lambda *_: fp) if fp is not None else (lambda *_: synthetic_factpack())
    return ResearchRun(cfg, "DEMO", DEMO_DATE, runner=runner, factpack_loader=loader, out_dir=tmp_path,
                       resume=resume, events=events).run()


def test_conflict_pauses_before_valuation_and_ruling_resumes(cfg, tmp_path):
    cfg.update(run_council=False)
    first, ev = Recorder(), EventLog()
    state = run(cfg, tmp_path, first, events=ev)
    assert state["held"]["stage"] == "review" and "final" not in state
    assert "valuation" not in [c["agent"] for c in first.calls]
    assert not (tmp_path / "report.html").exists()  # nothing published while it waits
    held = open_questions(tmp_path)
    [q] = held["questions"]
    assert q["kind"] == "conflict" and q["text"] == CONFLICT and held["memos"]
    assert ev.closed and ev.all()[-1]["type"] == "hold"
    assert "Paused for the firm owner" in (tmp_path / "transcript.md").read_text()

    with pytest.raises(ValueError, match="Rule on every open question"):
        record_rulings(tmp_path, {})
    record_rulings(tmp_path, {q["id"]: {"ruling": "Use the revised presentation: it supersedes the call."}})

    second = Recorder()
    state = run(cfg, tmp_path, second, resume=True)
    assert "held" not in state and state["report_status"] == "final"
    assert state["final"]["rating"] in ("BUY", "HOLD", "SELL") and state["valuation"]["target_price"]
    assert not [c for c in second.calls if c["agent"] in ("cio_mandate", "cio_review")]  # reused, not re-asked
    valuation_prompt = next(u for n, u in second.prompts if n == "valuation")
    assert "Use the revised presentation" in valuation_prompt
    decision_prompt = next(u for n, u in second.prompts if n == "cio_decision")
    assert "firm owner's rulings" in decision_prompt
    saved = json.loads((tmp_path / "research.json").read_text())
    assert saved["owner_rulings"][0]["question"] == CONFLICT
    assert "resumed on the firm owner" in (tmp_path / "report.html").read_text()


def test_resume_replays_finished_work(cfg, tmp_path):
    cfg.update(run_council=False)
    run(cfg, tmp_path, Recorder())
    q = open_questions(tmp_path)["questions"][0]
    record_rulings(tmp_path, {q["id"]: {"ruling": "The concall figure is right."}})
    r = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=Recorder(), factpack_loader=lambda *_: synthetic_factpack(),
                    out_dir=tmp_path, resume=True)
    r.run()
    assert r.runner.replayed >= 5  # mandate, desk memos and the CIO review are reused, not paid for again


def test_vendor_figure_conflict_takes_the_owners_number(cfg, tmp_path):
    cfg.update(run_council=False)
    state = run(cfg, tmp_path, Recorder(conflict=None), fp=disputed())
    [q] = state["held"]["questions"]
    assert q["kind"] == "data" and q["metric"] == "Revenue" and q["feeds"]["Yahoo"] == 2117.71
    with pytest.raises(ValueError, match="number"):
        record_rulings(tmp_path, {q["id"]: {"value": "lots"}})
    record_rulings(tmp_path, {q["id"]: {"value": 2150, "ruling": "FY26 annual report, p.112"}})

    state = run(cfg, tmp_path, Recorder(conflict=None), fp=disputed(), resume=True)
    assert state["report_status"] == "final" and state["valuation"]["target_price"]
    fact = next(f for f in state["fp"].fact_resolutions if f["status"] == "owner")
    assert fact["value"] == 2150 and fact["owner_note"] == "FY26 annual report, p.112"
    assert state["quant"]["default_dcf_inputs"].base_revenue == 2150
    assert "set by the firm owner" in (tmp_path / "report.html").read_text()


def test_council_conflict_holds_the_signed_call(cfg, tmp_path):
    from aladeen.firm.schemas import CouncilVerdict

    def responder(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is CouncilVerdict:
            out.report_complete, out.gaps_in_report = True, []
            if "firm owner's rulings" not in user:
                out.unresolved_material_conflicts = ["Order-book size differs between the AR and the investor deck."]
        return out

    cfg.update(run_council=True, council_followup=False)
    state = run(cfg, tmp_path, OfflineRunner(responder))
    assert state["held"]["stage"] == "council" and not state.get("call_id")
    [q] = state["held"]["questions"]
    record_rulings(tmp_path, {q["id"]: {"ruling": "The annual report figure is the audited one; use it."}})
    state = run(cfg, tmp_path, OfflineRunner(responder), resume=True)
    assert state["report_status"] == "final" and state["final"]["rating"]


def test_owner_can_publish_the_draft_instead(cfg, tmp_path):
    cfg.update(run_council=False)
    run(cfg, tmp_path, Recorder())
    record_rulings(tmp_path, {}, publish_draft=True)
    state = run(cfg, tmp_path, Recorder(), resume=True)
    assert state["report_status"] == "draft" and state["final"]["rating"] is None
    assert CONFLICT in state["draft_reason"] and not state.get("call_id")


def test_holding_can_be_switched_off(cfg, tmp_path):
    cfg.update(run_council=False, hold_for_owner=False)
    state = run(cfg, tmp_path, Recorder())
    assert "held" not in state and state["report_status"] == "draft"
    assert not (tmp_path / QUESTIONS_FILE).exists()


def test_no_conflict_asks_the_agents_the_same_questions(cfg, tmp_path):
    cfg.update(run_council=False)
    runner = Recorder(conflict=None)
    state = run(cfg, tmp_path, runner)
    assert state["report_status"] == "final" and not state["owner_rulings"]
    assert all("firm owner's rulings" not in u for _, u in runner.prompts)


def test_dashboard_pause_and_resolve(tmp_path, monkeypatch):
    import time

    from fastapi.testclient import TestClient

    import aladeen.demo as demo_mod
    from aladeen.server.app import create_app

    monkeypatch.setattr(demo_mod, "demo_runner", lambda delay=0.0: Recorder())
    client = TestClient(create_app(str(tmp_path / "home")))

    def settle(run_id):
        for _ in range(200):
            rec = client.get(f"/api/runs/{run_id}").json()
            if rec["status"] != "running":
                return rec
            time.sleep(0.1)
        raise AssertionError("still running")

    run_id = client.post("/api/research", json={"demo": True}).json()["id"]
    rec = settle(run_id)
    assert rec["status"] == "awaiting" and rec["headline"] == "Paused: 1 conflict needs your ruling"
    [q] = rec["hold"]["questions"]
    assert q["text"] == CONFLICT and rec["hold"]["memos"]
    assert client.get(f"/api/runs/{run_id}/transcript").status_code == 200
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 409  # a pause is not a failure

    bad = client.post(f"/api/runs/{run_id}/resolve", json={"rulings": {q["id"]: {"ruling": " "}}})
    assert bad.status_code == 400 and "Rule on every open question" in bad.json()["detail"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting"

    ok = client.post(f"/api/runs/{run_id}/resolve", json={"rulings": {q["id"]: {"ruling": "Revised deck wins."}}})
    assert ok.status_code == 200
    rec = settle(run_id)
    assert rec["status"] == "done" and rec["rating"] and rec["target_price"]
    assert rec["research"]["owner_rulings"][0]["ruling"] == "Revised deck wins."
    assert client.post(f"/api/runs/{run_id}/resolve", json={"rulings": {}}).status_code == 409


BETA = "Market sensitivity: the snapshot beta is 0.58 from two years of weekly data; a separate input is 0.72."
BETA_AGAIN = "Cost of equity: beta input 0.72 has no documented basis versus the regression's 0.58."
PHASE3 = "Fuel-cell Phase 3 commissioning: the August call and the revised deck give different quarters."


def clerk(user):
    """A stand-in for the conflict clerk: the same point is the one that mentions beta."""
    import re

    from aladeen.firm.schemas import ConflictMatch, ConflictMatches

    ruled = re.findall(r"^- id (q-\w+): (.*)$", user, re.M)
    new = re.findall(r"^(\d+)\. (.*)$", user.split("## New conflicts", 1)[1], re.M)
    out, first_beta = [], None
    for i, text in new:
        i = int(i)
        same = next((rid for rid, q in ruled if "beta" in q.lower() and "beta" in text.lower()), None)
        dup = first_beta if same is None and "beta" in text.lower() and first_beta is not None else None
        if "beta" in text.lower() and first_beta is None:
            first_beta = i
        out.append(ConflictMatch(index=i, same_as_ruling=same, duplicate_of=dup))
    return ConflictMatches(matches=out)


def test_a_ruled_point_reworded_later_is_not_asked_again(cfg, tmp_path):
    from aladeen.firm.schemas import ConflictMatches, CouncilVerdict

    def responder(name, schema, system, user):
        if schema is ConflictMatches:
            return clerk(user)
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            out.unresolved_material_conflicts = [BETA]
        if schema is CouncilVerdict:  # the council ignores the instruction and raises beta again, reworded
            out.report_complete, out.gaps_in_report = True, []
            out.unresolved_material_conflicts = [BETA_AGAIN]
        return out

    cfg.update(run_council=True, council_followup=False)
    state = run(cfg, tmp_path, OfflineRunner(responder))
    [q] = state["held"]["questions"]
    record_rulings(tmp_path, {q["id"]: {"ruling": "0.72 is the Blume adjustment of 0.58; use 0.72."}})
    ev = EventLog()
    state = run(cfg, tmp_path, OfflineRunner(responder), resume=True, events=ev)
    assert "held" not in state and state["report_status"] == "final" and state["final"]["rating"]
    assert any("Already ruled by the firm owner" in e.get("text", "") for e in ev.all())


def test_one_point_raised_twice_is_one_question(cfg, tmp_path):
    from aladeen.firm.schemas import ConflictMatches

    def responder(name, schema, system, user):
        if schema is ConflictMatches:
            return clerk(user)
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            out.unresolved_material_conflicts = [BETA, PHASE3, BETA_AGAIN, BETA]
        return out

    cfg.update(run_council=False)
    state = run(cfg, tmp_path, OfflineRunner(responder))
    qs = state["held"]["questions"]
    assert [q["text"] for q in qs] == [BETA, PHASE3]
    assert qs[0]["also"] == [BETA_AGAIN]


def test_a_failed_repeat_check_still_asks_the_owner(cfg, tmp_path):
    from aladeen.firm.schemas import ConflictMatches

    def responder(name, schema, system, user):
        if schema is ConflictMatches:
            raise RuntimeError("model unavailable")
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            out.unresolved_material_conflicts = [BETA, PHASE3]
        return out

    cfg.update(run_council=False)
    state = run(cfg, tmp_path, OfflineRunner(responder))
    assert len(state["held"]["questions"]) == 2
    assert any("Repeat check" in e for e in state["errors"])


def test_the_beta_adjustment_is_explained_to_the_agents(cfg):
    from aladeen.firm import context as cx
    from aladeen.quant.engine import compute_quant

    q = compute_quant(synthetic_factpack(), cfg, with_charts=False)
    md = cx.market_md(q)
    raw = q["market"]["beta_raw"]
    assert f"Blume adjustment 0.67 x {raw:.2f} + 0.33" in md and "not a second source" in md


def test_a_ruling_carries_to_the_next_research_on_the_company(cfg, tmp_path):
    from aladeen.firm.orchestrator import carried_rulings, remember_rulings
    from aladeen.firm.schemas import ConflictMatches

    def responder(name, schema, system, user):
        if schema is ConflictMatches:
            return clerk(user)
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            out.unresolved_material_conflicts = [BETA_AGAIN]  # the next research words it differently
        return out

    first = tmp_path / "first"
    cfg.update(run_council=False)
    run(cfg, first, Recorder(conflict=BETA))
    saved = record_rulings(first, {open_questions(first)["questions"][0]["id"]: {"ruling": "Use the Blume 0.72."}})
    remember_rulings(cfg, "DEMO", saved["rulings"], "run-1", DEMO_DATE)

    second = tmp_path / "second"
    state = run(cfg, second, OfflineRunner(responder))
    assert "held" not in state and state["report_status"] == "final"
    assert state["owner_rulings"][0]["carried"] and state["owner_rulings"][0]["run"] == "run-1"
    assert "from your ruling in research run-1" in (second / "report.html").read_text()

    cfg["carry_rulings_days"] = 0
    assert not carried_rulings(cfg, "DEMO", DEMO_DATE)
    cfg["carry_rulings_days"] = 90
    assert not carried_rulings(cfg, "DEMO", "2020-01-01")  # a backdated research cannot use a later ruling


def test_rulings_given_before_the_register_still_count(cfg, tmp_path):
    from pathlib import Path

    from aladeen.firm.orchestrator import carried_rulings

    old = Path(cfg["results_dir"]) / "20261120-164109-DEMO-167f"
    cfg.update(run_council=False)
    run(cfg, old, Recorder(conflict=BETA))
    q = open_questions(old)["questions"][0]
    record_rulings(old, {q["id"]: {"ruling": "Blume 0.72 is right."}})  # saved in the run folder only
    carried = carried_rulings(cfg, "DEMO", DEMO_DATE)
    assert carried[q["id"]]["ruling"] == "Blume 0.72 is right." and carried[q["id"]]["run"] == old.name
