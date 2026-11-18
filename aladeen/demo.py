"""Offline demo: a synthetic company and scripted agents. No network, no API key.

    aladeen demo            # writes examples/demo/report.html

Every number is synthetic. The demo exists to show the report layout and to test the
pipeline end to end; it says nothing about any real security.
"""

from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd

from aladeen.dataflows.factpack import FactPack
from aladeen.dataflows.logo import monogram_svg
from aladeen.firm.schemas import (
    Catalyst,
    CouncilVerdict,
    DebateVerdict,
    DeskReviewSet,
    ESGPillar,
    FinalCall,
    ResearchMandate,
    RiskItem,
    RiskReview,
    ValuationAssumptions,
)
from aladeen.llm import OfflineRunner

DEMO_DATE = date(2026, 11, 18)


def _prices(seed: int, last: float, drift: float, vol: float, end: date, years: int = 10) -> pd.DataFrame:
    """Random-walk prices rescaled so the final close equals ``last``."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=int(252 * years))
    rets = rng.normal(drift / 252, vol / np.sqrt(252), len(idx))
    close = np.exp(np.cumsum(rets))
    close = close / close[-1] * last
    high = close * (1 + np.abs(rng.normal(0, 0.008, len(idx))))
    low = close * (1 - np.abs(rng.normal(0, 0.008, len(idx))))
    vol_ = rng.integers(200_000, 900_000, len(idx)).astype(float)
    return pd.DataFrame({"open": (high + low) / 2, "high": high, "low": low, "close": close,
                         "adj_close": close, "volume": vol_}, index=idx)


def synthetic_factpack(as_of: date = DEMO_DATE) -> FactPack:
    years = [f"Mar {y}" for y in range(2015, 2027)]
    n = len(years)
    sales = [round(1000 * (1.12 ** i)) for i in range(n)]
    op = [round(s * (0.15 + 0.004 * i)) for i, s in enumerate(sales)]
    oi = [round(s * 0.01) for s in sales]
    it = [20 - i for i in range(n)]
    dep = [round(s * 0.03) for s in sales]
    pbt = [o + a - b - c for o, a, b, c in zip(op, oi, it, dep, strict=True)]
    pat = [round(p * 0.75) for p in pbt]
    shares = 10.0  # crore
    ttm_sales, ttm_pat = round(sales[-1] * 1.06), round(pat[-1] * 1.07)
    pl = {"columns": years + ["TTM"], "rows": {
        "Sales": sales + [ttm_sales], "Expenses": [s - o for s, o in zip(sales, op, strict=True)] + [None],
        "Operating Profit": op + [None], "OPM %": [round(o / s * 100) for o, s in zip(op, sales, strict=True)] + [None],
        "Other Income": oi + [None], "Interest": it + [None], "Depreciation": dep + [None],
        "Profit before tax": pbt + [None], "Tax %": [25] * n + [None], "Net Profit": pat + [ttm_pat],
        "EPS in Rs": [round(p / shares, 2) for p in pat] + [round(ttm_pat / shares, 2)],
        "Dividend Payout %": [20] * n + [None]}}
    eq = [100] * n
    reserves, res = [], 400.0
    for p in pat:
        res += p * 0.8
        reserves.append(round(res))
    borrow = [max(200 - 18 * i, 20) for i in range(n)]
    fixed = [300 + 40 * i for i in range(n)]
    cwip = [20 + 3 * i for i in range(n)]
    inv = [50 + 20 * i for i in range(n)]
    other_liab = [round(s * 0.18) for s in sales]
    total = [e + rs + b + ol for e, rs, b, ol in zip(eq, reserves, borrow, other_liab, strict=True)]
    other_assets = [t - f - c - i for t, f, c, i in zip(total, fixed, cwip, inv, strict=True)]
    bs = {"columns": years, "rows": {
        "Equity Capital": eq, "Reserves": reserves, "Borrowings": borrow, "Other Liabilities": other_liab,
        "Total Liabilities": list(total), "Fixed Assets": fixed, "CWIP": cwip, "Investments": inv,
        "Other Assets": other_assets, "Total Assets": list(total)}}
    cfo = [round(p * 1.05) for p in pat]
    capex = [round(s * 0.04) for s in sales]
    cfi = [-c - 10 for c in capex]
    cff = [round(-p * 0.2 - 18) for p in pat]
    cf = {"columns": years, "rows": {
        "Cash from Operating Activity": cfo, "Cash from Investing Activity": cfi,
        "Cash from Financing Activity": cff,
        "Net Cash Flow": [a + b + c for a, b, c in zip(cfo, cfi, cff, strict=True)],
        "Free Cash Flow": [a - c for a, c in zip(cfo, capex, strict=True)]}}
    ratios = {"columns": years, "rows": {"Debtor Days": [60 - i for i in range(n)],
                                          "Inventory Days": [80 - i for i in range(n)],
                                          "Days Payable": [50] * n,
                                          "Cash Conversion Cycle": [90 - 2 * i for i in range(n)],
                                          "ROCE %": [18 + i for i in range(n)]}}
    qcols = ["Sep 2023", "Dec 2023", "Mar 2024", "Jun 2024", "Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025",
             "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
    qs = [round(sales[-1] / 4 * (1.028 ** (i - 9))) for i in range(len(qcols))]
    qpat = [round(x * 0.135) for x in qs]
    quarters = {"columns": qcols, "rows": {"Sales": qs, "Operating Profit": [round(x * 0.2) for x in qs],
                                           "Net Profit": qpat, "EPS in Rs": [round(p / shares, 2) for p in qpat]}}
    shp = {"columns": qcols[-8:], "rows": {
        "Promoters": [61.2] * 6 + [60.8, 60.8],
        "FIIs": [12.1, 12.4, 12.9, 13.3, 13.8, 14.0, 14.6, 14.9],
        "DIIs": [9.8, 10.0, 10.2, 10.4, 10.6, 10.9, 11.1, 11.3],
        "Public": [16.9, 16.4, 15.7, 15.1, 14.4, 13.9, 13.5, 13.0],
        "No. of Shareholders": [52000, 54100, 57300, 60200, 63000, 65500, 68100, 70400]}}
    prices = _prices(7, 1150.0, 0.17, 0.30, as_of)
    bench = _prices(11, 25000.0, 0.11, 0.16, as_of)
    cmp_ = float(prices["close"].iloc[-1])
    mcap = round(cmp_ * shares)
    screener = {
        "source": "synthetic", "name": "Demo Industries Ltd", "consolidated": True, "company_id": None,
        "warehouse_id": None, "url": None,
        "top_ratios": {"Market Cap": mcap, "Current Price": round(cmp_, 2),
                       "High / Low": [round(float(prices["close"].tail(252).max())),
                                      round(float(prices["close"].tail(252).min()))],
                       "Stock P/E": round(mcap / ttm_pat, 1), "Book Value": round((100 + reserves[-1]) / shares),
                       "Dividend Yield": 0.6, "ROCE": 29.0, "ROE": 22.0, "Face Value": 10.0},
        "tables": {"profit_loss": pl, "balance_sheet": bs, "cash_flow": cf, "ratios": ratios,
                   "quarters": quarters, "shareholding": shp, "growth": {}},
        "documents": {"announcements": [
            {"title": "Outcome of board meeting: Q2 FY27 results", "url": "https://example.com/demo-results",
             "date": "2026-11-12", "summary": "Synthetic announcement for the demo"},
            {"title": "Credit rating reaffirmed", "url": "https://example.com/demo-rating",
             "date": "2026-10-28", "summary": "Synthetic announcement for the demo"}],
            "annual_reports": [], "concalls": [], "credit_ratings": []},
        "classification": {"Sector": "Industrials (synthetic)", "Industry": "Industrial components (synthetic)"},
        "indices": ["Demo Index"],
    }
    peers = [
        {"Company": "Demo Industries", "CMP Rs.": round(cmp_, 1), "P/E": round(mcap / ttm_pat, 1),
         "Mar Cap Rs.Cr.": mcap, "Div Yld %": 0.6, "Qtr Sales Var %": 11.0, "Qtr Profit Var %": 14.0,
         "ROCE %": 29.0},
        {"Company": "Sample Peer A", "CMP Rs.": 950.0, "P/E": 28.0, "Mar Cap Rs.Cr.": 9000, "Div Yld %": 0.8,
         "Qtr Sales Var %": 9.0, "Qtr Profit Var %": 10.0, "ROCE %": 24.0},
        {"Company": "Sample Peer B", "CMP Rs.": 410.0, "P/E": 31.0, "Mar Cap Rs.Cr.": 5200, "Div Yld %": 0.4,
         "Qtr Sales Var %": 13.0, "Qtr Profit Var %": 12.0, "ROCE %": 21.0},
        {"Company": "Sample Peer C", "CMP Rs.": 1290.0, "P/E": 24.0, "Mar Cap Rs.Cr.": 12500, "Div Yld %": 1.1,
         "Qtr Sales Var %": 7.0, "Qtr Profit Var %": 6.0, "ROCE %": 26.0},
    ]
    fp = FactPack(ticker="DEMO", yahoo_symbol="DEMO.NS", exchange="NSE", as_of=as_of.isoformat(),
                  benchmark="^NSEI", screener=screener, peers=peers, prices=prices, benchmark_prices=bench,
                  synthetic=True)
    fp.yahoo = {"info": {}, "balance_sheet_latest": {"date": "2026-03-31", "values": {
        "Total Debt": borrow[-1] * 1e7, "Cash Cash Equivalents And Short Term Investments": 260 * 1e7,
        "Minority Interest": 0.0, "Current Assets": 2600 * 1e7, "Current Liabilities": 1100 * 1e7,
        "Total Liabilities Net Minority Interest": 1500 * 1e7}}}
    fp.company = {"name": "Demo Industries Ltd", "about": "A synthetic industrial components maker used to "
                  "demonstrate the report. It does not exist.", "website": None,
                  "classification": screener["classification"], "indices": ["Demo Index"],
                  "bse_code": None, "nse_symbol": "DEMO", "pros": [], "cons": [],
                  "logo": monogram_svg("Demo Industries", "#0f9d8a")}
    fp.news = [{"title": "Demo Industries wins synthetic export order", "url": "https://example.com/n1",
                "date": "2026-11-14", "source": "Demo Wire"},
               {"title": "Sector demand steady, says synthetic survey", "url": "https://example.com/n2",
                "date": "2026-11-05", "source": "Demo Wire"}]
    fp.warnings = ["Synthetic data: this demo describes no real company."]
    fp.sources = [{"name": "Synthetic data generated by aladeen/demo.py", "url": "https://example.com/demo"}]
    return fp


def _grab(pattern: str, text: str, default: str = "n/a") -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else default


def demo_responder(name: str, schema, system: str, user: str):
    tag = "_Offline demo: scripted text, no model was called._"
    cmp_ = _grab(r"CMP: (₹[\d,\.]+)", user)
    ttm_rev = _grab(r"TTM revenue: (₹[\d,]+ Cr)", user)
    band = _grab(r"Rating implied by bands \(BUY >15%, HOLD 0-15%, SELL <0%\): (BUY|HOLD|SELL)", user, "HOLD")
    entry = _grab(r"entry price for 33% MoS ₹([\d,\.]+)", user, "")
    if schema is None:
        base = name.removesuffix("_rev")
        texts = {
            "fundamentals": f"{tag}\n\nRevenue has compounded steadily; TTM revenue is {ttm_rev}. Margins have "
                            "widened gradually and operating cash flow has tracked profit.\n\n**Red flags:** none found.",
            "business": f"{tag}\n\nA synthetic components maker with a mid-sized share of a fragmented market.",
            "governance": f"{tag}\n\nPromoter holding is stable with a small recent decline; institutional "
                          "holding is rising. Annual reports were not available in the demo, so related-party "
                          "and auditor checks could not be done.\n\nGovernance score: Satisfactory.",
            "technical": f"{tag}\n\nThe stock trades near {cmp_}. The long-term trend is up; momentum is neutral."
                         + (" Support sits at the 200-DMA; entry is better near it." if name.endswith("_rev") else ""),
            "news": f"{tag}\n\nNews flow is mildly positive (a synthetic export order).",
            "filings": f"{tag}\n\nNo annual report or concall text was available in the demo.",
        }
        if base in texts:
            return texts[base]
        if name.startswith("bull"):
            return f"{tag}\n\n**Bull:** steady compounding, rising margins and a net-cash balance sheet."
        if name.startswith("bear"):
            return f"{tag}\n\n**Bear:** the valuation leans on the terminal value and margins may mean-revert."
        return f"{tag} Council view: the demo shows structure, not a real investment case."
    if schema is ResearchMandate:
        desks = re.findall(r"^(\w+) \(", user.split("## Research desks to brief", 1)[-1], re.M)
        desks = desks or ["fundamentals", "business", "governance", "filings", "news", "technical"]
        return ResearchMandate(
            key_questions=["Can margins keep expanding?", "Is cash conversion sustainable?",
                           "What does the price already assume?"],
            briefs=[{"desk": d, "focus": f"Demo brief for the {d} desk."} for d in desks],
            watch_items=["All data is synthetic."])
    if schema is DeskReviewSet:
        desks = re.findall(r"^## Memo — .*$", user, re.M)
        reviews = [{"desk": d, "verdict": "accept", "notes": "Clear and supported."}
                   for d in ["fundamentals", "business", "governance", "filings", "news"] if d in user]
        second_look = "Revision" in user or "200-DMA" in user
        reviews.append({"desk": "technical", "verdict": "accept" if second_look else "revise",
                        "notes": "Add the support level that matters for entry." if not second_look else "Fixed."})
        del desks
        return DeskReviewSet(reviews=reviews, synthesis=f"{tag} The desks agree the business compounds steadily; "
                                                        "the question is price.")
    if schema is ValuationAssumptions:
        return ValuationAssumptions(
            rationale=f"{tag} History-based defaults kept.",
            bear_case_narrative="Growth slows and margins fall back.",
            base_case_narrative="Growth fades toward the stable rate; margins hold.",
            bull_case_narrative="Export orders lift growth and margins.")
    if schema is DebateVerdict:
        return DebateVerdict(lean=band, surviving_bull_points=["Steady compounding with cash conversion"],
                             surviving_bear_points=["Valuation depends on the terminal value"],
                             kill_fact="Two consecutive quarters of falling operating margin.",
                             why_losing_side_lost="Scripted demo outcome.", summary=tag)
    if schema is RiskReview:
        return RiskReview(aggressive=f"{tag} A larger position needs margin expansion to continue.",
                          neutral="The draft lean is consistent with the bands.",
                          conservative="Size the position to the bear-case value.",
                          risk_rating="Moderate", recommendation="Starter position at most until the kill fact clears.")
    if schema is FinalCall:
        e = float(entry.replace(",", "")) if entry else None
        return FinalCall(
            rating=band, position_size="Starter", entry_zone_low=e, entry_zone_high=e,
            headline="Demo: a steady compounder priced for its record (synthetic).",
            executive_summary=f"{tag}\n\nThis demo report shows the layout of an AlaDeen Capital Research report. "
                              "All figures are synthetic.",
            thesis_pillars=["Steady revenue compounding.", "Gradual margin expansion.", "Net-cash balance sheet."],
            catalysts=[Catalyst(catalyst="Synthetic export order execution", timeline="H2 FY27",
                                impact="Better revenue mix")],
            risks=[RiskItem(risk="Margin mean-reversion", category="Competitive", probability="Medium",
                            impact="Medium", description_and_mitigant="Synthetic risk for the demo.")],
            esg=[ESGPillar(pillar=p, assessment="Insufficient data", commentary="Not assessed in the demo.")
                 for p in ("Environmental", "Social", "Governance")],
            governance_score="Satisfactory", kill_fact="Two consecutive quarters of falling operating margin.",
            why_losing_side_lost="Scripted demo outcome.", rating_rationale="Rating follows the return bands.")
    if schema is CouncilVerdict:
        return CouncilVerdict(where_council_agrees=["The demo shows the full report structure."],
                              where_council_clashes=["None (scripted)."], blind_spots=["Synthetic data."],
                              recommendation="Run a real ticker with an API key.", verdict="WAIT",
                              one_thing_first="Add an API key in Settings and research a real company.",
                              gaps_in_report=["All data is synthetic."], report_complete=False)
    raise ValueError(f"No demo response for {name} / {schema}")


def demo_runner(delay: float = 0.0) -> OfflineRunner:
    return OfflineRunner(demo_responder, delay=delay)
