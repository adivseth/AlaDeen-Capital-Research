"""What each member of the firm does when asked. The orchestrator decides who is asked, and when."""

from __future__ import annotations

import json
import random
import re
from concurrent.futures import ThreadPoolExecutor

from aladeen.dataflows.factpack import FactPack
from aladeen.firm import context as cx
from aladeen.firm.prompts import COUNCIL_ADVISORS, system_for
from aladeen.firm.roster import TITLES
from aladeen.firm.schemas import (
    CouncilVerdict,
    DebateVerdict,
    DeskReviewSet,
    FinalCall,
    ResearchMandate,
    RiskReview,
    ValuationAssumptions,
)
from aladeen.llm import Runner

_GOV_KEYS = ("related party", "auditor", "key audit matter", "emphasis of matter", "qualified",
             "pledge", "contingent", "remuneration", "guarantee", "board of directors", "independent director",
             "business responsibility", "brsr")
_BIZ_KEYS = ("management discussion", "industry", "outlook", "segment", "opportunit", "strategy", "market share")


# ------------------------------------------------------------------ material for each desk
def _pages(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"\[page (\d+)\]\n", text or "")
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def _excerpt(fp: FactPack, kind: str, keys: tuple[str, ...], budget: int) -> str:
    out, used = [], 0
    for d in fp.documents:
        if d.get("error") or d["kind"] != kind:
            continue
        for num, txt in _pages(d.get("text", "")):
            if any(k in txt.lower() for k in keys) and used + len(txt) <= budget:
                out.append(f"[{d['title']} p.{num}]\n{txt.strip()}")
                used += len(txt)
    return "\n\n".join(out) if out else "_no matching document pages available_"


def _filings_material(runner: Runner, cfg: dict, fp: FactPack) -> str:
    docs = [d for d in fp.documents if not d.get("error") and d.get("text")]
    if not docs:
        return "_No annual report or concall text could be read for this run._\n" + cx.documents_index_md(fp)
    if cfg["document_mode"] != "full":
        # Each document keeps its own budget; the most recent concall and presentation are read in full.
        per_doc = cfg.get("filings_chars_per_document", 30000)
        latest = {next((d["title"] for d in docs if d["kind"] == k), None) for k in ("concall", "presentation")}
        out = []
        for d in docs:
            cap = len(d["text"]) if d["title"] in latest else per_doc
            cut = "" if len(d["text"]) <= cap else f"\n[... truncated: {len(d['text']) - cap:,} more characters]"
            out.append(f"### {d['title']} ({d['pages']} pages)\n{d['text'][:cap]}{cut}")
        return "\n\n".join(out)
    summaries = []
    sys = system_for("document_chunk", cfg)
    for d in docs:
        text = d["text"]
        chunks = [text[i:i + 24000] for i in range(0, len(text), 24000)]

        def summarise(chunk, title=d["title"]):
            return runner.text(sys, f"Document: {title}\n\n{chunk}", tier="quick", name="document_chunk")

        with ThreadPoolExecutor(max_workers=4) as ex:
            parts = list(ex.map(summarise, chunks))
        summaries.append(f"### {d['title']} ({d['pages']} pages, read in {len(chunks)} chunks)\n" +
                         "\n".join(p for p in parts if "nothing material" not in p.lower()))
    return "\n\n".join(summaries)


def desk_material(desk: str, runner: Runner, cfg: dict, fp: FactPack, q: dict) -> str:
    if desk == "fundamentals":
        parts = [cx.company_md(fp), cx.market_md(q), cx.financials_md(q), cx.reconciliation_md(q),
                 cx.corporate_actions_md(fp), cx.warnings_md(fp)]
    elif desk == "business":
        parts = [cx.company_md(fp), cx.market_md(q), cx.financials_md(q, 6), cx.peers_md(fp, q),
                 "## Annual report excerpts\n" + _excerpt(fp, "annual_report", _BIZ_KEYS, 15000),
                 cx.web_md(fp, "sector")]
    elif desk == "governance":
        parts = [cx.company_md(fp), cx.shareholding_md(fp), cx.financials_md(q, 10),
                 cx.documents_index_md(fp), cx.news_md(fp, 10),
                 "## Annual report excerpts (governance-related pages)\n"
                 + _excerpt(fp, "annual_report", _GOV_KEYS, 25000), cx.warnings_md(fp)]
    elif desk == "technical":
        parts = [cx.market_md(q), cx.technicals_md(q), cx.short_term_md(q, fp)]
    elif desk == "news":
        parts = [cx.company_md(fp), cx.market_md(q), cx.news_md(fp), cx.short_term_md(q, fp),
                 cx.corporate_actions_md(fp), cx.web_md(fp, "analysts"), cx.web_md(fp, "history")]
    elif desk == "filings":
        parts = [cx.company_md(fp), cx.financials_md(q, 5), _filings_material(runner, cfg, fp)]
    else:
        raise ValueError(f"Unknown desk {desk!r}")
    return "\n\n".join(parts)


def memos_md(memos: dict[str, str], only: tuple[str, ...] | None = None) -> str:
    keys = only or tuple(memos)
    return "\n\n".join(f"## Memo — {TITLES.get(k, k)}\n{memos[k]}" for k in keys if k in memos)


# ------------------------------------------------------------------ CIO
def brief_md(cfg: dict) -> str:
    b = (cfg.get("research_brief") or "").strip()
    return f"## The firm owner's standing research brief\n{b}" if b else ""


def cio_mandate(runner: Runner, cfg: dict, fp: FactPack, q: dict, prior_md: str) -> ResearchMandate:
    desks = ", ".join(f"{d} ({TITLES[d]})" for d in cfg["desks"])
    user = "\n\n".join([cx.company_md(fp), cx.market_md(q), cx.financials_md(q, 5), cx.reconciliation_md(q),
                        cx.documents_index_md(fp), cx.warnings_md(fp), prior_md, brief_md(cfg),
                        f"## Research desks to brief\n{desks}"])
    m = runner.structured(system_for("cio_mandate", cfg), user, ResearchMandate, tier="deep", name="cio_mandate")
    data = m.model_dump()
    briefs = [b for b in data["briefs"] if b["desk"] in cfg["desks"]]
    briefed = {b["desk"] for b in briefs}
    for d in cfg["desks"]:  # every enabled desk gets a brief, even if the model skipped one
        if d not in briefed:
            briefs.append({"desk": d, "focus": "Cover your standard scope for this company."})
    data["briefs"] = briefs
    return ResearchMandate.model_validate(data)


def write_memo(desk: str, runner: Runner, cfg: dict, fp: FactPack, q: dict, mandate: ResearchMandate,
               revision_notes: str | None = None, previous: str | None = None,
               peer_memos: dict[str, str] | None = None) -> tuple[str, str]:
    material = desk_material(desk, runner, cfg, fp, q)
    brief = next((b.focus for b in mandate.briefs if b.desk == desk), "")
    head = [brief_md(cfg), f"## CIO brief for you\n{brief}",
            "## CIO's key questions\n" + "\n".join(f"- {x}" for x in mandate.key_questions)]
    if revision_notes:
        head.append(f"## CIO revision request\n{revision_notes}\n\n## Your previous memo\n{previous}\n\n"
                    "Rewrite the memo in full, fixing every point above.")
        others = {k: v for k, v in (peer_memos or {}).items() if k != desk}
        if others:  # a revision sees what the rest of the team found, so the memos do not contradict each other
            head.append("## The other desks' memos (for consistency; do not copy their numbers unless they are "
                        "also in your material)\n" + memos_md(others))
    user = "\n\n".join(head + [material])
    text = runner.text(system_for(desk, cfg), user, tier="quick", name=f"{desk}{'_rev' if revision_notes else ''}")
    return text, material


def cio_review(runner: Runner, cfg: dict, mandate: ResearchMandate, memos: dict[str, str],
               audit_md: str) -> DeskReviewSet:
    user = "\n\n".join(["## Mandate\n" + mandate.model_dump_json(indent=1), memos_md(memos), audit_md])
    return runner.structured(system_for("cio_review", cfg), user, DeskReviewSet, tier="deep", name="cio_review")


def cio_rule_on_debate(runner: Runner, cfg: dict, material: str, history: list[dict],
                       audit_md: str) -> DebateVerdict:
    transcript = "\n\n".join(f"### {h['side'].upper()} r{h['round']}\n{h['text']}" for h in history)
    user = f"{material}\n\n## Debate transcript\n{transcript}\n\n{audit_md}"
    return runner.structured(system_for("cio_debate", cfg), user, DebateVerdict, tier="deep",
                             name="cio_debate")


def cio_decide(runner: Runner, cfg: dict, material: str, verdict: DebateVerdict, risk: RiskReview,
               audit_md: str) -> FinalCall:
    user = "\n\n".join([material, "## Your ruling on the debate\n" + verdict.model_dump_json(indent=1),
                        "## Chief Risk Officer's review\n" + risk.model_dump_json(indent=1), audit_md])
    return runner.structured(system_for("cio_decision", cfg), user, FinalCall, tier="deep", name="cio_decision")


# ------------------------------------------------------------------ valuation, debate, risk
def default_assumptions(q: dict, cfg: dict) -> dict:
    if not q["is_financial"]:
        d = q.get("default_dcf_inputs")
        return d.__dict__ if d else {}
    b = q.get("bank") or {}
    return {"roe_path": b.get("default_roe_path"), "sustainable_roe": b.get("default_terminal_roe"),
            "payout_ratio": b.get("payout_3y"), "long_term_growth": b.get("default_terminal_growth"),
            "_context": {"roe_ttm": b.get("roe_ttm"), "roe_history": b.get("roe_history"),
                         "book_value": q.get("book"),
                         "pb_history": (b.get("pb_history") or {}).get("points")}}


def cost_of_capital_md(q: dict, cfg: dict) -> str:
    m = q["market"]
    rf, ds = cfg["risk_free_rate"], cfg.get("country_default_spread", 0.0)
    return (f"## Cost of capital inputs\nG-Sec {rf:.2%} less sovereign default spread {ds:.2%} = riskless "
            f"{rf - ds:.2%}; ERP {cfg['equity_risk_premium']:.2%} (total, includes country risk); beta "
            f"{m['beta']:.2f} (regression {m['beta_raw'] if m['beta_raw'] is None else round(m['beta_raw'], 2)}); "
            f"tax {cfg['tax_rate']:.2%}; terminal growth cap {cfg['terminal_growth_cap']:.2%}. Sector treatment: "
            f"{'financial (residual income on book value)' if q['is_financial'] else 'FCFF DCF'}.")


def valuation_analyst(runner: Runner, cfg: dict, fp: FactPack, q: dict, memos: dict[str, str],
                      mandate: ResearchMandate, challenge: str | None = None,
                      previous: dict | None = None) -> ValuationAssumptions:
    defaults = json.dumps(default_assumptions(q, cfg), default=str)
    parts = [
        "## CIO's key questions\n" + "\n".join(f"- {x}" for x in mandate.key_questions),
        cx.company_md(fp), cx.market_md(q), cx.financials_md(q), cx.peers_md(fp, q),
        f"## Default (history-based) assumptions\n{defaults}",
        cost_of_capital_md(q, cfg),
        memos_md(memos, ("fundamentals", "business", "filings")),
        cx.warnings_md(fp),
    ]
    if challenge:
        parts.append(f"## Your previous assumptions\n{json.dumps(previous or {}, default=str)}\n\n"
                     f"## Challenge to the valuation\n{challenge}\n\nRevise the assumptions where the evidence "
                     "supports the challenge, keep them where it does not, and say which in the rationale.")
    return runner.structured(system_for("valuation", cfg, financial=q["is_financial"]), "\n\n".join(parts),
                             ValuationAssumptions, tier="deep", name="valuation_rev" if challenge else "valuation")


def debate_material(fp: FactPack, q: dict, valuation: dict | None, memos: dict[str, str], synthesis: str,
                    prior_md: str) -> str:
    """With ``valuation=None`` this is the material for the opening cases: the advocates argue the business
    first, so the engine's number does not anchor them. Rebuttals and the CIO's ruling see the valuation."""
    parts = [cx.company_md(fp), cx.market_md(q), cx.financials_md(q, 6)]
    if valuation is not None:
        parts.append(cx.valuation_md(valuation))
    return "\n\n".join(parts + [f"## CIO synthesis of the desk work\n{synthesis}", memos_md(memos), prior_md])


def debate_turn(side: str, runner: Runner, cfg: dict, material: str, history: list[dict], round_no: int) -> str:
    transcript = "\n\n".join(
        f"### {h['side'].upper()} ({'opening' if h['round'] == 0 else 'rebuttal'})\n{h['text']}" for h in history)
    phase = "opening case" if round_no == 0 else "rebuttal (answer the other side's best point)"
    user = f"{material}\n\n## Debate so far\n{transcript or '_none yet_'}\n\nWrite your {phase} now."
    return runner.text(system_for(side, cfg), user, tier="quick", name=f"{side}_r{round_no}")


def risk_office(runner: Runner, cfg: dict, valuation_md: str, verdict: DebateVerdict) -> RiskReview:
    user = (f"{valuation_md}\n\n## CIO's draft view after the debate\n{verdict.model_dump_json(indent=1)}")
    return runner.structured(system_for("risk", cfg), user, RiskReview, tier="deep", name="risk")


# ------------------------------------------------------------------ independent council
def council_review(runner: Runner, cfg: dict, report_summary: str, on_step=lambda *a: None,
                   seed: int = 7) -> dict:
    question = ("AlaDeen Capital Research has produced the equity research report summarised below. Is it "
                "complete and accurate enough to act on, and should an investor invest at the current price?"
                "\n\n" + report_summary)
    names = list(COUNCIL_ADVISORS)

    def advise(n):
        on_step(f"{n} is reviewing the report")
        return runner.text(system_for("council_advisor", cfg, advisor=n), question, tier="quick",
                           name=f"council:{n}")

    with ThreadPoolExecutor(max_workers=5) as ex:
        responses = dict(zip(names, ex.map(advise, names), strict=True))
    order = names[:]
    random.Random(seed).shuffle(order)
    letters = "ABCDE"
    anon = "\n\n".join(f"**Response {letters[i]}:**\n{responses[n]}" for i, n in enumerate(order))
    on_step("Anonymous peer review of the five opinions")

    def review(i):
        return runner.text(system_for("council_reviewer", cfg), f"{question}\n\n{anon}", tier="quick",
                           name=f"council_review_{i}")

    with ThreadPoolExecutor(max_workers=5) as ex:
        reviews = list(ex.map(review, range(5)))
    on_step("Chair is writing the council verdict")
    chair_user = (f"{question}\n\n## Advisor responses\n" +
                  "\n\n".join(f"**{n}:**\n{responses[n]}" for n in names) +
                  "\n\n## Peer reviews\n" + "\n\n".join(f"Review {i + 1}: {r}" for i, r in enumerate(reviews)))
    verdict = runner.structured(system_for("council_chair", cfg), chair_user, CouncilVerdict, tier="deep",
                                name="council_chair")
    return {"advisors": responses, "anonymised_order": dict(zip(letters, order, strict=True)),
            "reviews": reviews, "verdict": verdict.model_dump()}
