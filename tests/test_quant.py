import numpy as np
import pandas as pd

from aladeen.demo import synthetic_factpack
from aladeen.quant import audit, technicals
from aladeen.quant.statements import build_statements, cagr, fy_label, reconcile


def test_fy_label():
    assert fy_label("Mar 2026") == "FY26"
    assert fy_label("Dec 2020") == "Dec 2020"


def test_cagr():
    s = pd.Series([100.0, 110.0, 121.0])
    assert abs(cagr(s, 2) - 0.10) < 1e-9
    assert cagr(pd.Series([-1.0, 2.0]), 1) is None


def test_statements_and_reconciliation():
    fp = synthetic_factpack()
    st = build_statements(fp)
    a = st["annual"]
    assert {"Revenue", "EBITDA", "PAT", "ROE %", "CFO", "FCF", "Capex"} <= set(a.columns)
    assert st["ttm"]["quarters"]
    checks = reconcile(fp, st)
    assert checks and all(c["status"] == "OK" for c in checks)


def test_reconcile_flags_mismatch():
    fp = synthetic_factpack()
    fp.screener["tables"]["balance_sheet"]["rows"]["Total Assets"][-1] += 50
    checks = reconcile(fp, build_statements(fp))
    assert any(c["status"] == "MISMATCH" and "Total liabilities" in c["check"] for c in checks)


def test_rsi_bounds_and_macd():
    s = pd.Series(np.linspace(100, 200, 300))
    r = technicals.rsi(s).dropna()
    assert (r <= 100).all() and (r >= 0).all() and r.iloc[-1] > 90  # steady rise
    m = technicals.macd(s)
    assert {"macd", "signal", "hist"} <= set(m.columns)


def test_summary_and_short_term():
    fp = synthetic_factpack()
    t = technicals.summarize(fp.prices, fp.benchmark_prices)
    assert t["available"] and "rsi14" in t["indicators"] and t["beta_2y_weekly"] is not None
    st = technicals.short_term_check(fp.prices, fp.benchmark_prices)
    assert "5d" in st and "10d" in st and "relative" in st["5d"]


def test_number_audit():
    known = audit.known_set("Revenue ₹3,479 Cr; margin 19.4%; P/E 24.0x")
    assert audit.audit_text("Revenue of ₹3,479 Cr at a 19.4% margin", known) == []
    assert audit.audit_text("Margins will reach 31.5%", known) == ["31.5%"]
    assert audit.audit_text("Over 5 years since 2019", known) == []  # counts and years ignored
    assert audit.audit_text("margin 0.194", known) == []  # decimal <-> percent
