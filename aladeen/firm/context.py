"""Markdown renderings of the fact pack and quant results, sized for each agent."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import pandas as pd

from aladeen.dataflows.factpack import FactPack


def fmt(v: Any, kind: str = "num", nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if kind == "pct":  # decimal -> %
        return f"{v * 100:.{nd}f}%"
    if kind == "pctv":  # already in %
        return f"{v:.{nd}f}%"
    if kind == "inr":
        return f"₹{v:,.{nd}f}"
    if kind == "cr":
        return f"₹{v:,.0f} Cr"
    if kind == "x":
        return f"{v:.{nd}f}x"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def df_md(df: pd.DataFrame, nd: int = 1) -> str:
    if df is None or df.empty:
        return "_not available_"
    cols = [str(c) for c in df.columns]
    lines = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for idx, row in df.iterrows():
        cells = []
        for v in row:
            if v is None or (isinstance(v, float) and math.isnan(v)):
                cells.append("n/a")
            elif isinstance(v, (int, float)):
                cells.append(f"{v:,.{nd}f}")
            else:
                cells.append(str(v))
        lines.append(f"| {idx} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- sections
def company_md(fp: FactPack) -> str:
    c = fp.company
    cls = c.get("classification", {})
    lines = [
        f"# {fp.name} ({fp.exchange}: {fp.ticker})",
        f"Analysis date: {fp.as_of}. Benchmark: {fp.benchmark}.",
        f"Classification: {' > '.join(str(v) for v in cls.values() if v)}",
        f"Index membership: {', '.join(c.get('indices', [])[:12]) or 'n/a'}",
        f"Website: {c.get('website') or 'n/a'}",
        "",
        f"About: {c.get('about') or 'n/a'}",
    ]
    if c.get("pros") or c.get("cons"):
        lines += ["", "Screener auto-generated pros: " + "; ".join(c.get("pros", [])),
                  "Screener auto-generated cons: " + "; ".join(c.get("cons", []))]
    return "\n".join(lines)


def market_md(q: dict) -> str:
    m = q["market"]
    t = q["technicals"]
    ttm = q["statements"]["ttm"]
    return "\n".join([
        "## Market snapshot",
        f"- CMP: {fmt(m['cmp'], 'inr')} | Market cap: {fmt(m['market_cap_cr'], 'cr')} | "
        f"Shares: {fmt(m['shares_cr'], nd=2)} Cr",
        f"- 52-week high / low: {fmt(m['high_52w'], 'inr')} / {fmt(m['low_52w'], 'inr')}",
        f"- Screener P/E: {fmt(m['pe_screener'], 'x')} | Book value/share: {fmt(m['book_value_screener'], 'inr')} | "
        f"ROE: {fmt(m['roe_screener'], 'pctv')} | ROCE: {fmt(m['roce_screener'], 'pctv')}",
        f"- Dividend yield: {fmt(m['dividend_yield'], 'pct', 2)} | Face value: {fmt(m['face_value'], 'inr', 0)}",
        f"- Debt: {fmt(m['debt_cr'], 'cr')} | Cash & ST investments: {fmt(m['cash_cr'], 'cr')} | "
        f"Net debt: {fmt(m['net_debt_cr'], 'cr')} | Minority interest: {fmt(m['minority_cr'], 'cr')}",
        f"- Current ratio: {fmt(m['current_ratio'], nd=2)} | NCAV/share: {fmt(m['ncav_per_share'], 'inr')}",
        f"- Beta (2Y weekly vs benchmark): {fmt(m['beta_raw'], nd=2)} (used: {fmt(m['beta'], nd=2)})",
        f"- TTM EPS: {fmt(q.get('eps_ttm'), 'inr', 2)} | TTM PAT: {fmt(ttm.get('PAT'), 'cr')} "
        f"| TTM revenue: {fmt(ttm.get('Revenue'), 'cr')}",
        f"- 1Y return: {fmt(t.get('returns', {}).get('1Y'), 'pct')} vs benchmark "
        f"{fmt(t.get('benchmark_returns', {}).get('1Y'), 'pct')}",
    ])


ANNUAL_ROWS = ["Revenue", "Revenue growth %", "EBITDA", "EBITDA margin %", "D&A", "EBIT", "Interest",
               "Other Income", "PBT", "Tax %", "PAT", "PAT margin %", "EPS", "EPS growth %",
               "Dividend Payout %", "Net Worth", "Borrowings", "Debt/Equity", "ROE %", "ROCE %",
               "ROCE % (Screener)", "CFO", "Capex", "FCF", "CFO/PAT", "Debtor Days", "Inventory Days",
               "Days Payable", "Cash Conversion Cycle", "Interest Coverage", "BVPS"]


def financials_md(q: dict, years: int = 10) -> str:
    st = q["statements"]
    a = st["annual"]
    rows = [r for r in ANNUAL_ROWS if r in a.columns]
    out = ["## Annual financials (₹ Cr unless stated; source Screener.in, derived ratios computed in code)",
           df_md(a[rows].tail(years).T) if rows else "_not available_"]
    qd = st["quarterly"]
    if not qd.empty:
        out += ["", "## Last 8 quarters (₹ Cr)", df_md(qd.tail(8).T)]
    ttm = st["ttm"]
    if ttm:
        out += ["", f"TTM ({', '.join(ttm.get('quarters', []))}): revenue {fmt(ttm.get('Revenue'), 'cr')}, "
                f"EBITDA {fmt(ttm.get('EBITDA'), 'cr')}, PAT {fmt(ttm.get('PAT'), 'cr')}, "
                f"EPS {fmt(ttm.get('EPS'), 'inr', 2)}"]
    g = q.get("growth", {})
    if g:
        out += ["", "## Compound annual growth (computed)"]
        for k, v in g.items():
            out.append(f"- {k}: " + ", ".join(f"{p} {fmt(x, 'pct')}" for p, x in v.items()))
    return "\n".join(out)


def reconciliation_md(q: dict) -> str:
    rec = q.get("reconciliation", [])
    if not rec:
        return "## Reconciliation checks\n_none run_"
    bad = [r for r in rec if r["status"] != "OK"]
    lines = [f"## Reconciliation checks: {len(rec) - len(bad)}/{len(rec)} passed"]
    for r in bad:
        lines.append(f"- MISMATCH {r['check']} ({r['period']}): expected {r['expected']:,}, "
                     f"reported {r['actual']:,}, difference {r['difference']:,}")
    return "\n".join(lines)


def shareholding_md(fp: FactPack) -> str:
    sh = fp.table("shareholding")
    if not sh.get("rows"):
        return "## Shareholding\n_not available_"
    df = pd.DataFrame({k: v[: len(sh["columns"])] for k, v in sh["rows"].items()}, index=sh["columns"]).T
    return "## Shareholding pattern (% of equity, quarterly; source Screener.in)\n" + df_md(
        df.iloc[:, -8:], nd=2)


def peers_md(fp: FactPack, q: dict) -> str:
    if not fp.peers:
        return "## Peers\n_not available_"
    cols = [c for c in ["CMP Rs.", "P/E", "Mar Cap Rs.Cr.", "Div Yld %", "Qtr Sales Var %",
                        "Qtr Profit Var %", "ROCE %"] if c in fp.peers[0]]
    df = pd.DataFrame([{c: p.get(c) for c in cols} for p in fp.peers],
                      index=[p["Company"] for p in fp.peers])
    pm = q["peers"]
    return ("## Peer comparison (source Screener.in)\n" + df_md(df, 2) +
            f"\n\nPeer median P/E (excluding the company): {fmt(pm.get('peer_pe_median'), 'x')} "
            f"from {pm.get('peer_count')} peers.")


def technicals_md(q: dict) -> str:
    t = q["technicals"]
    if not t.get("available"):
        return "## Technicals\n_price history not available_"
    ind = t["indicators"]
    lines = [f"## Technicals (daily bars {t['start']} to {t['as_of']}, {t['observations']} sessions)",
             f"- Close {fmt(t['close'], 'inr')}; 52w high {fmt(t['high_52w'], 'inr')}, "
             f"low {fmt(t['low_52w'], 'inr')}",
             "- " + "; ".join(f"{k.upper()} {v:,.2f}" for k, v in ind.items()),
             "- Signals: " + "; ".join(t.get("signals", [])),
             "- Returns (CAGR beyond 1Y): " + ", ".join(f"{k} {fmt(v, 'pct')}" for k, v in t["returns"].items())]
    if t.get("benchmark_returns"):
        lines.append("- Benchmark returns: " + ", ".join(
            f"{k} {fmt(v, 'pct')}" for k, v in t["benchmark_returns"].items()))
    dd = t.get("max_drawdown_10y")
    if dd:
        lines.append(f"- Max drawdown: {fmt(dd[0], 'pct')} (peak {dd[1]}, trough {dd[2]})")
    lines.append(f"- 1Y annualised volatility: {fmt(t.get('volatility_1y'), 'pct')}; "
                 f"beta {fmt(t.get('beta_2y_weekly'), nd=2)}")
    if t.get("crosses"):
        lines.append("- 50/200-DMA crosses: " + ", ".join(f"{c['type']} {c['date']}" for c in t["crosses"]))
    return "\n".join(lines)


def short_term_md(q: dict, fp: FactPack) -> str:
    s = q.get("short_term", {})
    lines = ["## Short-term check (last 5-10 trading days)"]
    for k in ("5d", "10d"):
        if k in s:
            r = s[k]
            lines.append(f"- {k} ({r['from']} to {r['to']}): stock {fmt(r['stock'], 'pct')}, "
                         f"benchmark {fmt(r.get('benchmark'), 'pct')}, relative {fmt(r.get('relative'), 'pct')}")
    if s.get("volume_10d_vs_3m") is not None:
        lines.append(f"- 10-day average volume vs 3-month average: {s['volume_10d_vs_3m']:.2f}x")
    try:
        start = date.fromisoformat(s.get("10d", {}).get("from", fp.as_of))
    except ValueError:
        start = date.fromisoformat(fp.as_of) - timedelta(days=14)
    anns = [a for a in fp.screener.get("documents", {}).get("announcements", [])
            if a.get("date") and start.isoformat() <= a["date"] <= fp.as_of]
    if anns:
        lines.append("- Exchange announcements in the window:")
        lines += [f"  - {a['date']}: {a['title']} — {a.get('summary', '')}" for a in anns]
    else:
        lines.append("- No exchange announcements in the window from the configured sources.")
    lines.append("- F&O open interest / participant data: not available from the configured sources.")
    return "\n".join(lines)


def news_md(fp: FactPack, limit: int = 30) -> str:
    lines = []
    if fp.news:
        lines.append(f"## News headlines (Google News, {min(limit, len(fp.news))} most recent)")
        lines += [f"- {n['date']} [{n.get('source', '')}] {n['title']}" for n in fp.news[:limit]]
    else:
        lines.append("## News\n_no news items retrieved_")
    anns = fp.screener.get("documents", {}).get("announcements", [])
    if anns:
        lines += ["", "## Recent exchange announcements (BSE via Screener)"]
        lines += [f"- {a.get('date')}: {a['title']} — {a.get('summary', '')}" for a in anns]
    return "\n".join(lines)


def documents_index_md(fp: FactPack) -> str:
    d = fp.screener.get("documents", {})
    lines = ["## Documents"]
    if fp.documents:
        for x in fp.documents:
            status = f"{x['pages']} pages read" if not x.get("error") else f"NOT READ ({x['error']})"
            lines.append(f"- {x['title']}: {status}")
    else:
        lines.append(f"- Annual report links available: {len(d.get('annual_reports', []))}; "
                     f"concall links: {len(d.get('concalls', []))} (not downloaded)")
    if d.get("credit_ratings"):
        lines.append("- Credit rating documents: " + "; ".join(c["title"] for c in d["credit_ratings"][:6]))
    return "\n".join(lines)


def warnings_md(fp: FactPack, extra: list[str] | None = None) -> str:
    w = list(fp.warnings) + list(extra or [])
    if not w:
        return "## Data caveats\n- none"
    return "## Data caveats\n" + "\n".join(f"- {x}" for x in w)


def valuation_md(res: dict) -> str:
    c = res["capital"]
    lines = [
        f"## Valuation (method: {res['method']}; all arithmetic in code)",
        f"- Cost of equity {fmt(c['cost_of_equity'], 'pct', 2)} = Rf {fmt(c['risk_free'], 'pct', 2)} + "
        f"beta {c['beta']:.2f} x ERP {fmt(c['erp'], 'pct', 2)}",
        f"- Cost of debt (pre-tax) {fmt(c['cost_of_debt_pre_tax'], 'pct', 2)}; tax {fmt(c['tax_rate'], 'pct', 2)}; "
        f"debt/capital {fmt(c['debt_to_capital'], 'pct', 1)}; WACC {fmt(c['wacc'], 'pct', 2)}",
    ]
    d = res.get("dcf")
    if d:
        inp = res["inputs"]["dcf"]
        lines += [
            f"- Base revenue {fmt(inp['base_revenue'], 'cr')}; growth path "
            + ", ".join(fmt(g, 'pct') for g in inp["revenue_growth"])
            + "; EBIT margin path " + ", ".join(fmt(m, 'pct') for m in inp["ebit_margin"]),
            f"- D&A {fmt(inp['da_pct_revenue'], 'pct')} of revenue; capex {fmt(inp['capex_pct_revenue'], 'pct')}; "
            f"NWC {fmt(inp['nwc_pct_incremental_revenue'], 'pct')} of incremental revenue; terminal growth "
            f"{fmt(inp['terminal_growth'], 'pct')}; stable ROC {fmt(inp['stable_roc'], 'pct')}",
            f"- PV explicit FCFF {fmt(d['pv_explicit'], 'cr')}; PV terminal {fmt(d['pv_terminal'], 'cr')} "
            f"({fmt(d['tv_share_of_ev'], 'pct', 0)} of EV); EV {fmt(d['enterprise_value'], 'cr')}; "
            f"equity {fmt(d['equity_value'], 'cr')}; DCF value/share {fmt(d['per_share'], 'inr')}",
        ]
    jp = res.get("justified_pb")
    if jp:
        lines.append(f"- Justified P/B {jp['justified_pb']:.2f}x (ROE {fmt(jp['roe'], 'pct')}, "
                     f"g {fmt(jp['growth'], 'pct')}, Ke {fmt(jp['cost_of_equity'], 'pct')}) x BVPS "
                     f"{fmt(jp['bvps'], 'inr')} = {fmt(jp['per_share'], 'inr')}")
    mu = res["multiples"]
    lines.append(f"- Peer median P/E {fmt(mu.get('peer_pe_median'), 'x')} x TTM EPS {fmt(mu.get('eps_ttm'), 'inr', 2)} "
                 f"= {fmt(mu.get('implied_price'), 'inr')}")
    lines.append("- Scenarios: " + "; ".join(
        f"{k} {fmt(v['value'], 'inr')} (p={v['probability']:.0%})" for k, v in res["scenarios"].items()))
    lines += [
        f"- Probability-weighted target {fmt(res['target_price'], 'inr')}; upside {fmt(res['upside'], 'pct')}; "
        f"dividend yield {fmt(res['dividend_yield'], 'pct', 2)}; expected total return {fmt(res['total_return'], 'pct')}",
        f"- Rating implied by bands (BUY >15%, HOLD 0-15%, SELL <0%): {res['band_rating']}",
        f"- Margin of safety at CMP vs base value: {fmt(res['margin_of_safety'], 'pct')}; entry price for 33% MoS "
        f"{fmt(res['entry_price_for_mos'], 'inr')}",
    ]
    g = res.get("graham", {})
    lines.append(f"- Graham number {fmt(g.get('graham_number'), 'inr')}; Graham formula value "
                 f"{fmt(g.get('graham_formula_value'), 'inr')} (g {g.get('graham_growth_pct')}%, "
                 f"Y {g.get('aaa_yield_pct', 0):.2f}%); NCAV/share {fmt(g.get('ncav_per_share'), 'inr')}")
    cl = g.get("checklist", [])
    if cl:
        passed = sum(1 for c_ in cl if c_["pass"])
        verdict = {True: "pass", False: "fail", None: "n/a"}
        lines.append(f"- Graham defensive checklist: {passed}/{len(cl)} passed: " + "; ".join(
            f"{c_['criterion']} = {c_['value']} ({verdict[c_['pass']]})" for c_ in cl))
    if res.get("warnings"):
        lines.append("- Valuation warnings: " + " | ".join(res["warnings"]))
    return "\n".join(lines)


def full_fact_sheet(fp: FactPack, q: dict) -> str:
    return "\n\n".join([company_md(fp), market_md(q), financials_md(q), reconciliation_md(q),
                        shareholding_md(fp), peers_md(fp, q), technicals_md(q), short_term_md(q, fp),
                        news_md(fp), documents_index_md(fp), warnings_md(fp)])
