"""Financial statements: tidy tables, derived metrics, growth and reconciliation checks.

All arithmetic happens here, in code. Agents receive the results; they never compute.
"""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

from aladeen.dataflows.factpack import FactPack


def fy_label(col: str) -> str:
    """'Mar 2016' -> 'FY16'; other year-ends keep their month ('Dec 2020')."""
    m = re.match(r"^(Mar)\s+(\d{4})$", col.strip())
    return f"FY{m.group(2)[2:]}" if m else col.strip()


def to_frame(table: dict, drop: tuple[str, ...] = ("TTM",)) -> pd.DataFrame:
    cols = table.get("columns", [])
    rows = table.get("rows", {})
    if not cols or not rows:
        return pd.DataFrame()
    data = {}
    for name, vals in rows.items():
        vals = list(vals) + [None] * (len(cols) - len(vals))
        data[name] = vals[: len(cols)]
    df = pd.DataFrame(data, index=cols).T
    keep = [c for c in df.columns if c not in drop]
    return df[keep].apply(pd.to_numeric, errors="coerce")


def _row(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def is_financial(fp: FactPack) -> bool:
    rows = fp.table("profit_loss").get("rows", {})
    if "Financing Profit" in rows or ("Revenue" in rows and "Sales" not in rows):
        return True
    cls = " ".join(str(v) for v in fp.company.get("classification", {}).values()).lower()
    return any(k in cls for k in ("bank", "finance", "nbfc", "insurance", "housing finance"))


def build_statements(fp: FactPack) -> dict[str, Any]:
    pl = to_frame(fp.table("profit_loss"))
    bs = to_frame(fp.table("balance_sheet"), drop=())
    cf = to_frame(fp.table("cash_flow"))
    rt = to_frame(fp.table("ratios"))
    qt = to_frame(fp.table("quarters"))
    # Balance sheet: keep fiscal year-end columns only (drop half-year columns like 'Sep 2026')
    bs_latest_interim = None
    if not bs.empty and not pl.empty:
        bs_interim = [c for c in bs.columns if c not in pl.columns]
        if bs_interim:
            bs_latest_interim = bs[bs_interim[-1]]
        bs = bs[[c for c in bs.columns if c in pl.columns]]

    fin = is_financial(fp)
    m = pd.DataFrame(index=pl.columns, dtype=float)
    if not pl.empty:
        sales = _row(pl, "Sales", "Revenue")
        m["Revenue"] = sales
        op = _row(pl, "Operating Profit", "Financing Profit")
        m["EBITDA"] = op
        dep = _row(pl, "Depreciation")
        m["D&A"] = dep
        if op is not None and dep is not None:
            m["EBIT"] = op - dep
        m["Other Income"] = _row(pl, "Other Income")
        m["Interest"] = _row(pl, "Interest")
        m["PBT"] = _row(pl, "Profit before tax")
        m["Tax %"] = _row(pl, "Tax %")
        m["PAT"] = _row(pl, "Net Profit")
        m["EPS"] = _row(pl, "EPS in Rs")
        m["Dividend Payout %"] = _row(pl, "Dividend Payout %")
        m["Revenue growth %"] = m["Revenue"].pct_change(fill_method=None) * 100
        m["EBITDA margin %"] = m["EBITDA"] / m["Revenue"] * 100
        m["PAT margin %"] = m["PAT"] / m["Revenue"] * 100
        m["EPS growth %"] = m["EPS"].pct_change(fill_method=None) * 100
    if not bs.empty:
        eq = _row(bs, "Equity Capital")
        res = _row(bs, "Reserves")
        nw = eq + res if eq is not None and res is not None else None
        m["Borrowings"] = _row(bs, "Borrowings", "Borrowing")
        m["Total Assets"] = _row(bs, "Total Assets")
        m["Fixed Assets"] = _row(bs, "Fixed Assets")
        m["CWIP"] = _row(bs, "CWIP")
        m["Investments"] = _row(bs, "Investments")
        if nw is not None:
            m["Net Worth"] = nw
            avg_nw = ((nw + nw.shift(1)) / 2).fillna(nw)
            m["ROE %"] = m["PAT"] / avg_nw * 100
            if not fin:
                ce = nw + m["Borrowings"].fillna(0)
                avg_ce = ((ce + ce.shift(1)) / 2).fillna(ce)
                m["ROCE %"] = (m["PBT"] + m["Interest"].fillna(0)) / avg_ce * 100
            m["Debt/Equity"] = m["Borrowings"] / nw
            shares = m["PAT"] / m["EPS"]  # crore shares
            m["BVPS"] = nw / shares
    if not cf.empty:
        m["CFO"] = _row(cf, "Cash from Operating Activity")
        m["CFI"] = _row(cf, "Cash from Investing Activity")
        m["CFF"] = _row(cf, "Cash from Financing Activity")
        m["Net Cash Flow"] = _row(cf, "Net Cash Flow")
        fcf = _row(cf, "Free Cash Flow")
        if fcf is not None:
            m["FCF"] = fcf
            m["Capex"] = m["CFO"] - fcf
        m["CFO/PAT"] = m["CFO"] / m["PAT"]
    if not rt.empty:
        for name in ["Debtor Days", "Inventory Days", "Days Payable", "Cash Conversion Cycle",
                     "Working Capital Days", "ROCE %"]:
            s = _row(rt, name)
            if s is not None:
                m[f"{name} (Screener)" if name == "ROCE %" else name] = s
    if "EBIT" in m and "Interest" in m:
        m["Interest Coverage"] = m["EBIT"] / m["Interest"].replace(0, float("nan"))
    m.index = [fy_label(c) for c in m.index]

    q = pd.DataFrame()
    if not qt.empty:
        q = pd.DataFrame(index=qt.columns)
        q["Revenue"] = _row(qt, "Sales", "Revenue")
        q["EBITDA"] = _row(qt, "Operating Profit", "Financing Profit")
        q["EBITDA margin %"] = q["EBITDA"] / q["Revenue"] * 100
        q["PAT"] = _row(qt, "Net Profit")
        q["EPS"] = _row(qt, "EPS in Rs")
        q["Revenue YoY %"] = q["Revenue"].pct_change(4, fill_method=None) * 100
        q["PAT YoY %"] = q["PAT"].pct_change(4, fill_method=None) * 100

    ttm: dict[str, Any] = {}
    if not q.empty and len(q) >= 4:
        last4 = q.tail(4)
        ttm = {k: float(last4[k].sum()) for k in ["Revenue", "EBITDA", "PAT", "EPS"]
               if last4[k].notna().all()}
        ttm["quarters"] = list(last4.index)

    return {
        "annual": m,
        "quarterly": q,
        "ttm": ttm,
        "is_financial": fin,
        "bs_latest_interim": bs_latest_interim,
        "raw": {"pl": pl, "bs": bs, "cf": cf, "ratios": rt},
    }


def cagr(series: pd.Series, years: int) -> float | None:
    s = series.dropna()
    if len(s) < years + 1:
        return None
    start, end = s.iloc[-(years + 1)], s.iloc[-1]
    if start <= 0 or end <= 0:
        return None
    return float((end / start) ** (1 / years) - 1)


def growth_table(annual: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    out = {}
    for metric in ["Revenue", "EBITDA", "PAT", "EPS"]:
        if metric in annual:
            out[metric] = {f"{y}Y": cagr(annual[metric], y) for y in (3, 5, 10)}
    return out


def _check(name: str, period: str, expected: float, actual: float, tol_abs: float,
           tol_rel: float = 0.0) -> dict:
    diff = actual - expected
    ok = abs(diff) <= max(tol_abs, abs(expected) * tol_rel)
    return {"check": name, "period": period, "expected": round(float(expected), 2),
            "actual": round(float(actual), 2), "difference": round(float(diff), 2),
            "status": "OK" if ok else "MISMATCH"}


def _num(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def reconcile(fp: FactPack, st: dict) -> list[dict]:
    """Arithmetic and cross-source checks. Mismatches are reported, never silently fixed."""
    checks: list[dict] = []
    pl, bs, cf = st["raw"]["pl"], st["raw"]["bs"], st["raw"]["cf"]

    def cell(df, r, c):
        return df.at[r, c] if r in df.index else None

    if not pl.empty and not st["is_financial"]:
        for c in pl.columns[-5:]:
            s, e, o = (cell(pl, r, c) for r in ("Sales", "Expenses", "Operating Profit"))
            if _num(s) and _num(e) and _num(o):
                checks.append(_check("Sales - Expenses = Operating Profit", fy_label(c), s - e, o, 2))
            vals = [cell(pl, r, c) for r in
                    ("Operating Profit", "Other Income", "Interest", "Depreciation", "Profit before tax")]
            if all(_num(v) for v in vals):
                op_, oi, it, dp, pbt = vals
                checks.append(_check("OP + Other income - Interest - D&A = PBT", fy_label(c),
                                     op_ + oi - it - dp, pbt, 3, 0.005))
    if not bs.empty:
        for c in bs.columns[-5:]:
            tl, ta = cell(bs, "Total Liabilities", c), cell(bs, "Total Assets", c)
            if _num(tl) and _num(ta):
                checks.append(_check("Total liabilities = Total assets", fy_label(c), ta, tl, 2))
    if not cf.empty:
        for c in cf.columns[-5:]:
            vals = [cell(cf, r, c) for r in
                    ("Cash from Operating Activity", "Cash from Investing Activity",
                     "Cash from Financing Activity", "Net Cash Flow")]
            if all(_num(v) for v in vals):
                checks.append(_check("CFO + CFI + CFF = Net cash flow", fy_label(c),
                                     vals[0] + vals[1] + vals[2], vals[3], 3))
    # Cross-source: Screener vs Yahoo for the latest common fiscal year (Yahoo reports INR units)
    yinc = fp.yahoo.get("annual_income", {})
    ann = st["annual"]
    if yinc and not ann.empty:
        for ylabel, mlabel in [("Total Revenue", "Revenue"), ("Net Income", "PAT")]:
            for d, v in sorted((yinc.get(ylabel) or {}).items(), reverse=True):
                label = f"FY{d[2:4]}" if d[5:7] == "03" else None
                if v is not None and label in ann.index and mlabel in ann and _num(ann.at[label, mlabel]):
                    if any(f["metric"] == mlabel and fy_label(f["period"]) == label for f in fp.fact_resolutions):
                        break  # the cited resolution retains both original vendor readings
                    checks.append(_check(f"{mlabel}: Screener vs Yahoo (Rs Cr)", label,
                                         ann.at[label, mlabel], v / 1e7, 5, 0.03))
                    break
    # Screener P/E vs computed (market cap / TTM PAT)
    tr = fp.screener.get("top_ratios", {})
    mcap, pe = tr.get("Market Cap"), tr.get("Stock P/E")
    ttm_pat = st["ttm"].get("PAT")
    if _num(mcap) and _num(pe) and ttm_pat and ttm_pat > 0:
        checks.append(_check("Stock P/E: Market cap / TTM PAT vs Screener", "TTM", mcap / ttm_pat,
                             pe, 0.5, 0.05))
    return checks
