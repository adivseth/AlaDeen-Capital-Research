"""Filed facts must reach the engine before analysts or publication can select a number."""
import json
from pathlib import Path

import pytest

from aladeen.dataflows.authority import filed_rows
from aladeen.dataflows.factpack import FactPack
from aladeen.demo import DEMO_DATE, demo_runner, synthetic_factpack
from aladeen.firm.orchestrator import ResearchRun
from aladeen.quant.engine import compute_quant, value_company

PAGE = """Consolidated Statement of Profit and Loss
Amounts in INR lakhs
Particulars Note Year ended March 31, 2026 Year ended March 31, 2025
Revenue from operations 27 215,000 180,000
Profit attributable to owners of the parent 20,000 15,000
Total equity dividend attributable to the financial year 4,000 3,000
"""


def disputed():
    fp = synthetic_factpack()
    t = fp.screener["tables"]["profit_loss"]
    t["rows"]["Sales"][-2] = 2302
    t["rows"]["Dividend Payout %"][-2] = 15
    fp.yahoo["annual_income"] = {"Total Revenue": {"2026-03-31": 2117.71e7}}
    return fp


def filing(page=PAGE, **kwargs):
    return dict(kind="annual_report", title="FY26 accounts", url="https://www.bseindia.com/filing.pdf",
                period="2026", filed_rows=filed_rows(["Cover", page]), **kwargs)


def test_filing_drives_engine_and_restatement(cfg):
    fp = disputed()
    fp.documents = [filing(filed_on="2026-07-01")]
    q = compute_quant(fp, cfg, with_charts=False)
    assert not q["valuation_blockers"]
    assert q["default_dcf_inputs"].base_revenue == 2150
    annual = q["statements"]["annual"]
    assert annual.at["FY26", "Dividend Payout %"] == 20
    fact = next(r for r in fp.fact_resolutions if r["metric"] == "Revenue" and r["period"] == "Mar 2026")
    assert fact["feeds"] == {"Screener": 2302, "Yahoo": 2117.71}
    assert fact["evidence"][0]["page"] == 2
    assert FactPack.from_json(fp.to_json()).fact_resolutions == fp.fact_resolutions
    old = value_company(q, cfg)
    fp.documents.append(filing(PAGE.replace("215,000", "225,000"), filed_on="2026-10-01"))
    q = compute_quant(fp, cfg, with_charts=False)
    assert q["default_dcf_inputs"].base_revenue == 2250
    assert value_company(q, cfg).target_price != old.target_price


@pytest.mark.parametrize("doc", [filing(PAGE.replace("Consolidated", "Standalone")), filing(filed_on="2027-01-01"),
                                 {**filing(), "url": "https://bseindia.com.example.org/file.pdf"},
                                 filing(PAGE.replace("INR lakhs", "units unclear"))])
def test_ineligible_filing_keeps_material_conflict_open(cfg, doc):
    fp = disputed()
    fp.documents = [doc]
    q = compute_quant(fp, cfg, with_charts=False)
    assert q["valuation_blockers"]
    with pytest.raises(ValueError, match="pending reconciliation"):
        value_company(q, cfg)


def test_payout_narrative_is_a_lead_only(cfg):
    fp = disputed()
    fp.yahoo["annual_income"] = {}
    fp.documents = [filing("Dividend payout for the financial year was 20%.")]
    q = compute_quant(fp, cfg, with_charts=False)
    assert fp.fact_resolutions[0]["status"] == "unresolved"
    assert not q["valuation_blockers"]  # DCF does not use the historical payout ratio


def test_unresolved_run_publishes_independent_work_without_a_call(cfg, tmp_path):
    runner = demo_runner()
    fp = disputed()
    cfg.update(run_council=False, block_incomplete_reports=False)
    state = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=runner, factpack_loader=lambda *_: fp, out_dir=tmp_path).run()
    assert state["memos"] and state["report_status"] == "draft" and not state.get("call_id")
    assert "valuation" not in [c["agent"] for c in runner.calls]
    saved = json.loads(Path(state["paths"]["research"]).read_text())
    assert saved["final"]["rating"] is None and saved["valuation"]["target_price"] is None
    html = Path(state["paths"]["report"]).read_text()
    assert "Rating and target price pending" in html and "2117.71" in html


def test_desk_identified_conflict_blocks_call_without_council(cfg, tmp_path):
    from aladeen.demo import demo_responder
    from aladeen.firm.schemas import DeskReviewSet
    from aladeen.llm import OfflineRunner

    def responder(name, schema, system, user):
        response = demo_responder(name, schema, system, user)
        if schema is DeskReviewSet:
            response.unresolved_material_conflicts = ["Obtain the exchange order to verify the suspension date."]
        return response

    cfg.update(run_council=False, block_incomplete_reports=False)
    state = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=OfflineRunner(responder),
                        factpack_loader=lambda *args: synthetic_factpack(), out_dir=tmp_path).run()
    assert state["final"]["rating"] is None and "exchange order" in state["draft_reason"]


def test_conflicting_official_copies_are_not_resolved_by_vendor_consensus(cfg):
    fp = disputed()
    fp.screener["website"] = "https://www.issuer.example"
    fp.yahoo.setdefault("info", {})["website"] = "https://issuer.example"
    fp.documents = [filing(), {**filing(PAGE.replace("215,000", "230,200")),
                               "url": "https://ir.issuer.example/annual-report.pdf"}]
    q = compute_quant(fp, cfg, with_charts=False)
    r = q["valuation_blockers"][0]
    assert r["value"] is None and len(r["evidence"]) == 2
