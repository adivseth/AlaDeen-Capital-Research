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
    beta_used = beta_raw
    if beta_raw is None:
        beta_used = 1.0
        notes.append("Beta unavailable: 1.0 used.")
    else:
        if cfg.get("blume_adjust_beta", True):  # Blume: 0.67 x raw + 0.33 x 1.0 (mean reversion)
            beta_used = 0.67 * beta_raw + 0.33
        beta_used = min(max(beta_used, 0.5), 2.0)
        if abs(beta_used - beta_raw) > 1e-9:
            notes.append(f"Regression beta {beta_raw:.2f} adjusted to {beta_used:.2f}"
                         f"{' (Blume)' if cfg.get('blume_adjust_beta', True) else ''}"
                         f"{', bounded to 0.5-2.0' if beta_used in (0.5, 2.0) else ''}.")

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
    fp.resolve_facts()
    st = statements.build_statements(fp)
    tech = technicals.summarize(fp.prices, fp.benchmark_prices)
    q: dict[str, Any] = {
        "statements": st,
        "valuation_blockers": [f for f in fp.fact_resolutions if f["status"] == "unresolved"
                               and (f["metric"] != "Dividend Payout %" or st["is_financial"])],
        "growth": statements.growth_table(st["annual"]) if not st["annual"].empty else {},
        "reconciliation": statements.reconcile(fp, st),
        "technicals": tech,
        "short_term": technicals.short_term_check(fp.prices, fp.benchmark_prices),
    }
    mk = market_snapshot(fp, st, tech, cfg)
    q["market"] = mk
    q["peers"] = val.peer_multiples(fp.peers, [fp.name, fp.ticker, fp.company.get("nse_symbol") or ""],
                                    market_cap_cr=mk.get("market_cap_cr"))
    annual = st["annual"]
    q["eps_ttm"] = st["ttm"].get("EPS") or _last(annual.get("EPS"))
    q["is_financial"] = st["is_financial"]
    q["book"] = book_value(st, mk)
    q["bvps"] = q["book"]["bvps"]
    if q["is_financial"]:
        q["bank"] = bank_defaults(st, q["book"], cfg)
        q["bank"]["pb_history"] = val.historical_pb(fp.prices, annual.get("BVPS"))
    q["consensus"] = consensus(fp)
    if not q["valuation_blockers"] and "Revenue" in annual and annual["Revenue"].notna().any() and not st["is_financial"]:
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


def book_value(st: dict, mk: dict) -> dict:
    """Net worth and book value per share at the latest balance-sheet date (half-year if available)."""
    annual = st["annual"]
    interim = st.get("bs_latest_interim")
    nw, date_ = None, None
    if interim is not None and "Equity Capital" in interim and "Reserves" in interim:
        e, r = interim.get("Equity Capital"), interim.get("Reserves")
        if pd.notna(e) and pd.notna(r):
            nw, date_ = float(e + r), str(interim.name)
    if nw is None and "Net Worth" in annual and annual["Net Worth"].notna().any():
        s = annual["Net Worth"].dropna()
        nw, date_ = float(s.iloc[-1]), str(s.index[-1])
    shares = mk.get("shares_cr")
    bvps = nw / shares if nw and shares else (mk.get("book_value_screener") or _last(annual.get("BVPS")))
    return {"net_worth_cr": nw, "date": date_, "bvps": bvps, "screener_bvps": mk.get("book_value_screener")}


def bank_defaults(st: dict, book: dict, cfg: dict) -> dict:
    """History-based starting assumptions for the residual-income model."""
    annual = st["annual"]
    roe_hist = annual.get("ROE %")
    hist = roe_hist.dropna() / 100 if roe_hist is not None else pd.Series(dtype=float)
    ttm_pat = st["ttm"].get("PAT")
    nw0 = book.get("net_worth_cr")
    nw_prev = _last(annual.get("Net Worth"))
    roe_ttm = None
    if ttm_pat and nw0:
        avg = (nw0 + nw_prev) / 2 if nw_prev else nw0
        roe_ttm = ttm_pat / avg
    normalised = float(hist.tail(5).median()) if len(hist) else roe_ttm
    roe_now = roe_ttm if roe_ttm is not None else normalised
    pay = annual.get("Dividend Payout %")
    payout = float(pay.dropna().tail(3).mean() / 100) if pay is not None and pay.notna().any() else 0.2
    return {
        "roe_ttm": roe_ttm, "roe_5y_median": normalised, "roe_history": {k: float(v) for k, v in hist.items()},
        "payout_3y": payout,
        "default_roe_path": val.default_roe_path(roe_now, normalised) if roe_now is not None else None,
        "default_terminal_roe": normalised, "default_terminal_growth": cfg["terminal_growth_cap"],
    }


def consensus(fp: FactPack) -> dict:
    info = fp.yahoo.get("info", {})
    t = info.get("targetMeanPrice")
    return {"target_mean": t, "target_high": info.get("targetHighPrice"), "target_low": info.get("targetLowPrice"),
            "analysts": info.get("numberOfAnalystOpinions"), "source": "Yahoo Finance" if t else None}


def capital_inputs(q: dict, cfg: dict, beta_override: float | None = None,
                   kd_override: float | None = None,
                   dv_override: float | None = None, premium: float = 0.0) -> val.CapitalInputs:
    mk = q["market"]
    return val.CapitalInputs(
        risk_free=cfg["risk_free_rate"],
        beta=beta_override if beta_override is not None else mk["beta"],
        erp=cfg["equity_risk_premium"],
        cost_of_debt_pre_tax=kd_override if kd_override is not None else mk["cost_of_debt_pre_tax"],
        tax_rate=cfg["tax_rate"],
        debt_to_capital=dv_override if dv_override is not None else mk["debt_to_capital"],
        default_spread=cfg.get("country_default_spread", 0.0),
        premium=premium,
    )


def value_company(q: dict, cfg: dict, assumptions: dict | None = None) -> val.ValuationResult:
    """Run the valuation with the analyst's assumptions (or history-based defaults)."""
    if q.get("valuation_blockers"):
        raise ValueError("Valuation pending reconciliation to filed accounts")
    a = {k: v for k, v in (assumptions or {}).items() if v is not None}
    mk = q["market"]
    cap = capital_inputs(q, cfg, a.get("beta"), a.get("cost_of_debt_pre_tax"), a.get("debt_to_capital"),
                         a.get("cost_of_equity_premium") or 0.0)
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
    bank_inputs = bank_inputs_from(q, cfg, a) if q["is_financial"] else None
    res = val.run_valuation(
        cmp_=mk["cmp"], shares_cr=mk["shares_cr"], capital=cap, cfg=cfg, dcf_inputs=dcf_inputs,
        net_debt=mk["net_debt_cr"], minority=mk["minority_cr"], eps_ttm=q["eps_ttm"], bvps=q["bvps"],
        peers=q["peers"], financial=q["is_financial"], bank_inputs=bank_inputs,
        pb_anchor=(q.get("bank") or {}).get("pb_history"),
        dividend_yield=mk["dividend_yield"], shifts=shifts, consensus=q.get("consensus"),
        graham_inputs={"growth_pct": q["graham_growth_pct"], "ncav_per_share": mk["ncav_per_share"],
                       "checklist": q["graham_checklist"]},
    )
    res.warnings.extend(mk["notes"])
    return res


def bank_inputs_from(q: dict, cfg: dict, a: dict) -> val.BankInputs | None:
    """Analyst assumptions over history-based defaults. ``sustainable_roe`` is the terminal ROE."""
    b, book = q.get("bank") or {}, q.get("book") or {}
    if not book.get("net_worth_cr"):
        return None
    term = a.get("terminal_roe", a.get("sustainable_roe", b.get("default_terminal_roe")))
    if term is None:
        return None
    path = a.get("roe_path")
    if path:
        path = [float(x) for x in path][:10]
        path += [term] * (10 - len(path)) if len(path) < 10 else []
    else:
        now = b.get("roe_ttm") if b.get("roe_ttm") is not None else term
        path = val.default_roe_path(now, term)
    return val.BankInputs(
        bv0_cr=book["net_worth_cr"], bv_date=book.get("date") or "", roe_path=path, terminal_roe=float(term),
        payout=float(a.get("payout_ratio", b.get("payout_3y", 0.2))),
        terminal_growth=float(a.get("long_term_growth", b.get("default_terminal_growth", cfg["terminal_growth_cap"]))),
    )
