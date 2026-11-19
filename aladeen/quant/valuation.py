"""Valuation engine: WACC, FCFF DCF, residual income (banks), sensitivity, Graham, peers, scenarios, rating.

The valuation analyst (an LLM) proposes *assumptions* with reasons. This module does
every calculation. Methodology follows Damodaran (FCFF with stable-growth terminal value
and reinvestment = g / ROC; excess-return / residual-income model for banks, NBFCs and
insurers) and Graham (formula value, Graham number, NCAV, defensive checklist),
calibrated for India. See aladeen/knowledge/*.md.

Cost of equity: when the equity risk premium is a *total* country ERP (Damodaran's India
figure already contains the country risk premium), the INR risk-free rate is the G-Sec
yield less the sovereign default spread; otherwise country risk is counted twice.

The 12-month target rolls today's value forward one year at the cost of equity, less the
dividend paid. A stock priced at fair value is therefore expected to return its cost of
equity, not zero.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


# --------------------------------------------------------------------------- inputs
@dataclass
class DCFInputs:
    base_revenue: float  # last full-year revenue, Rs Cr
    revenue_growth: list[float]  # 5 explicit years, decimals
    ebit_margin: list[float]  # 5 explicit years, decimals
    tax_rate: float
    da_pct_revenue: float
    capex_pct_revenue: float
    nwc_pct_incremental_revenue: float
    terminal_growth: float
    stable_roc: float  # return on capital in stable growth (sets terminal reinvestment)

    def shifted(self, growth_pp: float = 0.0, margin_pp: float = 0.0) -> DCFInputs:
        d = asdict(self)
        d["revenue_growth"] = [g + growth_pp for g in self.revenue_growth]
        d["ebit_margin"] = [max(m + margin_pp, -0.5) for m in self.ebit_margin]
        return DCFInputs(**d)


@dataclass
class CapitalInputs:
    risk_free: float  # G-Sec yield
    beta: float
    erp: float
    cost_of_debt_pre_tax: float
    tax_rate: float
    debt_to_capital: float
    default_spread: float = 0.0  # sovereign default spread netted off the G-Sec yield
    premium: float = 0.0  # company-specific premium, only with a stated reason

    @property
    def riskless_rate(self) -> float:
        return self.risk_free - self.default_spread

    @property
    def cost_of_equity(self) -> float:
        return self.riskless_rate + self.beta * self.erp + self.premium

    @property
    def wacc(self) -> float:
        kd_post = self.cost_of_debt_pre_tax * (1 - self.tax_rate)
        return self.cost_of_equity * (1 - self.debt_to_capital) + kd_post * self.debt_to_capital


@dataclass
class ScenarioShift:
    growth_pp: float = 0.0
    margin_pp: float = 0.0
    wacc_pp: float = 0.0
    roe_pp: float = 0.0  # financials only


# Symmetric by default: the bear and bull cases move each driver by the same amount.
DEFAULT_SHIFTS = {
    "bear": ScenarioShift(growth_pp=-0.02, margin_pp=-0.015, wacc_pp=0.005, roe_pp=-0.02),
    "base": ScenarioShift(),
    "bull": ScenarioShift(growth_pp=0.02, margin_pp=0.015, wacc_pp=-0.005, roe_pp=0.02),
}


@dataclass
class BankInputs:
    """Inputs to the residual-income model. ROE path and payout are decimals."""

    bv0_cr: float  # net worth at the latest balance-sheet date, Rs Cr
    bv_date: str
    roe_path: list[float]  # explicit years, starting the year after bv_date
    terminal_roe: float
    payout: float  # dividend payout ratio over the explicit years
    terminal_growth: float

    def shifted(self, roe_pp: float = 0.0) -> BankInputs:
        d = asdict(self)
        d["roe_path"] = [r + roe_pp for r in self.roe_path]
        d["terminal_roe"] = self.terminal_roe + roe_pp
        return BankInputs(**d)


def default_roe_path(roe_now: float, roe_term: float, years: int = 10, fade: int = 5) -> list[float]:
    """Linear fade from the current ROE to the normalised ROE over ``fade`` years, then flat."""
    fade = max(1, min(fade, years))
    return [round(roe_now + (roe_term - roe_now) * min(t, fade) / fade, 4) for t in range(1, years + 1)]


# --------------------------------------------------------------------------- DCF
def dcf_fcff(inp: DCFInputs, wacc: float, net_debt: float, minority: float, shares_cr: float) -> dict:
    if wacc <= inp.terminal_growth:
        raise ValueError(f"WACC {wacc:.2%} must exceed terminal growth {inp.terminal_growth:.2%}")
    rows = []
    rev_prev = inp.base_revenue
    pv_sum = 0.0
    for t, (g, m) in enumerate(zip(inp.revenue_growth, inp.ebit_margin, strict=True), start=1):
        rev = rev_prev * (1 + g)
        ebit = rev * m
        nopat = ebit * (1 - inp.tax_rate)
        da = rev * inp.da_pct_revenue
        capex = rev * inp.capex_pct_revenue
        dnwc = (rev - rev_prev) * inp.nwc_pct_incremental_revenue
        fcff = nopat + da - capex - dnwc
        df = 1 / (1 + wacc) ** t
        pv_sum += fcff * df
        rows.append({"year": t, "revenue": rev, "growth": g, "ebit": ebit, "ebit_margin": m,
                     "nopat": nopat, "da": da, "capex": capex, "delta_nwc": dnwc, "fcff": fcff,
                     "discount_factor": df, "pv_fcff": fcff * df})
        rev_prev = rev
    # Terminal value: NOPAT_{n+1} x (1 - g / ROC_stable) / (WACC - g)
    nopat_next = rows[-1]["nopat"] * (1 + inp.terminal_growth)
    reinvest_rate = inp.terminal_growth / inp.stable_roc if inp.stable_roc > 0 else 0.0
    fcff_next = nopat_next * (1 - reinvest_rate)
    tv = fcff_next / (wacc - inp.terminal_growth)
    pv_tv = tv * rows[-1]["discount_factor"]
    ev = pv_sum + pv_tv
    equity = ev - net_debt - minority
    return {
        "projections": rows,
        "pv_explicit": pv_sum,
        "terminal_value": tv,
        "pv_terminal": pv_tv,
        "terminal_reinvestment_rate": reinvest_rate,
        "enterprise_value": ev,
        "net_debt": net_debt,
        "minority_interest": minority,
        "equity_value": equity,
        "shares_cr": shares_cr,
        "per_share": equity / shares_cr if shares_cr else None,
        "tv_share_of_ev": pv_tv / ev if ev else None,
        "wacc": wacc,
    }


def sensitivity(inp: DCFInputs, wacc: float, net_debt: float, minority: float, shares_cr: float,
                wacc_step: float = 0.01, g_step: float = 0.005, n: int = 2) -> dict:
    waccs = [round(wacc + i * wacc_step, 4) for i in range(-n, n + 1)]
    gs = [round(inp.terminal_growth + i * g_step, 4) for i in range(-n, n + 1)]
    grid = []
    for g in gs:
        row = []
        for w in waccs:
            if w <= g + 0.005:
                row.append(None)
                continue
            d = asdict(inp)
            d["terminal_growth"] = g
            row.append(dcf_fcff(DCFInputs(**d), w, net_debt, minority, shares_cr)["per_share"])
        grid.append(row)
    return {"wacc": waccs, "terminal_growth": gs, "values": grid}


# --------------------------------------------------------------------------- financials
def residual_income(inp: BankInputs, ke: float, shares_cr: float) -> dict:
    """Excess-return model: equity = BV0 + sum PV[(ROE_t - Ke) x BV_{t-1}] + PV(terminal RI).

    Terminal RI = (ROE_T - Ke) x BV_n / (Ke - g), discounted from the end of year n.
    Book value grows by retained profit: BV_t = BV_{t-1} x (1 + ROE_t x (1 - payout)).
    """
    if ke <= inp.terminal_growth:
        raise ValueError(f"Cost of equity {ke:.2%} must exceed terminal growth {inp.terminal_growth:.2%}")
    rows, bv, pv = [], inp.bv0_cr, 0.0
    for t, roe in enumerate(inp.roe_path, start=1):
        ni = roe * bv
        ri = (roe - ke) * bv
        df = 1 / (1 + ke) ** t
        pv += ri * df
        rows.append({"year": t, "bv_open": bv, "roe": roe, "net_income": ni, "dividend": ni * inp.payout,
                     "residual_income": ri, "discount_factor": df, "pv_ri": ri * df})
        bv = bv + ni * (1 - inp.payout)
    df_n = rows[-1]["discount_factor"] if rows else 1.0
    tv = (inp.terminal_roe - ke) * bv / (ke - inp.terminal_growth)
    pv_tv = tv * df_n
    equity = inp.bv0_cr + pv + pv_tv
    return {
        "projections": rows, "bv0": inp.bv0_cr, "bv_date": inp.bv_date, "pv_explicit_ri": pv,
        "terminal_ri": tv, "pv_terminal": pv_tv, "bv_end": bv, "equity_value": equity,
        "shares_cr": shares_cr, "per_share": equity / shares_cr if shares_cr else None,
        "implied_pb": equity / inp.bv0_cr if inp.bv0_cr else None,
        "tv_share_of_value": pv_tv / equity if equity else None,
        "dps_year1": rows[0]["dividend"] / shares_cr if rows and shares_cr else 0.0,
        "bvps0": inp.bv0_cr / shares_cr if shares_cr else None,
        "cost_of_equity": ke, "terminal_roe": inp.terminal_roe, "terminal_growth": inp.terminal_growth,
        "payout": inp.payout,
    }


def implied_roe(price: float, inp: BankInputs, ke: float, shares_cr: float) -> float | None:
    """Flat ROE (every year and terminal) at which the residual-income value equals the price."""
    def gap(r: float) -> float:
        flat = BankInputs(**{**asdict(inp), "roe_path": [r] * len(inp.roe_path), "terminal_roe": r})
        return residual_income(flat, ke, shares_cr)["per_share"] - price

    lo, hi = -0.10, 0.60
    if gap(lo) > 0 or gap(hi) < 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gap(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def bank_sensitivity(inp: BankInputs, ke: float, shares_cr: float, ke_step: float = 0.005,
                     roe_step: float = 0.01, n: int = 2) -> dict:
    kes = [round(ke + i * ke_step, 4) for i in range(-n, n + 1)]
    roes = [round(inp.terminal_roe + i * roe_step, 4) for i in range(-n, n + 1)]
    grid = []
    for r in roes:
        row = []
        for k in kes:
            if k <= inp.terminal_growth + 0.005:
                row.append(None)
                continue
            shifted = inp.shifted(r - inp.terminal_roe)
            row.append(residual_income(shifted, k, shares_cr)["per_share"])
        grid.append(row)
    return {"cost_of_equity": kes, "terminal_roe": roes, "values": grid}


def historical_pb(prices: pd.DataFrame, bvps_by_fy: pd.Series, years: int = 5) -> dict:
    """Price / book at each fiscal year-end (31 March) over the last ``years`` years."""
    out = []
    if prices is None or prices.empty or bvps_by_fy is None or "close" not in prices:
        return {"points": [], "median": None}
    close = prices["close"].dropna()
    for label, bv in bvps_by_fy.dropna().items():
        if not str(label).startswith("FY") or not bv or bv <= 0:
            continue
        fy_end = pd.Timestamp(f"20{str(label)[2:4]}-03-31")
        px = close[close.index <= fy_end]
        if px.empty or (fy_end - px.index[-1]).days > 10:
            continue
        out.append({"fy": label, "price": float(px.iloc[-1]), "bvps": float(bv), "pb": float(px.iloc[-1] / bv)})
    out = out[-years:]
    return {"points": out, "median": statistics.median(p["pb"] for p in out) if out else None}


def justified_pb(bvps: float, roe: float, growth: float, cost_of_equity: float) -> dict:
    """Gordon-based justified P/B = (ROE - g) / (Ke - g). Used for banks / NBFCs / insurers."""
    if cost_of_equity <= growth:
        raise ValueError("Cost of equity must exceed growth")
    pb = (roe - growth) / (cost_of_equity - growth)
    return {"justified_pb": pb, "per_share": max(pb, 0) * bvps, "roe": roe, "growth": growth,
            "cost_of_equity": cost_of_equity, "bvps": bvps}


# --------------------------------------------------------------------------- Graham
def graham_number(eps: float | None, bvps: float | None) -> float | None:
    if not eps or not bvps or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(22.5 * eps * bvps)


def graham_formula(eps: float | None, growth_pct: float, aaa_yield_pct: float) -> float | None:
    """V = EPS x (8.5 + 2g) x 4.4 / Y, with g and Y in percent (Y = Indian AAA / G-Sec yield)."""
    if not eps or eps <= 0 or aaa_yield_pct <= 0:
        return None
    return eps * (8.5 + 2 * growth_pct) * 4.4 / aaa_yield_pct


def ncav_per_share(current_assets_cr: float | None, total_liabilities_cr: float | None,
                   shares_cr: float) -> float | None:
    if current_assets_cr is None or total_liabilities_cr is None or not shares_cr:
        return None
    return (current_assets_cr - total_liabilities_cr) / shares_cr


def graham_checklist(annual: pd.DataFrame, cmp_: float, current_ratio: float | None) -> list[dict]:
    """Graham's defensive-investor tests, adapted for India (10-year dividend record)."""
    out = []

    def add(criterion, value, passed, note=""):
        out.append({"criterion": criterion, "value": value,
                    "pass": None if passed is None else bool(passed), "note": note})

    def last(col):
        s = annual.get(col)
        return None if s is None or not s.notna().any() else float(s.dropna().iloc[-1])

    rev = last("Revenue")
    add("Adequate size (revenue > Rs 500 Cr)", f"Rs {rev:,.0f} Cr" if rev else "n/a",
        None if rev is None else rev > 500)
    add("Strong financial condition (current ratio >= 2.0)",
        f"{current_ratio:.2f}" if current_ratio else "n/a",
        None if current_ratio is None else current_ratio >= 2.0)
    eps = annual.get("EPS")
    e10 = eps.dropna().tail(10) if eps is not None else pd.Series(dtype=float)
    add("Earnings stability (positive EPS in each of last 10 years)",
        f"{int((e10 > 0).sum())}/{len(e10)} years positive",
        bool(len(e10) >= 10 and (e10 > 0).all()) if len(e10) else None,
        "" if len(e10) >= 10 else "fewer than 10 years of data")
    pay = annual.get("Dividend Payout %")
    p10 = pay.dropna().tail(10) if pay is not None else pd.Series(dtype=float)
    add("Dividend record (paid in each of last 10 years)", f"{int((p10 > 0).sum())}/{len(p10)} years",
        bool(len(p10) >= 10 and (p10 > 0).all()) if len(p10) else None)
    growth = None
    if len(e10) >= 10:
        first3, last3 = e10.iloc[:3].mean(), e10.iloc[-3:].mean()
        growth = last3 / first3 - 1 if first3 > 0 else None
    add("Earnings growth (+33% in 3-yr avg EPS over the decade)",
        f"{growth * 100:+.0f}%" if growth is not None else "n/a",
        None if growth is None else growth >= 0.33,
        "" if len(e10) >= 10 else "fewer than 10 years of data")
    avg3 = e10.tail(3).mean() if len(e10) >= 3 else None
    pe3 = cmp_ / avg3 if avg3 and avg3 > 0 else None
    add("Moderate P/E (<= 15x 3-year average EPS)", f"{pe3:.1f}x" if pe3 else "n/a",
        None if pe3 is None else pe3 <= 15)
    bv = last("BVPS")
    pb = cmp_ / bv if bv and bv > 0 else None
    prod = pe3 * pb if pe3 and pb else None
    add("Moderate P/E x P/B (<= 22.5)", f"{prod:.1f}" if prod else "n/a",
        None if prod is None else prod <= 22.5)
    return out


# --------------------------------------------------------------------------- peers
def _is_self(p: dict, names: set[str], slugs: set[str]) -> bool:
    nm = (p.get("Company") or "").lower()
    if not nm or nm in names or any(n.startswith(nm) or nm.startswith(n) for n in names):
        return True
    url = (p.get("url") or "").lower()
    return any(f"/company/{s}/" in url for s in slugs)


def peer_multiples(peers: list[dict], self_names: list[str], market_cap_cr: float | None = None,
                   size_band: float = 0.25) -> dict:
    """Median peer P/E, excluding the company itself and, when market caps are known, peers smaller
    than ``size_band`` x or larger than 1/``size_band`` x the company."""
    names = {n.lower() for n in self_names if n}
    slugs = {n.lower() for n in self_names if n and " " not in n}
    pes, used, dropped = [], [], []
    sector_median = None
    for p in peers:
        nm = (p.get("Company") or "").lower()
        if nm.startswith("median"):
            sector_median = p
            continue
        if _is_self(p, names, slugs):
            continue
        cap = p.get("Mar Cap Rs.Cr.")
        if market_cap_cr and cap and not (size_band * market_cap_cr <= cap <= market_cap_cr / size_band):
            dropped.append(p.get("Company"))
            continue
        pe = p.get("P/E")
        if pe is not None and 0 < pe < 150:
            pes.append(pe)
            used.append(p.get("Company"))
    return {"peer_pe_median": statistics.median(pes) if pes else None, "peers_used": used,
            "peer_count": len(pes), "peers_dropped_for_size": dropped, "sector_median_row": sector_median}


# --------------------------------------------------------------------------- rating
def rating_from_return(total_return: float, bands: dict) -> str:
    if total_return > bands["buy"]:
        return "BUY"
    if total_return >= bands["sell"]:
        return "HOLD"
    return "SELL"


# --------------------------------------------------------------------------- orchestration
@dataclass
class ValuationResult:
    method: str
    cmp: float
    shares_cr: float
    capital: dict
    dcf: dict | None = None
    sensitivity: dict | None = None
    justified_pb: dict | None = None
    residual_income: dict | None = None
    implied_roe_at_cmp: float | None = None
    value_today: float = 0.0  # probability-weighted value today, before the 12-month roll-forward
    reality_check: dict = field(default_factory=dict)
    multiples: dict = field(default_factory=dict)
    scenarios: dict = field(default_factory=dict)
    target_price: float = 0.0
    upside: float = 0.0
    dividend_yield: float = 0.0
    total_return: float = 0.0
    band_rating: str = "HOLD"
    intrinsic_base: float = 0.0
    margin_of_safety: float = 0.0
    entry_price_for_mos: float = 0.0
    graham: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def run_valuation(*, cmp_: float, shares_cr: float, capital: CapitalInputs, cfg: dict,
                  dcf_inputs: DCFInputs | None, net_debt: float, minority: float,
                  eps_ttm: float | None, bvps: float | None, peers: dict,
                  financial: bool, bank_inputs: BankInputs | None = None, pb_anchor: dict | None = None,
                  dividend_yield: float = 0.0, shifts: dict[str, ScenarioShift] | None = None,
                  graham_inputs: dict | None = None, consensus: dict | None = None) -> ValuationResult:
    shifts = shifts or DEFAULT_SHIFTS
    w = cfg["dcf_weight"]
    probs = cfg["scenario_probabilities"]
    factors = cfg["scenario_multiple_factors"]
    ke = capital.cost_of_equity
    res = ValuationResult(method="residual_income" if financial else "fcff_dcf", cmp=cmp_,
                          shares_cr=shares_cr,
                          capital={**asdict(capital), "riskless_rate": capital.riskless_rate,
                                   "cost_of_equity": ke, "wacc": None if financial else capital.wacc},
                          dividend_yield=dividend_yield)
    res.inputs = {"dcf": asdict(dcf_inputs) if dcf_inputs else None,
                  "bank": asdict(bank_inputs) if bank_inputs else None, "net_debt": net_debt,
                  "minority": minority, "eps_ttm": eps_ttm, "bvps": bvps,
                  "shifts": {k: asdict(v) for k, v in shifts.items()}, "dcf_weight": w}

    # Relative leg: banks use the company's own median P/B over five fiscal year-ends (book is the
    # anchor for a lender); others use the median P/E of size-comparable peers.
    mult_price = None
    if financial:
        pba = (pb_anchor or {}).get("median")
        if pba and bvps:
            mult_price = pba * bvps
        res.multiples = {**peers, "eps_ttm": eps_ttm, "basis": "own 5-year median P/B x latest book",
                         "pb_anchor": pba, "pb_history": (pb_anchor or {}).get("points", []), "bvps": bvps,
                         "implied_price": mult_price}
        if mult_price is None:
            res.warnings.append("No P/B history: target uses the residual-income value only.")
    else:
        if peers.get("peer_pe_median") and eps_ttm and eps_ttm > 0:
            mult_price = peers["peer_pe_median"] * eps_ttm
        res.multiples = {**peers, "eps_ttm": eps_ttm, "basis": "median P/E of size-comparable peers x TTM EPS",
                         "implied_price": mult_price}
        if mult_price is None:
            res.warnings.append("No usable peer P/E: target uses the intrinsic method only.")
    if mult_price is None:
        w = 1.0
    res.inputs["dcf_weight_used"] = w

    intrinsic: dict[str, float] = {}
    dps1 = cmp_ * dividend_yield
    if financial:
        if bank_inputs is None:
            raise ValueError("Financial-sector valuation needs book value and an ROE path")
        g_cap = cfg["terminal_growth_cap"]
        if bank_inputs.terminal_growth > g_cap:
            res.warnings.append(f"Terminal growth capped at {g_cap:.1%} (nominal GDP proxy).")
            bank_inputs.terminal_growth = g_cap
            res.inputs["bank"] = asdict(bank_inputs)
        base = residual_income(bank_inputs, ke, shares_cr)
        res.residual_income = base
        dps1 = base["dps_year1"] or dps1
        res.sensitivity = bank_sensitivity(bank_inputs, ke, shares_cr)
        res.justified_pb = justified_pb(bvps or base["bvps0"], bank_inputs.terminal_roe,
                                        bank_inputs.terminal_growth, ke)
        res.implied_roe_at_cmp = implied_roe(cmp_, bank_inputs, ke, shares_cr)
        if base["tv_share_of_value"] and base["tv_share_of_value"] > cfg["tv_share_warning"]:
            res.warnings.append(f"Terminal value is {base['tv_share_of_value']:.0%} of equity value.")
        for s, sh in shifts.items():
            intrinsic[s] = residual_income(bank_inputs.shifted(sh.roe_pp), ke + sh.wacc_pp,
                                           shares_cr)["per_share"]
    else:
        if dcf_inputs is None:
            raise ValueError("Non-financial valuation needs DCF inputs")
        g_cap = cfg["terminal_growth_cap"]
        if dcf_inputs.terminal_growth > g_cap:
            res.warnings.append(f"Terminal growth capped at {g_cap:.1%} (nominal GDP proxy).")
            dcf_inputs.terminal_growth = g_cap
            res.inputs["dcf"] = asdict(dcf_inputs)
        base = dcf_fcff(dcf_inputs, capital.wacc, net_debt, minority, shares_cr)
        res.dcf = base
        res.sensitivity = sensitivity(dcf_inputs, capital.wacc, net_debt, minority, shares_cr)
        if base["tv_share_of_ev"] and base["tv_share_of_ev"] > cfg["tv_share_warning"]:
            res.warnings.append(
                f"Terminal value is {base['tv_share_of_ev']:.0%} of enterprise value: the valuation "
                "depends heavily on long-run assumptions.")
        for s, sh in shifts.items():
            inp = dcf_inputs.shifted(sh.growth_pp, sh.margin_pp)
            intrinsic[s] = dcf_fcff(inp, capital.wacc + sh.wacc_pp, net_debt, minority,
                                    shares_cr)["per_share"]

    # Values today, then the 12-month target: value x (1 + Ke) less the year-1 dividend.
    roll = cfg.get("roll_forward_target", True)
    for s in ("bear", "base", "bull"):
        mval = mult_price * factors[s] if mult_price else None
        today = w * intrinsic[s] + (1 - w) * (mval or 0.0)
        value_12m = today * (1 + ke) - dps1 if roll else today
        res.scenarios[s] = {"intrinsic": intrinsic[s], "multiples": mval, "value_today": today,
                            "value": value_12m, "probability": probs[s]}
    res.value_today = sum(v["value_today"] * v["probability"] for v in res.scenarios.values())
    res.target_price = sum(v["value"] * v["probability"] for v in res.scenarios.values())
    res.upside = res.target_price / cmp_ - 1
    res.total_return = res.upside + dividend_yield
    res.band_rating = rating_from_return(res.total_return, cfg["rating_bands"])
    res.inputs["roll_forward"] = {"applied": roll, "cost_of_equity": ke, "dps_year1": dps1}
    res.intrinsic_base = res.scenarios["base"]["value_today"]
    res.margin_of_safety = ((res.intrinsic_base - cmp_) / res.intrinsic_base
                            if res.intrinsic_base > 0 else -1.0)
    res.entry_price_for_mos = res.intrinsic_base * (1 - cfg["margin_of_safety"])
    if res.target_price <= 0:
        res.warnings.append("Target price is not positive: equity value is negative under these inputs.")
    res.reality_check = reality_check(res, cfg, consensus)
    if res.reality_check.get("flag"):
        res.warnings.append(res.reality_check["message"])

    gi = graham_inputs or {}
    aaa = gi.get("aaa_yield_pct", cfg["risk_free_rate"] * 100)
    res.graham = {
        "graham_number": graham_number(eps_ttm, bvps),
        "graham_formula_value": graham_formula(eps_ttm, gi.get("growth_pct", 0.0), aaa),
        "graham_growth_pct": gi.get("growth_pct"),
        "aaa_yield_pct": aaa,
        "ncav_per_share": gi.get("ncav_per_share"),
        "checklist": gi.get("checklist", []),
    }
    return res


def reality_check(res: ValuationResult, cfg: dict, consensus: dict | None = None) -> dict:
    """Flag a target far from both the market price and (when known) the broker consensus.

    A large gap is allowed, but it must be explained: the CIO is asked to justify or revise it.
    """
    limit = cfg.get("reality_check_threshold", 0.25)
    vs_price = res.target_price / res.cmp - 1 if res.cmp else None
    cons = (consensus or {}).get("target_mean")
    vs_cons = res.target_price / cons - 1 if cons else None
    far_price = vs_price is not None and abs(vs_price) > limit
    far_cons = vs_cons is None or abs(vs_cons) > limit
    flag = bool(far_price and far_cons)
    parts = [f"target {res.target_price:,.0f} is {vs_price:+.0%} vs CMP {res.cmp:,.0f}"] if vs_price is not None else []
    if vs_cons is not None:
        parts.append(f"{vs_cons:+.0%} vs consensus {cons:,.0f} ({(consensus or {}).get('analysts') or 'n/a'} analysts)")
    else:
        parts.append("no broker consensus in the fact pack")
    if res.implied_roe_at_cmp is not None:
        parts.append(f"the price implies a steady ROE of {res.implied_roe_at_cmp:.1%} at Ke "
                     f"{res.capital['cost_of_equity']:.1%}")
    msg = ("Reality check: " + "; ".join(parts) + "." +
           (f" The gap exceeds {limit:.0%}: explain why the market is wrong, or revise the inputs." if flag else ""))
    return {"flag": flag, "threshold": limit, "vs_price": vs_price, "vs_consensus": vs_cons,
            "consensus": consensus or {}, "implied_roe_at_cmp": res.implied_roe_at_cmp, "message": msg}


def default_dcf_inputs(annual: pd.DataFrame, cfg: dict, horizon: int = 5) -> DCFInputs:
    """History-based starting assumptions. The valuation analyst may override each one."""
    a = annual.dropna(subset=["Revenue"])
    rev = a["Revenue"]
    base = float(rev.iloc[-1])
    g5 = None
    if len(rev) >= 6 and rev.iloc[-6] > 0:
        g5 = float((rev.iloc[-1] / rev.iloc[-6]) ** (1 / 5) - 1)
    g_start = min(max(g5 if g5 is not None else 0.08, 0.0), 0.25)
    g_term = min(cfg["terminal_growth_cap"], 0.05)
    growth = [g_start + (g_term - g_start) * i / horizon for i in range(horizon)]

    def avg_ratio(num: str, den: str = "Revenue", n: int = 3, default: float = 0.0) -> float:
        if num not in a or den not in a:
            return default
        r = (a[num] / a[den]).dropna().tail(n)
        return float(r.mean()) if len(r) else default

    margin = avg_ratio("EBIT", default=0.12)
    return DCFInputs(
        base_revenue=base,
        revenue_growth=[round(x, 4) for x in growth],
        ebit_margin=[round(margin, 4)] * horizon,
        tax_rate=cfg["tax_rate"],
        da_pct_revenue=round(avg_ratio("D&A", default=0.03), 4),
        capex_pct_revenue=round(avg_ratio("Capex", default=0.04), 4),
        nwc_pct_incremental_revenue=0.10,
        terminal_growth=g_term,
        stable_roc=max(cfg["risk_free_rate"] + cfg["equity_risk_premium"] + 0.02, 0.12),
    )


def as_float(x: Any) -> float | None:
    try:
        f = float(x)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None
