"""Render the finished research as a self-contained HTML report (plus JSON and markdown)."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

from aladeen import __version__
from aladeen.calllog import store as calllog
from aladeen.config import DESKS
from aladeen.dataflows.symbols import safe_component
from aladeen.firm.roster import TITLES
from aladeen.quant.statements import fy_label

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")
_TPL = Path(__file__).parent / "templates"


# ---------------------------------------------------------------- formatting
def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def f_num(v, nd=0):
    return "—" if _nan(v) else (f"({abs(v):,.{nd}f})" if v < 0 else f"{v:,.{nd}f}")


def f_inr(v, nd=2):
    return "—" if _nan(v) else f"₹{v:,.{nd}f}"


def f_pct(v, nd=1):  # decimal
    return "—" if _nan(v) else f"{v * 100:.{nd}f}%"


def f_pctv(v, nd=1):  # already percent
    return "—" if _nan(v) else f"{v:.{nd}f}%"


def f_x(v, nd=1):
    return "—" if _nan(v) else f"{v:.{nd}f}x"


def md(text: str | None) -> str:
    return _MD.render(text or "")


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TPL)), autoescape=select_autoescape(["html", "j2"]))
    env.filters.update(num=f_num, inr=f_inr, pct=f_pct, pctv=f_pctv, x=f_x, md=md)
    return env


# ---------------------------------------------------------------- table builders
_FMT = {
    "num": lambda v: f_num(v, 0), "num1": lambda v: f_num(v, 1), "num2": lambda v: f_num(v, 2),
    "pctv": f_pctv, "x": f_x, "x2": lambda v: f_x(v, 2),
}


def _table(df: pd.DataFrame, rows: list[tuple[str, str, str]], cols: list[str]) -> list[dict]:
    """rows: (label, column-in-df, format). A leading '*' in the label makes the row bold."""
    out = []
    for label, key, kind in rows:
        if key not in df.columns:
            continue
        vals = [_FMT[kind](df.at[c, key] if c in df.index else None) for c in cols]
        out.append({"label": label.lstrip("*"), "values": vals, "bold": label.startswith("*")})
    return out


_BOLD = {"Sales", "Revenue", "Operating Profit", "Financing Profit", "Net Profit", "Profit before tax",
         "Total Assets", "Total Liabilities", "Cash from Operating Activity", "Free Cash Flow"}


def _raw_table(df: pd.DataFrame, n: int = 6) -> dict:
    if df is None or df.empty:
        return {"cols": [], "rows": []}
    cols = list(df.columns)[-n:]
    rows = []
    for name in df.index:
        vals = [df.at[name, c] for c in cols]
        if all(_nan(x) for x in vals):
            continue
        rows.append({"label": name,
                     "values": [f_pctv(x, 0) if "%" in name else f_num(x, 0) for x in vals],
                     "bold": name in _BOLD})
    return {"cols": [fy_label(c) for c in cols], "rows": rows}


def _historical_multiples(fp, annual: pd.DataFrame) -> pd.DataFrame:
    """P/E and P/B at each fiscal year end, from point-in-time prices."""
    out = pd.DataFrame(index=annual.index)
    if fp.prices is None or fp.prices.empty:
        return out
    px = fp.prices["close"]
    pe, pb = [], []
    for lab in annual.index:
        p = None
        if lab.startswith("FY"):
            fy_end = pd.Timestamp(year=2000 + int(lab[2:]), month=3, day=31)
            s = px[px.index <= fy_end]
            if not s.empty and (fy_end - s.index[-1]).days <= 10:
                p = float(s.iloc[-1])
        eps = annual.at[lab, "EPS"] if "EPS" in annual else None
        bv = annual.at[lab, "BVPS"] if "BVPS" in annual else None
        pe.append(p / eps if p and not _nan(eps) and eps > 0 else None)
        pb.append(p / bv if p and not _nan(bv) and bv > 0 else None)
    out["P/E"] = pe
    out["P/B"] = pb
    return out


def _plain(obj) -> dict:
    if obj is None:
        return {}
    return obj.model_dump() if hasattr(obj, "model_dump") else dict(obj)


def build_context(state: dict, cfg: dict) -> dict[str, Any]:
    fp, q, v, f = state["fp"], state["quant"], state["valuation"], state["final"]
    st = q["statements"]
    annual: pd.DataFrame = st["annual"]
    a5 = [c for c in annual.index if c.startswith("FY")][-5:] or list(annual.index)[-5:]

    # Highlights: 5 actual years + 2 model years (revenue only: the model does not forecast PAT/EPS)
    hi = _table(annual, [("*Revenue", "Revenue", "num"), ("YoY growth (%)", "Revenue growth %", "pctv"),
                         ("*EBITDA", "EBITDA", "num"), ("EBITDA margin (%)", "EBITDA margin %", "pctv"),
                         ("*PAT", "PAT", "num"), ("PAT margin (%)", "PAT margin %", "pctv"),
                         ("EPS (₹)", "EPS", "num2"), ("Free cash flow", "FCF", "num"),
                         ("*ROE (%)", "ROE %", "pctv"), ("ROCE (%)", "ROCE %", "pctv"),
                         ("Borrowings", "Borrowings", "num")], a5)
    model_cols: list[str] = []
    if v.get("dcf") and a5:
        last = a5[-1]
        base_year = int(last[2:]) if last.startswith("FY") else None
        proj = v["dcf"]["projections"][:2]
        model_cols = [f"FY{base_year + i + 1:02d}E" if base_year is not None else f"Y{i + 1}E"
                      for i in range(len(proj))]
        for r in hi:
            if r["label"] == "Revenue":
                r["values"] += [f_num(p["revenue"]) for p in proj]
            elif r["label"] == "YoY growth (%)":
                r["values"] += [f_pct(p["growth"]) for p in proj]
            else:
                r["values"] += ["—"] * len(proj)

    ratios = _table(annual.join(_historical_multiples(fp, annual)), [
        ("P/E at fiscal year-end (x)", "P/E", "x"), ("P/B at fiscal year-end (x)", "P/B", "x"),
        ("Return on equity (%)", "ROE %", "pctv"), ("Return on capital employed (%)", "ROCE %", "pctv"),
        ("ROCE as published by Screener (%)", "ROCE % (Screener)", "pctv"),
        ("Debt / equity (x)", "Debt/Equity", "x2"), ("Interest coverage (x)", "Interest Coverage", "x"),
        ("CFO / PAT (x)", "CFO/PAT", "x2"), ("Debtor days", "Debtor Days", "num"),
        ("Inventory days", "Inventory Days", "num"), ("Days payable", "Days Payable", "num"),
        ("Cash conversion cycle (days)", "Cash Conversion Cycle", "num"), ("EPS (₹)", "EPS", "num2"),
        ("Book value per share (₹)", "BVPS", "num1"), ("Dividend payout (%)", "Dividend Payout %", "pctv"),
    ], a5)

    qd: pd.DataFrame = st["quarterly"]
    quarters = []
    if not qd.empty:
        for idx, r in qd.tail(8).iterrows():
            quarters.append({"q": idx, "rev": f_num(r["Revenue"]), "yoy": f_pctv(r.get("Revenue YoY %")),
                             "ebitda": f_num(r["EBITDA"]), "mgn": f_pctv(r["EBITDA margin %"]),
                             "pat": f_num(r["PAT"]), "pat_yoy": f_pctv(r.get("PAT YoY %")),
                             "eps": f_num(r["EPS"], 2)})

    sh = fp.table("shareholding")
    shareholding = {
        "cols": sh.get("columns", [])[-6:],
        "rows": [{"label": k, "values": [f_num(x) if k == "No. of Shareholders" else f_pctv(x, 2)
                                         for x in vals[-6:]]}
                 for k, vals in sh.get("rows", {}).items()],
    }
    latest_sh = {k: (vals[-1] if vals else None) for k, vals in sh.get("rows", {}).items()}
    rec = q.get("reconciliation", [])
    cls = fp.company.get("classification", {})
    rating = f["rating"]
    runner = state.get("_runner")
    return {
        "version": __version__,
        "cfg": cfg,
        "fp": fp,
        "company": fp.company,
        "sector": cls.get("Sector") or cls.get("Broad Sector") or "—",
        "industry": cls.get("Industry") or cls.get("Broad Industry") or "—",
        "rating": rating,
        "rating_class": {"BUY": "buy", "HOLD": "hold", "SELL": "sell"}.get(rating, "hold"),
        "final": f,
        "v": v,
        "q": q,
        "mk": q["market"],
        "tr": fp.screener.get("top_ratios", {}),
        "t": q["technicals"],
        "latest_sh": latest_sh,
        "decision": _plain(state.get("debate_verdict")),
        "assumptions": state.get("assumptions", {}),
        "memos": {k: state["memos"][k] for k in DESKS if k in state.get("memos", {})},
        "titles": TITLES,
        "mandate": _plain(state.get("mandate")),
        "desk_review": _plain(state.get("desk_review")),
        "revisions": state.get("revisions", []),
        "debate": state.get("debate", []),
        "risk": _plain(state.get("risk_review")),
        "rating_check": state.get("rating_check", {}),
        "council": state.get("council"),
        "audit_flags": {k: x for k, x in state.get("audit", {}).items() if x},
        "audit_count": len(state.get("audit", {})),
        "reconciliation": rec,
        "rec_failed": [r for r in rec if r["status"] != "OK"],
        "highlights": {"cols": a5 + model_cols, "rows": hi, "model_cols": model_cols},
        "income": _raw_table(st["raw"]["pl"]),
        "balance": _raw_table(st["raw"]["bs"]),
        "cashflow": _raw_table(st["raw"]["cf"]),
        "ratios": {"cols": a5, "rows": ratios},
        "quarters": quarters,
        "shareholding": shareholding,
        "sens": v.get("sensitivity"),
        "peers": fp.peers,
        "peer_cols": [c for c in ["CMP Rs.", "P/E", "Mar Cap Rs.Cr.", "Div Yld %", "Qtr Sales Var %",
                                  "Qtr Profit Var %", "ROCE %"] if fp.peers and c in fp.peers[0]],
        "short_term": q.get("short_term", {}),
        "charts": {**q.get("charts", {}), "scenario": v.get("scenario_chart")},
        "news": fp.news[:12],
        "announcements": fp.screener.get("documents", {}).get("announcements", []),
        "documents": fp.documents,
        "warnings": list(dict.fromkeys(state.get("data_caveats", fp.warnings) + v.get("warnings", []))),
        "report_status": state.get("report_status", "final"),
        "draft_reason": state.get("draft_reason", ""),
        "owner_rulings": state.get("owner_rulings", []),
        "valuation_revisions": state.get("valuation_revisions", []),
        "sources": [s for s in fp.sources if s.get("url")],
        "prior_calls": state.get("prior_calls", []),
        "published": date.fromisoformat(fp.as_of).strftime("%d-%b-%Y"),
        "synthetic": fp.synthetic,
        "llm_calls": len(getattr(runner, "calls", []) or []),
    }


def render_report(state: dict, cfg: dict) -> str:
    if state.get("decision_pending"):
        return _env().get_template("pending.html.j2").render(**state)
    return _env().get_template("report.html.j2").render(**build_context(state, cfg))


def _bullets(items) -> list[str]:
    return [f"- {i}" for i in items or []] or ["- None"]


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


_ASSUMPTION_LABELS = [
    ("revenue_growth", "Revenue growth, years 1-5", "pct_list"), ("ebit_margin", "EBIT margin, years 1-5", "pct_list"),
    ("da_pct_revenue", "Depreciation, % of revenue", "pct"), ("capex_pct_revenue", "Capex, % of revenue", "pct"),
    ("nwc_pct_incremental_revenue", "Working capital, % of extra revenue", "pct"),
    ("terminal_growth", "Terminal growth", "pct"), ("stable_roc", "Return on capital in stable growth", "pct"),
    ("beta", "Beta", "num"), ("cost_of_equity_premium", "Company-specific premium on Ke", "pct"),
    ("roe_path", "ROE, years 1-10", "pct_list"), ("sustainable_roe", "Sustainable (terminal) ROE", "pct"),
    ("payout_ratio", "Dividend payout", "pct"), ("long_term_growth", "Terminal growth", "pct"),
]


def _assumptions_md(a: dict) -> list[str]:
    rows = ["| Assumption | Value |", "|---|---|"]
    for key, label, kind in _ASSUMPTION_LABELS:
        v = a.get(key)
        if v is None:
            continue
        shown = (", ".join(_pct(x) for x in v) if kind == "pct_list" else _pct(v) if kind == "pct" else f"{v:.2f}")
        rows.append(f"| {label} | {shown} |")
    if len(rows) == 2:
        rows.append("| All assumptions | Engine defaults (history-based) |")
    out = rows + [""]
    for case in ("bear", "base", "bull"):
        if a.get(f"{case}_case_narrative"):
            out.append(f"**{case.title()} case:** {a[f'{case}_case_narrative']}")
    if a.get("rationale"):
        out.append(f"**Rationale:** {a['rationale']}")
    return out


def transcript_md(state: dict) -> str:
    """The research file: everything the team wrote, in the order it happened, readable by a non-expert."""
    fp = state["fp"]
    out = [f"# Research file — {fp.name} ({fp.ticker}), {fp.as_of}", ""]
    m = _plain(state.get("mandate"))
    if m:
        out += ["## CIO mandate", "**Key questions**", *_bullets(m.get("key_questions")), "", "**Desk briefs**",
                "| Desk | Brief |", "|---|---|",
                *[f"| {TITLES.get(b['desk'], b['desk'])} | {b['focus']} |" for b in m.get("briefs", [])], ""]
        if m.get("watch_items"):
            out += ["**Watch items**", *_bullets(m["watch_items"]), ""]
    for k, text in state.get("memos", {}).items():
        out += [f"## Memo — {TITLES.get(k, k)}", text, ""]
    r = _plain(state.get("desk_review"))
    if r:
        out += ["## CIO review of the memos", "| Desk | Verdict | Notes |", "|---|---|---|",
                *[f"| {TITLES.get(x['desk'], x['desk'])} | {x['verdict'].title()} | {x['notes']} |"
                  for x in r.get("reviews", [])], "", f"**Synthesis:** {r.get('synthesis', '')}", ""]
    if state.get("owner_rulings"):
        out += ["## The firm owner's rulings on conflicting evidence"]
        for r in state["owner_rulings"]:
            fig = f" Figure: {r['value']:g} {r.get('unit') or ''}".rstrip() if r.get("value") is not None else ""
            out += [f"- **{r['question']}** — {r.get('ruling') or 'Figure set by the owner.'}{fig}"]
        out += [""]
    held = state.get("held")
    if held:
        out += ["## Paused for the firm owner", "The research is waiting for rulings on:",
                *_bullets(q["text"] for q in held["questions"]), ""]
    for rv in state.get("revisions", []):
        out += [f"## Revision request — {TITLES.get(rv['desk'], rv['desk'])} (round {rv['round']})", rv["notes"], ""]
    out += ["## Valuation assumptions", *_assumptions_md(state.get("assumptions") or {}), ""]
    for d in state.get("debate", []):
        out += [f"## {d['side'].title()} Advocate — {'opening' if d['round'] == 0 else 'rebuttal ' + str(d['round'])}",
                d["text"], ""]
    dv = _plain(state.get("debate_verdict"))
    if dv:
        out += ["## CIO ruling on the debate", f"**Lean:** {dv['lean']}", "", dv.get("summary", ""), "",
                "**Bull points that survived**", *_bullets(dv.get("surviving_bull_points")), "",
                "**Bear points that survived**", *_bullets(dv.get("surviving_bear_points")), ""]
        if dv.get("rejected_points"):
            out += ["**Rejected points**", *_bullets(dv["rejected_points"]), ""]
        out += [f"**Kill fact:** {dv.get('kill_fact', '')}", "",
                f"**Why the losing side lost:** {dv.get('why_losing_side_lost', '')}", ""]
    rr = _plain(state.get("risk_review"))
    if rr:
        out += ["## Chief Risk Officer", f"**Risk rating:** {rr['risk_rating']}", "",
                f"**Aggressive lens:** {rr['aggressive']}", "", f"**Neutral lens:** {rr['neutral']}", "",
                f"**Conservative lens:** {rr['conservative']}", "", f"**Recommendation:** {rr['recommendation']}", ""]
    f = state.get("final") or {}
    if state.get("report_status") == "draft":
        out += ["## Decision pending", state["draft_reason"]]
    elif f:
        out += ["## CIO decision", f"**Rating:** {f.get('rating')}{' (' + f['qualifier'] + ')' if f.get('qualifier') else ''}"
                f" · **Position:** {f.get('position_size')} · **Governance:** {f.get('governance_score')}", "",
                f"**Headline:** {f.get('headline', '')}", "", f.get("executive_summary", ""), "",
                "**Thesis pillars**", *_bullets(f.get("thesis_pillars")), "",
                f"**Kill fact:** {f.get('kill_fact', '')}", "", f"**Rating rationale:** {f.get('rating_rationale', '')}",
                ""]
    rc = state.get("rating_check") or {}
    if rc.get("note"):
        out += ["## Compliance", rc["note"], ""]
    c = state.get("council")
    if c and c.get("advisors"):
        for k, text in c["advisors"].items():
            out += [f"## Independent council — {k}", text, ""]
        for i, rev in enumerate(c.get("reviews", []), 1):
            out += [f"## Council peer review {i}", rev, ""]
        v = c.get("verdict") or {}
        if v:
            out += ["## Council verdict", f"**Verdict:** {v.get('verdict')}", "", v.get("recommendation", ""), "",
                    "**Where the council agrees**", *_bullets(v.get("where_council_agrees")), "",
                    "**Where it clashes**", *_bullets(v.get("where_council_clashes")), "",
                    "**Blind spots**", *_bullets(v.get("blind_spots")), "",
                    f"**Do this first:** {v.get('one_thing_first', '')}", ""]
    if state.get("errors"):
        out += ["## Process notes", *_bullets(state["errors"]), ""]
    return "\n".join(out)


def _jsonable(state: dict) -> dict:
    keep = ["ticker", "as_of", "memos", "revisions", "assumptions", "debate", "final", "rating_check", "council",
            "audit", "errors", "prior_calls", "call_id", "valuation_revisions"]
    out = {k: state.get(k) for k in keep + ["report_status", "draft_reason", "decision_pending", "owner_rulings"]}
    out["fact_resolutions"] = state["fp"].fact_resolutions
    for k in ("mandate", "desk_review", "debate_verdict", "risk_review"):
        out[k] = _plain(state.get(k))
    v = dict(state.get("valuation", {}))
    v.pop("scenario_chart", None)
    out["valuation"] = v
    return out


def save_outputs(state: dict, cfg: dict, out_dir: str | Path | None = None) -> dict[str, Path]:
    fp = state["fp"]
    base = Path(out_dir) if out_dir else Path(cfg["results_dir"]) / safe_component(fp.ticker) / fp.as_of
    base.mkdir(parents=True, exist_ok=True)
    paths = {"report": base / "report.html", "factpack": base / "factpack.json",
             "research": base / "research.json", "transcript": base / "transcript.md"}
    paths["report"].write_text(render_report(state, cfg), encoding="utf-8")
    fp.save(paths["factpack"])
    paths["research"].write_text(json.dumps(_jsonable(state), indent=2, default=str), encoding="utf-8")
    paths["transcript"].write_text(transcript_md(state), encoding="utf-8")
    return paths


def log_call(state: dict, cfg: dict, report_path: str | Path) -> dict | None:
    """Append the call to the call log (closing prices on the report date)."""
    fp, v, f = state["fp"], state["valuation"], state["final"]
    if fp.synthetic or state.get("report_status") == "draft":
        return None
    bench_close = None
    if fp.benchmark_prices is not None and not fp.benchmark_prices.empty:
        bench_close = float(fp.benchmark_prices["close"].iloc[-1])
    last_px_date = fp.prices.index[-1].date().isoformat()
    notes = [] if last_px_date == fp.as_of else [f"Closing price is from {last_px_date} (last trading day)."]
    row = {
        "call_date": fp.as_of, "company": fp.name, "ticker": fp.yahoo_symbol,
        "rating": f["rating"] + (f" ({f['qualifier']})" if f.get("qualifier") else ""),
        "target_price": f"{v['target_price']:.2f}", "close_on_call_date": f"{v['cmp']:.2f}",
        "benchmark": fp.benchmark,
        "benchmark_close_on_call_date": f"{bench_close:.2f}" if bench_close else "",
        "report_file": str(report_path), "notes": " ".join(notes),
    }
    return calllog.store_from_config(cfg).append(row)
