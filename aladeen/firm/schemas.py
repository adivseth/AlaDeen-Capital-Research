"""Structured work products exchanged inside the firm."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DeskId = Literal["fundamentals", "business", "governance", "filings", "news", "technical"]


# ------------------------------------------------------------------ CIO
class DeskBrief(BaseModel):
    desk: DeskId
    focus: str = Field(..., description="What this desk must investigate for this company, in 1-3 sentences")


class ResearchMandate(BaseModel):
    """The CIO's opening brief to the team."""

    key_questions: list[str] = Field(..., description="3-6 questions that will decide the investment case")
    briefs: list[DeskBrief] = Field(..., description="One brief per research desk")
    watch_items: list[str] = Field(default_factory=list, description="Data caveats or red flags to watch")


class MemoReview(BaseModel):
    desk: DeskId
    verdict: Literal["accept", "revise"]
    notes: str = Field(..., description="Why accepted, or exactly what must be fixed")
    revisit_value: bool = Field(default=True, description="Could this correction change a valuation assumption?")
    revisit_risk: bool = Field(default=True, description="Could this correction change the thesis or risk assessment?")


class FilingAssessment(BaseModel):
    action: Literal["retain", "revalue", "escalate"]
    desk: DeskId
    reason: str = Field(description="Identify the specific disclosure and explain its impact on the signed thesis.")
    affected_inputs: list[str] = Field(description="Forecast assumptions or risk factors affected by this evidence.")


class DeskReviewSet(BaseModel):
    """The CIO's review of the desk memos."""

    unresolved_material_conflicts: list[str] = Field(default_factory=list, description=(
        "Only specific unresolved factual contradictions that could change valuation or the rating. "
        "Identify both claims, the sources, and the underlying filing or order needed."))
    reviews: list[MemoReview]
    synthesis: str = Field(..., description="What the team's work says so far, in 4-8 sentences")


class DebateVerdict(BaseModel):
    """The CIO's ruling on the bull vs bear debate."""

    lean: Literal["BUY", "HOLD", "SELL"]
    surviving_bull_points: list[str]
    surviving_bear_points: list[str]
    rejected_points: list[str] = Field(default_factory=list)
    kill_fact: str = Field(..., description="The single verifiable fact that would overturn the call")
    why_losing_side_lost: str
    summary: str


# ------------------------------------------------------------------ valuation
class Shift(BaseModel):
    growth_pp: float = Field(0.0, description="Change to every year's revenue growth, decimal (-0.03 = -3pp)")
    margin_pp: float = Field(0.0, description="Change to every year's EBIT margin, decimal")
    wacc_pp: float = Field(0.0, description="Change to WACC / cost of equity, decimal")
    roe_pp: float = Field(0.0, description="Financials only: change to sustainable ROE, decimal")


class ValuationAssumptions(BaseModel):
    """Assumptions proposed by the valuation analyst. Leave a field null to keep the default."""

    revenue_growth: list[float] | None = Field(None, description="5 yearly revenue growth rates, decimals")
    ebit_margin: list[float] | None = Field(None, description="5 yearly EBIT margins, decimals")
    da_pct_revenue: float | None = None
    capex_pct_revenue: float | None = None
    nwc_pct_incremental_revenue: float | None = None
    terminal_growth: float | None = Field(None, description="Stable growth, decimal; capped at nominal GDP")
    stable_roc: float | None = Field(None, description="Return on capital in stable growth, decimal")
    beta: float | None = Field(None, description="Override only with a stated reason")
    cost_of_equity_premium: float | None = Field(
        None, description="Company-specific premium added to the cost of equity, decimal; only with a stated reason")
    sustainable_roe: float | None = Field(
        None, description="Banks/NBFCs/insurers: normalised (terminal) ROE the business can sustain, decimal")
    roe_path: list[float] | None = Field(
        None, description="Banks/NBFCs/insurers: ROE for each of the next 10 years, decimals (shorter lists "
                          "are extended at the sustainable ROE)")
    payout_ratio: float | None = Field(None, description="Banks/NBFCs/insurers: dividend payout ratio, decimal")
    long_term_growth: float | None = Field(None, description="Banks/NBFCs/insurers: terminal growth, decimal")
    bear: Shift = Field(default_factory=lambda: Shift(growth_pp=-0.02, margin_pp=-0.015, wacc_pp=0.005,
                                                      roe_pp=-0.02))
    bull: Shift = Field(default_factory=lambda: Shift(growth_pp=0.02, margin_pp=0.015, wacc_pp=-0.005,
                                                      roe_pp=0.02))
    bear_case_narrative: str = ""
    base_case_narrative: str = ""
    bull_case_narrative: str = ""
    rationale: str = Field(..., description="Why each assumption differs from (or keeps) the default")

    def to_engine(self) -> dict:
        d = self.model_dump(exclude={"bear", "bull", "rationale", "bear_case_narrative",
                                     "base_case_narrative", "bull_case_narrative"})
        d["scenarios"] = {"bear": self.bear.model_dump(), "bull": self.bull.model_dump()}
        if d.get("sustainable_roe") is not None:
            d["terminal_roe"] = d["sustainable_roe"]
        for k in ("revenue_growth", "ebit_margin"):
            v = d.get(k)
            if v is not None and len(v) != 5:
                d[k] = (list(v) + [v[-1]] * 5)[:5] if v else None
        return d


# ------------------------------------------------------------------ risk office
class RiskReview(BaseModel):
    """The Chief Risk Officer's three-lens review of the draft view."""

    aggressive: str = Field(..., description="What would justify a larger position or higher target (3-5 lines)")
    neutral: str = Field(..., description="Is the draft view consistent with valuation and debate (3-5 lines)")
    conservative: str = Field(..., description="Realistic loss in the bear case and a safe entry price (3-5 lines)")
    risk_rating: Literal["Low", "Moderate", "Elevated", "High"]
    recommendation: str = Field(..., description="One-paragraph recommendation to the CIO")


# ------------------------------------------------------------------ CIO decision
class Catalyst(BaseModel):
    catalyst: str
    timeline: str
    impact: str


class RiskItem(BaseModel):
    risk: str
    category: Literal["Market", "Regulatory", "Competitive", "Execution", "Macro", "Management",
                      "Governance", "Financial", "Technology", "ESG", "Other"]
    probability: Literal["Low", "Medium", "High"]
    impact: Literal["Low", "Medium", "High"]
    description_and_mitigant: str


class ESGPillar(BaseModel):
    pillar: Literal["Environmental", "Social", "Governance"]
    assessment: Literal["Above benchmark", "In line", "Below benchmark", "Insufficient data"]
    commentary: str


class FinalCall(BaseModel):
    """The CIO's signed investment decision."""

    rating: Literal["BUY", "HOLD", "SELL"]
    qualifier: str | None = Field(None, description="e.g. 'High Risk', 'Selective'; does not change the band")
    position_size: Literal["Starter", "Full", "Avoid"]
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    headline: str = Field(..., description="One-line investment view")
    executive_summary: str = Field(..., description="2-3 short paragraphs for a non-expert investor")
    thesis_pillars: list[str] = Field(..., description="Three pillars, each one sentence")
    catalysts: list[Catalyst]
    risks: list[RiskItem]
    esg: list[ESGPillar]
    governance_score: Literal["Good", "Satisfactory", "Moderate", "Weak"]
    kill_fact: str
    why_losing_side_lost: str
    rating_rationale: str
    valuation_challenge: str | None = Field(
        None, description="Only if you believe the engine's valuation is wrong: the specific input you dispute "
                          "(e.g. the ROE path, cost of equity, growth) and the evidence. The valuation is re-run once "
                          "with your challenge; the rating then follows the bands.")


# ------------------------------------------------------------------ independent council
class CouncilVerdict(BaseModel):
    where_council_agrees: list[str]
    where_council_clashes: list[str]
    blind_spots: list[str]
    recommendation: str
    verdict: Literal["INVEST", "DO NOT INVEST", "WAIT"]
    one_thing_first: str
    gaps_in_report: list[str] = Field(default_factory=list)
    unresolved_material_conflicts: list[str] = Field(default_factory=list, description=(
        "Contradictory facts that remain unsupported by primary documentation and could change the call. "
        "Identify claims, sources and the primary evidence required."))
    report_complete: bool
