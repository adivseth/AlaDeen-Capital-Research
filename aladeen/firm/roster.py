"""Who works at AlaDeen Capital Research, where they sit, and the stages of a research mandate."""

from __future__ import annotations

ROSTER: list[dict] = [
    {"id": "cio", "title": "Chief Investment Officer", "short": "CIO", "room": "executive", "icon": "🧭",
     "color": "#4f46e5", "tier": "senior",
     "role": "Leads the firm. Sets the research mandate, briefs every desk, reviews their memos, rules on the "
             "debate and signs the final investment decision."},
    {"id": "data", "title": "Data & Quant Desk", "short": "Quant", "room": "lab", "icon": "🗄️",
     "color": "#0891b2", "tier": "system",
     "role": "Collects statements, prices, filings and news; reconciles every figure; computes ratios, "
             "technicals and charts. Pure code: no language model."},
    {"id": "fundamentals", "title": "Financial Statements Analyst", "short": "Financials", "room": "floor",
     "icon": "📊", "color": "#2563eb", "tier": "analyst",
     "role": "Earnings quality, margins, cash conversion, working capital, balance sheet and red flags."},
    {"id": "business", "title": "Sector & Strategy Analyst", "short": "Sector", "room": "floor", "icon": "🏭",
     "color": "#7c3aed", "tier": "analyst",
     "role": "Business model, segments, competitive position, moat and industry structure."},
    {"id": "governance", "title": "Governance & ESG Analyst", "short": "Governance", "room": "floor",
     "icon": "⚖️", "color": "#db2777", "tier": "analyst",
     "role": "Promoters, dilution, related parties, auditors, board, capital allocation and ESG."},
    {"id": "filings", "title": "Filings & Earnings-Call Analyst", "short": "Filings", "room": "floor",
     "icon": "📑", "color": "#ea580c", "tier": "analyst",
     "role": "Reads annual reports and concall transcripts: guidance, delivery against guidance, tone."},
    {"id": "news", "title": "Market Intelligence Analyst", "short": "Intel", "room": "floor", "icon": "📰",
     "color": "#0d9488", "tier": "analyst",
     "role": "News flow, exchange announcements, catalysts and the short-term check."},
    {"id": "technical", "title": "Technical Strategist", "short": "Technicals", "room": "floor", "icon": "📈",
     "color": "#16a34a", "tier": "analyst",
     "role": "Ten years of price action: trend, momentum, levels and entry timing."},
    {"id": "valuation", "title": "Valuation Analyst", "short": "Valuation", "room": "lab", "icon": "🧮",
     "color": "#0f766e", "tier": "senior",
     "role": "Sets DCF / justified P/B assumptions and scenarios; the engine does every calculation."},
    {"id": "bull", "title": "Bull Advocate", "short": "Bull", "room": "debate", "icon": "🐂", "color": "#16a34a",
     "tier": "analyst", "role": "Argues the strongest honest case for owning the stock."},
    {"id": "bear", "title": "Bear Advocate", "short": "Bear", "room": "debate", "icon": "🐻", "color": "#dc2626",
     "tier": "analyst", "role": "Argues the strongest honest case against it, starting with governance."},
    {"id": "risk", "title": "Chief Risk Officer", "short": "CRO", "room": "risk", "icon": "🛡️", "color": "#b45309",
     "tier": "senior",
     "role": "Stress-tests the draft view through aggressive, neutral and conservative lenses."},
    {"id": "compliance", "title": "Compliance Officer", "short": "Compliance", "room": "risk", "icon": "✅",
     "color": "#475569", "tier": "system",
     "role": "Audits every number against the data, enforces the rating bands and the disclosures. Code only."},
    {"id": "council", "title": "Independent Council", "short": "Council", "room": "council", "icon": "🏛️",
     "color": "#9333ea", "tier": "analyst",
     "role": "Five outside advisors review the signed report, peer-review each other and give a verdict."},
    {"id": "editor", "title": "Publishing Editor", "short": "Editor", "room": "publishing", "icon": "🖨️",
     "color": "#1d4ed8", "tier": "system", "role": "Typesets the final report and files it in the archive."},
]

ROOMS: list[dict] = [
    {"id": "executive", "title": "Executive Suite"},
    {"id": "floor", "title": "Research Floor"},
    {"id": "lab", "title": "Valuation Lab"},
    {"id": "debate", "title": "Debate Room"},
    {"id": "risk", "title": "Risk & Compliance"},
    {"id": "council", "title": "Council Chamber"},
    {"id": "publishing", "title": "Publishing"},
]

PHASES: list[dict] = [
    {"id": "data", "title": "Data collection"},
    {"id": "mandate", "title": "CIO mandate"},
    {"id": "desks", "title": "Desk research"},
    {"id": "review", "title": "CIO review"},
    {"id": "valuation", "title": "Valuation"},
    {"id": "debate", "title": "Bull vs bear"},
    {"id": "risk", "title": "Risk office"},
    {"id": "decision", "title": "CIO decision"},
    {"id": "compliance", "title": "Compliance"},
    {"id": "council", "title": "Independent council"},
    {"id": "publish", "title": "Publication"},
]

TITLES = {a["id"]: a["title"] for a in ROSTER}


def roster_payload() -> dict:
    return {"agents": ROSTER, "rooms": ROOMS, "phases": PHASES}
