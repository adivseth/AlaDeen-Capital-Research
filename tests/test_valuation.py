import pytest

from aladeen.demo import synthetic_factpack
from aladeen.quant import valuation as v
from aladeen.quant.engine import compute_quant, value_company


def _inputs(**kw):
    base = dict(base_revenue=1000.0, revenue_growth=[0.1] * 5, ebit_margin=[0.2] * 5, tax_rate=0.25,
                da_pct_revenue=0.03, capex_pct_revenue=0.04, nwc_pct_incremental_revenue=0.1,
                terminal_growth=0.05, stable_roc=0.15)
    base.update(kw)
    return v.DCFInputs(**base)


def test_dcf_hand_check():
    inp = _inputs()
    out = v.dcf_fcff(inp, wacc=0.12, net_debt=0.0, minority=0.0, shares_cr=10.0)
    rev1 = 1100.0
    fcff1 = rev1 * 0.2 * 0.75 + rev1 * 0.03 - rev1 * 0.04 - 100 * 0.1
    assert out["projections"][0]["fcff"] == pytest.approx(fcff1)
    nopat5 = 1000 * 1.1 ** 5 * 0.2 * 0.75
    tv = nopat5 * 1.05 * (1 - 0.05 / 0.15) / (0.12 - 0.05)
    assert out["terminal_value"] == pytest.approx(tv)
    assert out["per_share"] == pytest.approx(out["enterprise_value"] / 10)


def test_wacc_and_guards():
    cap = v.CapitalInputs(risk_free=0.07, beta=1.0, erp=0.07, cost_of_debt_pre_tax=0.09, tax_rate=0.25,
                          debt_to_capital=0.2)
    assert cap.cost_of_equity == pytest.approx(0.14)
    assert cap.wacc == pytest.approx(0.14 * 0.8 + 0.09 * 0.75 * 0.2)
    with pytest.raises(ValueError):
        v.dcf_fcff(_inputs(terminal_growth=0.13), 0.12, 0, 0, 10)


def test_justified_pb_and_graham():
    jp = v.justified_pb(bvps=100, roe=0.18, growth=0.06, cost_of_equity=0.14)
    assert jp["justified_pb"] == pytest.approx(1.5)
    assert v.graham_number(10, 100) == pytest.approx((22.5 * 1000) ** 0.5)
    assert v.graham_formula(10, 5, 4.4) == pytest.approx(10 * 18.5)


def test_rating_bands():
    bands = {"buy": 0.15, "sell": 0.0}
    assert v.rating_from_return(0.2, bands) == "BUY"
    assert v.rating_from_return(0.05, bands) == "HOLD"
    assert v.rating_from_return(-0.01, bands) == "SELL"


def test_peer_multiples_excludes_self_and_median():
    peers = [{"Company": "Demo Industries", "P/E": 10}, {"Company": "A", "P/E": 20},
             {"Company": "B", "P/E": 30}, {"Company": "Median: 5 Co.", "P/E": 99}]
    pm = v.peer_multiples(peers, ["Demo Industries Ltd", "DEMO"])
    assert pm["peer_pe_median"] == 25 and pm["peer_count"] == 2


def test_engine_end_to_end(cfg):
    q = compute_quant(synthetic_factpack(), cfg, with_charts=False)
    res = value_company(q, cfg)
    probs = sum(s["probability"] for s in res.scenarios.values())
    assert probs == pytest.approx(1.0)
    assert res.scenarios["bear"]["value"] < res.scenarios["base"]["value"] < res.scenarios["bull"]["value"]
    assert res.target_price == pytest.approx(sum(s["value"] * s["probability"] for s in res.scenarios.values()))
    assert res.band_rating == v.rating_from_return(res.total_return, cfg["rating_bands"])
    assert len(res.sensitivity["values"]) == 5


def test_terminal_growth_cap(cfg):
    q = compute_quant(synthetic_factpack(), cfg, with_charts=False)
    res = value_company(q, cfg, {"terminal_growth": 0.09})
    assert res.inputs["dcf"]["terminal_growth"] == cfg["terminal_growth_cap"]
    assert any("capped" in w for w in res.warnings)
