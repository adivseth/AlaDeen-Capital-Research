"""Residual-income bank valuation, cost of equity, reality check, roll-forward and related plumbing."""

import pytest

from aladeen.calllog import store as calllog
from aladeen.dataflows import documents as docs
from aladeen.dataflows.news import queries, short_name
from aladeen.demo import synthetic_factpack
from aladeen.quant import valuation as v
from aladeen.quant.engine import compute_quant, value_company


def _bank(**kw):
    base = dict(bv0_cr=100.0, bv_date="Sep 2026", roe_path=[0.15, 0.15], terminal_roe=0.15, payout=0.5,
                terminal_growth=0.05)
    base.update(kw)
    return v.BankInputs(**base)


def test_residual_income_hand_check():
    out = v.residual_income(_bank(), ke=0.12, shares_cr=1.0)
    ri1 = (0.15 - 0.12) * 100
    bv1 = 100 + 15 * 0.5
    ri2 = (0.15 - 0.12) * bv1
    bv2 = bv1 + 0.15 * bv1 * 0.5
    tv = (0.15 - 0.12) * bv2 / (0.12 - 0.05)
    expected = 100 + ri1 / 1.12 + ri2 / 1.12 ** 2 + tv / 1.12 ** 2
    assert out["per_share"] == pytest.approx(expected)
    assert out["bv_end"] == pytest.approx(bv2)
    assert out["dps_year1"] == pytest.approx(7.5)


def test_roe_equal_to_ke_is_worth_book():
    out = v.residual_income(_bank(roe_path=[0.12] * 10, terminal_roe=0.12), ke=0.12, shares_cr=2.0)
    assert out["per_share"] == pytest.approx(50.0)
    assert out["implied_pb"] == pytest.approx(1.0)


def test_implied_roe_round_trip():
    inp = _bank(roe_path=[0.17] * 10, terminal_roe=0.17)
    price = v.residual_income(inp, 0.115, 1.0)["per_share"]
    assert v.implied_roe(price, inp, 0.115, 1.0) == pytest.approx(0.17, abs=1e-6)


def test_default_roe_path_fades_then_holds():
    path = v.default_roe_path(0.11, 0.14, years=10, fade=5)
    assert path[0] == pytest.approx(0.116) and path[4] == pytest.approx(0.14) and path[-1] == pytest.approx(0.14)


def test_cost_of_equity_nets_default_spread():
    cap = v.CapitalInputs(risk_free=0.0722, beta=0.83, erp=0.0708, cost_of_debt_pre_tax=0.08, tax_rate=0.25,
                          debt_to_capital=0.0, default_spread=0.0187)
    assert cap.riskless_rate == pytest.approx(0.0535)
    assert cap.cost_of_equity == pytest.approx(0.0535 + 0.83 * 0.0708)


def test_peers_exclude_self_by_url_and_size():
    peers = [{"Company": "Kotak Mah. Bank", "url": "/company/KOTAKBANK/consolidated/", "P/E": 23,
              "Mar Cap Rs.Cr.": 490000},
             {"Company": "Big Bank", "url": "/company/BIG/", "P/E": 16, "Mar Cap Rs.Cr.": 1200000},
             {"Company": "Mid Bank", "url": "/company/MID/", "P/E": 14, "Mar Cap Rs.Cr.": 420000},
             {"Company": "Tiny Bank", "url": "/company/TINY/", "P/E": 10, "Mar Cap Rs.Cr.": 80000}]
    pm = v.peer_multiples(peers, ["Kotak Mahindra Bank Ltd", "KOTAKBANK"], market_cap_cr=490000)
    assert pm["peers_used"] == ["Big Bank", "Mid Bank"] and pm["peer_pe_median"] == 15
    assert pm["peers_dropped_for_size"] == ["Tiny Bank"]


def test_reality_check_flags_far_target_without_consensus(cfg):
    res = v.ValuationResult(method="residual_income", cmp=500.0, shares_cr=1.0,
                            capital={"cost_of_equity": 0.115}, target_price=300.0)
    rc = v.reality_check(res, cfg)
    assert rc["flag"] and "explain" in rc["message"]
    near = v.reality_check(res, cfg, {"target_mean": 320.0, "analysts": 30})
    assert not near["flag"]  # far from the price but close to the consensus: no flag


def _bank_factpack():
    """The demo company re-labelled as a lender: Screener's bank layout and a half-year balance sheet."""
    fp = synthetic_factpack()
    t = fp.screener["tables"]
    pl = t["profit_loss"]["rows"]
    pl["Revenue"] = pl.pop("Sales")
    pl["Financing Profit"] = pl.pop("Operating Profit")
    bs = t["balance_sheet"]
    bs["columns"] = bs["columns"] + ["Sep 2026"]
    for vals in bs["rows"].values():
        vals.append(round(vals[-1] * 1.05))
    t["ratios"]["rows"]["ROE %"] = [14.0] * len(t["ratios"]["columns"])
    q = t["quarters"]["rows"]
    q["Revenue"] = q.pop("Sales")
    q["Financing Profit"] = q.pop("Operating Profit")
    fp.company["classification"] = {"Sector": "Financial Services", "Industry": "Private Sector Bank"}
    return fp


def test_bank_engine_end_to_end(cfg):
    q = compute_quant(_bank_factpack(), cfg, with_charts=False)
    assert q["is_financial"] and q["book"]["date"] == "Sep 2026"
    res = value_company(q, cfg)
    assert res.method == "residual_income" and res.dcf is None
    ri = res.residual_income
    assert ri["bv0"] == pytest.approx(q["book"]["net_worth_cr"])
    assert res.scenarios["bear"]["value"] < res.scenarios["base"]["value"] < res.scenarios["bull"]["value"]
    ke = res.capital["cost_of_equity"]
    dps = res.inputs["roll_forward"]["dps_year1"]
    for s in res.scenarios.values():  # 12-month value = value today rolled forward at Ke, less the dividend
        assert s["value"] == pytest.approx(s["value_today"] * (1 + ke) - dps)
    assert res.implied_roe_at_cmp is not None
    assert res.multiples["pb_anchor"] is not None and len(res.multiples["pb_history"]) <= 5
    # the analyst's ROE path and sustainable ROE drive the model
    hi = value_company(q, cfg, {"roe_path": [0.2] * 3, "sustainable_roe": 0.2})
    assert hi.residual_income["projections"][0]["roe"] == pytest.approx(0.2)
    assert hi.residual_income["per_share"] > ri["per_share"]


def test_roll_forward_can_be_switched_off(cfg):
    cfg["roll_forward_target"] = False
    res = value_company(compute_quant(synthetic_factpack(), cfg, with_charts=False), cfg)
    assert res.target_price == pytest.approx(res.value_today)


def test_call_ids_continue_from_floor_and_shared_sheet(tmp_path):
    class Sheet:
        def read(self):
            return [dict.fromkeys(calllog.COLUMNS, "") | {"call_id": "AC-024", "ticker": "KOTAKBANK.NS"}]

        def describe(self):
            return "stub sheet"

    st = calllog.CSVStore(tmp_path / "log.csv", mirror=Sheet())
    row = st.append({"company": "X", "ticker": "X.NS"})
    assert row["call_id"] == "AC-025" and "shared sheet" in row["notes"]
    assert [r["call_id"] for r in st.read()] == ["AC-024", "AC-025"]
    assert calllog.next_call_id([], floor=24) == "AC-025"

    class Broken(Sheet):
        def read(self):
            raise RuntimeError("HTTP 401")

    st2 = calllog.CSVStore(tmp_path / "log2.csv", id_floor=30, mirror=Broken())
    assert st2.append({"company": "Y"})["call_id"] == "AC-031"


def test_document_labels_and_latest_call_gap():
    url = "https://x/FY-2027/q1/transcript/Q1FY27-Transcript.pdf"
    assert docs.quarter_label(url) == "Q1 FY27"
    gap = docs.latest_call_gap({"concalls": [{"period": "Oct 2026", "ppt": "p.pdf",
                                              "recording": "https://x/FY-2027/q2/rec"}]})
    assert gap and "Oct 2026" in gap
    assert docs.latest_call_gap({"concalls": [{"period": "Aug 2026", "transcript": url}]}) is None


def test_news_queries_drop_legal_suffix():
    assert short_name("Kotak Mahindra Bank Ltd") == "Kotak Mahindra Bank"
    assert queries("Kotak Mahindra Bank Ltd", "KOTAKBANK")[0] == '"Kotak Mahindra Bank"'
