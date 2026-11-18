"""Quant engine: turns a FactPack into verified numbers, charts and default valuation inputs."""

from __future__ import annotations

from typing import Any

import pandas as pd

from aladeen.dataflows.factpack import FactPack
from aladeen.quant import charts, statements, technicals
from aladeen.quant import valuation as val


def _last(series: pd.Series | None) -> float | None:
    if series is None or not series.notna().any():
        return None
    return float(series.dropna().iloc[-1])


def market_snapshot(fp: FactPack, st: dict, tech: dict, cfg: dict) -> dict[str, Any]:
    tr = fp.screener.get("top_ratios", {})
    info = fp.yahoo.get("info", {})
    bsy = fp.yahoo.get("balance_sheet_latest", {}).get("values", {})
    notes: list[str] = []
    cmp_ = tech.get("close") if tech.get("available") else None
    if cmp_ is None:
        cmp_ = tr.get("Current Price")
        notes.append("CMP taken from Screener (no price history).")
    shares = None
    if tr.get("Market Cap") and tr.get("Current Price"):
        shares = tr["Market Cap"] / tr["Current Price"]  # crore shares
    elif info.get("sharesOutstanding"):
        shares = info["sharesOutstanding"] / 1e7
        notes.append("Share count from Yahoo.")
    mcap = cmp_ * shares if cmp_ and shares else tr.get("Market Cap")

    annual = st["annual"]
    debt = cash = None
    if bsy.get("Total Debt") is not None:
        debt = bsy["Total Debt"] / 1e7
    elif "Borrowings" in annual:
        debt = _last(annual["Borrowings"])
        notes.append("Debt from Screener borrowings (Yahoo balance sheet unavailable).")
    for k in ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"):
        if bsy.get(k) is not None:
            cash = bsy[k] / 1e7
            break
    if cash is None:
        notes.append("Cash balance unavailable: net debt assumes zero cash (conservative).")
    net_debt = (debt or 0.0) - (cash or 0.0)
    minority = (bsy.get("Minority Interest") or 0.0) / 1e7
    ca, cl = bsy.get("Current Assets"), bsy.get("Current Liabilities")
    current_ratio = ca / cl if ca and cl else None
    tl = bsy.get("Total Liabilities Net Minority Interest")
    ncav = val.ncav_per_share(ca / 1e7 if ca else None, tl / 1e7 if tl else None, shares or 0)

    beta_raw = tech.get("beta_2y_weekly")
    beta_used = min(max(beta_raw, 0.5), 2.0) if beta_raw is not None else 1.0
    if beta_raw is None:
        notes.append("Beta unavailable: 1.0 used.")
    elif beta_used != beta_raw:
        notes.append(f"Regression beta {beta_raw:.2f} bounded to {beta_used:.2f}.")

    rf = cfg["risk_free_rate"]
    kd = rf + 0.015
    interest = _last(annual.get("Interest"))
    borrowings = annual.get("Borrowings")
    if interest and borrowings is not None and borrowings.notna().sum() >= 2:
        avg_b = float(borrowings.dropna().tail(2).mean())
        if avg_b > 1:
            kd = min(max(interest / avg_b, rf), rf + 0.06)
    d_v = (debt / (debt + mcap)) if debt and mcap else 0.0
    dy = tr.get("Dividend Yield")
    div_yield = dy / 100 if isinstance(dy, (int, float)) else 0.0
    hl = tr.get("High / Low") or [None, None]
    return {
        "cmp": cmp_, "shares_cr": shares, "market_cap_cr": mcap, "debt_cr": debt, "cash_cr": cash,
        "net_debt_cr": net_debt, "minority_cr": minority, "current_ratio": current_ratio,
        "ncav_per_share": ncav, "beta_raw": beta_raw, "beta": beta_used,
        "cost_of_debt_pre_tax": kd, "debt_to_capital": d_v, "dividend_yield": div_yield,
        "pe_screener": tr.get("Stock P/E"), "book_value_screener": tr.get("Book Value"),
        "roe_screener": tr.get("ROE"), "roce_screener": tr.get("ROCE"),
        "face_value": tr.get("Face Value"),
        "high_52w": tech.get("high_52w") or (hl[0] if isinstance(hl, list) else None),
        "low_52w": tech.get("low_52w") or (hl[-1] if isinstance(hl, list) else None),
        "avg_volume_3m": tech.get("avg_volume_3m") or info.get("averageVolume"),
        "notes": notes,
    }


def compute_quant(fp: FactPack, cfg: dict, with_charts: bool = True) -> dict[str, Any]:
    st = statements.build_statements(fp)
    tech = technicals.summarize(fp.prices, fp.benchmark_prices)
    q: dict[str, Any] = {
        "statements": st,
        "growth": statements.growth_table(st["annual"]) if not st["annual"].empty else {},
        "reconciliation": statements.reconcile(fp, st),
        "technicals": tech,
        "short_term": technicals.short_term_check(fp.prices, fp.benchmark_prices),
    }
    mk = market_snapshot(fp, st, tech, cfg)
    q["market"] = mk
    q["peers"] = val.peer_multiples(fp.peers, [fp.name, fp.ticker, fp.company.get("nse_symbol") or ""])
    annual = st["annual"]
    q["eps_ttm"] = st["ttm"].get("EPS") or _last(annual.get("EPS"))
    q["bvps"] = mk.get("book_value_screener") or _last(annual.get("BVPS"))
    q["is_financial"] = st["is_financial"]
    if not annual.empty and "Revenue" in annual and not st["is_financial"]:
        q["default_dcf_inputs"] = val.default_dcf_inputs(annual, cfg)
    roe_hist = annual.get("ROE %")
    q["roe_3y_avg"] = (float(roe_hist.dropna().tail(3).mean() / 100)
                       if roe_hist is not None and roe_hist.notna().any() else None)
    eps_g = q["growth"].get("EPS", {}).get("5Y")
    q["graham_growth_pct"] = round(min(max(eps_g or 0.0, 0.0), 0.15) * 100, 2)
    q["graham_checklist"] = (val.graham_checklist(annual, mk["cmp"], mk["current_ratio"])
                             if mk["cmp"] and not annual.empty else [])
    q["charts"] = {}
    if with_charts:
        q["charts"] = {
            "technical": charts.technical_chart(fp.prices, f"{fp.name} — 10-year price with indicators"),
            "relative": charts.relative_chart(fp.prices, fp.benchmark_prices, fp.ticker,
                                              "Nifty 50" if fp.benchmark == "^NSEI" else fp.benchmark),
            "financials": charts.financials_chart(annual),
        }
    return q


def capital_inputs(q: dict, cfg: dict, beta_override: float | None = None,
                   kd_override: float | None = None,
                   dv_override: float | None = None) -> val.CapitalInputs:
    mk = q["market"]
    return val.CapitalInputs(
        risk_free=cfg["risk_free_rate"],
        beta=beta_override if beta_override is not None else mk["beta"],
        erp=cfg["equity_risk_premium"],
        cost_of_debt_pre_tax=kd_override if kd_override is not None else mk["cost_of_debt_pre_tax"],
        tax_rate=cfg["tax_rate"],
        debt_to_capital=dv_override if dv_override is not None else mk["debt_to_capital"],
    )


def value_company(q: dict, cfg: dict, assumptions: dict | None = None) -> val.ValuationResult:
    """Run the valuation with the analyst's assumptions (or history-based defaults)."""
    a = {k: v for k, v in (assumptions or {}).items() if v is not None}
    mk = q["market"]
    cap = capital_inputs(q, cfg, a.get("beta"), a.get("cost_of_debt_pre_tax"), a.get("debt_to_capital"))
    shifts = None
    if a.get("scenarios"):
        shifts = {k: val.ScenarioShift(**v) for k, v in a["scenarios"].items()}
        shifts.setdefault("base", val.ScenarioShift())
    dcf_inputs = None
    if not q["is_financial"]:
        d = q["default_dcf_inputs"]
        fields = {k: a[k] for k in ("revenue_growth", "ebit_margin", "da_pct_revenue",
                                    "capex_pct_revenue", "nwc_pct_incremental_revenue",
                                    "terminal_growth", "stable_roc") if k in a}
        dcf_inputs = val.DCFInputs(**{**d.__dict__, **fields})
    roe = a.get("sustainable_roe", q.get("roe_3y_avg"))
    res = val.run_valuation(
        cmp_=mk["cmp"], shares_cr=mk["shares_cr"], capital=cap, cfg=cfg, dcf_inputs=dcf_inputs,
        net_debt=mk["net_debt_cr"], minority=mk["minority_cr"], eps_ttm=q["eps_ttm"], bvps=q["bvps"],
        peers=q["peers"], financial=q["is_financial"], roe=roe, bank_growth=a.get("long_term_growth"),
        dividend_yield=mk["dividend_yield"], shifts=shifts,
        graham_inputs={"growth_pct": q["graham_growth_pct"], "ncav_per_share": mk["ncav_per_share"],
                       "checklist": q["graham_checklist"]},
    )
    res.warnings.extend(mk["notes"])
    return res
