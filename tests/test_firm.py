"""End-to-end: synthetic data + scripted agents through the real CIO-led research process."""

import json
from pathlib import Path

import pytest

from aladeen.demo import DEMO_DATE, demo_responder, demo_runner, synthetic_factpack
from aladeen.firm.events import EventLog
from aladeen.firm.orchestrator import ResearchRun
from aladeen.firm.prompts import ROLES, system_for
from aladeen.firm.roster import PHASES, ROSTER
from aladeen.firm.schemas import DeskReviewSet, FinalCall
from aladeen.llm import OfflineRunner


def _run(cfg, tmp_path, runner=None, events=None):
    runner = runner or demo_runner()
    ev = events or EventLog()
    state = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=runner, events=ev,
                        factpack_loader=lambda t, d: synthetic_factpack(d), out_dir=tmp_path / "out").run()
    return state, runner, ev


def test_full_research(cfg, tmp_path):
    state, runner, _ = _run(cfg, tmp_path)
    names = [c["agent"] for c in runner.calls]
    for a in ("cio_mandate", "cio_review", "cio_debate", "cio_decision"):  # the CIO leads every stage
        assert a in names
    for desk in ("fundamentals", "business", "governance", "technical", "news", "filings"):
        assert desk in names
    for a in ("valuation", "risk", "council_chair"):
        assert a in names
    assert "technical_rev" in names  # the demo CIO sends the technical memo back once
    assert [r["desk"] for r in state["revisions"]] == ["technical"]
    assert [d["side"] for d in state["debate"]] == ["bull", "bear", "bull", "bear"]
    assert state["final"]["rating"] == state["valuation"]["band_rating"]
    assert state["council"]["verdict"]["verdict"] in ("INVEST", "DO NOT INVEST", "WAIT")
    html = Path(state["paths"]["report"]).read_text(encoding="utf-8")
    for s in ("SECTION 01", "SECTION 09", "SECTION 13", "APPENDIX A4", "Kill fact", "CIO ruling",
              "Independent council review", "AlaDeen Capital Research"):
        assert s in html, s
    assert html.count("<section") == html.count("</section>")
    assert json.loads(Path(state["paths"]["research"]).read_text())["final"]["rating"] == state["final"]["rating"]
    assert "call_id" not in state  # synthetic runs are never logged


def test_event_stream_drives_the_office(cfg, tmp_path):
    _, _, ev = _run(cfg, tmp_path)
    events = ev.all()
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert events[-1]["type"] == "done" and ev.closed
    assert {e["phase"] for e in events if e["type"] == "phase"} == {p["id"] for p in PHASES}
    agents = {a["id"] for a in ROSTER}
    for e in events:
        if e["type"] in ("agent", "message", "log"):
            assert e["agent"] in agents, e
        if e["type"] == "message":
            assert e["to"] in agents and e["text"]
    briefed = {e["to"] for e in events if e["type"] == "message" and e["agent"] == "cio"}
    assert {"fundamentals", "business", "governance", "filings", "news", "technical"} <= briefed


def test_rating_forced_to_bands(cfg, tmp_path):
    def contrarian(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is FinalCall:
            out = out.model_copy(update={"rating": "BUY" if out.rating != "BUY" else "SELL"})
        return out

    state, _, _ = _run(cfg, tmp_path, OfflineRunner(contrarian))
    assert state["final"]["rating"] == state["valuation"]["band_rating"]
    assert state["rating_check"]["consistent"] is False and state["rating_check"]["note"]


def test_no_revision_rounds_means_no_send_backs(cfg, tmp_path):
    cfg["cio_revision_rounds"] = 0
    cfg["council_followup"] = False  # the follow-up has its own switch
    state, runner, _ = _run(cfg, tmp_path)
    assert not [c for c in runner.calls if c["agent"].endswith("_rev")]
    assert state["revisions"] == []


def test_cio_accepting_everything_skips_revisions(cfg, tmp_path):
    def happy(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            out = out.model_copy(update={"reviews": [r.model_copy(update={"verdict": "accept"}) for r in out.reviews]})
        return out

    state, _, _ = _run(cfg, tmp_path, OfflineRunner(happy))
    assert state["revisions"] == []


def test_no_council_and_more_rounds(cfg, tmp_path):
    cfg["run_council"] = False
    cfg["max_debate_rounds"] = 2
    state, _, ev = _run(cfg, tmp_path)
    assert "council" not in state
    assert len(state["debate"]) == 6
    assert "council" not in {e.get("phase") for e in ev.all() if e["type"] == "phase"}


def test_desk_selection(cfg, tmp_path):
    cfg["desks"] = ["fundamentals", "news"]
    state, runner, _ = _run(cfg, tmp_path)
    names = {c["agent"] for c in runner.calls}
    assert {"fundamentals", "news"} <= names
    assert not {"business", "governance", "technical", "filings"} & names
    assert set(state["memos"]) == {"fundamentals", "news"}


def test_valuation_analyst_failure_falls_back_and_is_disclosed(cfg, tmp_path):
    def broken(name, schema, system, user):
        if name == "valuation":
            raise RuntimeError("model unavailable")
        return demo_responder(name, schema, system, user)

    state, _, _ = _run(cfg, tmp_path, OfflineRunner(broken))
    assert any("model unavailable" in e for e in state["errors"])
    assert state["final"]["rating"] == state["valuation"]["band_rating"]


def test_failure_emits_error_event(cfg, tmp_path):
    def broken(name, schema, system, user):
        if name == "cio_decision":
            raise RuntimeError("model unavailable")
        return demo_responder(name, schema, system, user)

    ev = EventLog()
    with pytest.raises(RuntimeError):
        _run(cfg, tmp_path, OfflineRunner(broken), ev)
    assert ev.all()[-1]["type"] == "error" and "model unavailable" in ev.all()[-1]["text"]


def test_missing_api_key_fails_before_data_work(cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg["api_keys"] = {}
    called = []
    ev = EventLog()
    with pytest.raises(RuntimeError, match="Settings"):
        ResearchRun(cfg, "DEMO", DEMO_DATE, events=ev, out_dir=tmp_path / "out",
                    factpack_loader=lambda t, d: called.append(t) or synthetic_factpack(d)).run()
    assert called == []
    assert ev.all()[-1]["type"] == "error"


def test_prompts_contain_house_rules(cfg):
    for agent in ROLES:
        kw = {"advisor": "The Contrarian"} if agent == "council_advisor" else {}
        text = system_for(agent, cfg, **kw)
        assert "Do not introduce new numbers" in text


def test_council_gaps_go_back_to_desks_and_decision_is_resigned(cfg, tmp_path):
    from aladeen.firm.schemas import CouncilVerdict

    calls = {"review": 0}

    def gappy(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            calls["review"] += 1
            if "independent council found these gaps" in user:  # the follow-up review
                out = out.model_copy(update={"reviews": [r.model_copy(update={
                    "verdict": "revise" if r.desk == "business" else "accept", "notes": "Add the sector outlook."})
                    for r in out.reviews]})
        if schema is CouncilVerdict:
            out = out.model_copy(update={"report_complete": False, "gaps_in_report": ["No sector outlook."]})
        return out

    runner = OfflineRunner(gappy)
    state, _, ev = _run(cfg, tmp_path, runner)
    assert {"desk": "business", "notes": "Add the sector outlook.", "round": "council"} in state["revisions"]
    names = [c["agent"] for c in runner.calls]
    assert names.count("cio_decision") == 2  # re-signed after the follow-up
    revised = names.index("business_rev", names.index("council_chair"))
    revalued = names.index("valuation_rev", revised)
    assert revalued < names.index("risk", revalued) < names.index("cio_decision", revalued)
    evidence = next(r for r in state["valuation_revisions"] if r["by"] == "evidence")
    assert evidence["after"] == state["valuation"]["target_price"]
    assert evidence["fair_after"] == state["valuation"]["value_today"]
    assert "followup" in {e.get("phase") for e in ev.all() if e["type"] == "phase"}
    assert state["final"]["rating"] == state["valuation"]["band_rating"]  # compliance ran again


def test_complete_council_skips_followup(cfg, tmp_path):
    from aladeen.firm.schemas import CouncilVerdict

    def done(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is CouncilVerdict:
            out = out.model_copy(update={"report_complete": True})
        return out

    state, runner, ev = _run(cfg, tmp_path, OfflineRunner(done))
    assert [c["agent"] for c in runner.calls].count("cio_decision") == 1
    assert "followup" not in {e.get("phase") for e in ev.all() if e["type"] == "phase"}


def test_research_brief_reaches_cio_and_desks(cfg, tmp_path):
    cfg["research_brief"] = "Always cover the ZEBRA factor."
    seen = set()

    def spy(name, schema, system, user):
        if "ZEBRA factor" in user:
            seen.add(name)
        return demo_responder(name, schema, system, user)

    _run(cfg, tmp_path, OfflineRunner(spy))
    assert {"cio_mandate", "fundamentals", "news"} <= seen


def test_incomplete_report_is_a_draft_and_council_rechecks(cfg, tmp_path):
    from aladeen.firm.schemas import CouncilVerdict

    def gappy(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet and "independent council found these gaps" in user:
            out = out.model_copy(update={"reviews": [r.model_copy(update={
                "verdict": "revise" if r.desk == "business" else "accept"}) for r in out.reviews]})
        if schema is CouncilVerdict:
            out = out.model_copy(update={"report_complete": False, "gaps_in_report": ["No sector outlook."]})
        return out

    state, runner, _ = _run(cfg, tmp_path, OfflineRunner(gappy))
    assert [c["agent"] for c in runner.calls].count("council_chair") == 2  # checked again after the follow-up
    assert state["council"]["first_verdict"]["report_complete"] is False
    assert state["report_status"] == "draft" and "No sector outlook" in state["draft_reason"]
    assert "DRAFT" in Path(state["paths"]["report"]).read_text(encoding="utf-8")


def test_complete_report_is_final(cfg, tmp_path):
    from aladeen.firm.schemas import CouncilVerdict

    def done(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        return out.model_copy(update={"report_complete": True}) if schema is CouncilVerdict else out

    state, _, _ = _run(cfg, tmp_path, OfflineRunner(done))
    assert state["report_status"] == "final"


def test_cio_can_challenge_the_valuation_once(cfg, tmp_path):
    seen = []

    def challenger(name, schema, system, user):
        out = demo_responder(name, schema, system, user)
        if schema is FinalCall and not seen:
            seen.append(1)
            out = out.model_copy(update={"valuation_challenge": "Margins are understated: the concall guides higher."})
        if name == "valuation_rev":
            assert "Margins are understated" in user and "previous assumptions" in user
        return out

    state, runner, _ = _run(cfg, tmp_path, OfflineRunner(challenger))
    names = [c["agent"] for c in runner.calls]
    assert "valuation_rev" in names and names.count("cio_decision") >= 2
    assert any(r["by"] == "cio" for r in state["valuation_revisions"])
    assert state["final"]["rating"] == state["valuation"]["band_rating"]


def test_reality_check_sends_valuation_back(cfg, tmp_path):
    cfg["reality_check_threshold"] = 0.0  # every target is "far" from the price
    state, runner, _ = _run(cfg, tmp_path)
    assert "valuation_rev" in [c["agent"] for c in runner.calls]
    assert state["valuation_revisions"][0]["by"] == "reality_check"


def test_debate_openings_do_not_see_the_valuation(cfg, tmp_path):
    seen = {}

    def spy(name, schema, system, user):
        seen[name] = user
        return demo_responder(name, schema, system, user)

    _run(cfg, tmp_path, OfflineRunner(spy))
    assert "## Valuation (method" not in seen["bull_r0"] and "## Valuation (method" not in seen["bear_r0"]
    assert "## Valuation (method" in seen["bull_r1"] and "## Valuation (method" in seen["cio_debate"]


def test_revision_sees_other_desks(cfg, tmp_path):
    seen = {}

    def spy(name, schema, system, user):
        seen[name] = user
        return demo_responder(name, schema, system, user)

    _run(cfg, tmp_path, OfflineRunner(spy))
    assert "The other desks' memos" in seen["technical_rev"]
    assert "Memo — " in seen["technical_rev"]
