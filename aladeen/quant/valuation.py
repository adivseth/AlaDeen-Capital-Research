"""Valuation engine: WACC, FCFF DCF, sensitivity, justified P/B, Graham, peers, scenarios, rating.

The valuation analyst (an LLM) proposes *assumptions* with reasons. This module does
every calculation. Methodology follows Damodaran (FCFF, stable-growth terminal value
with reinvestment = g / ROC) and Graham (formula value, Graham number, NCAV, defensive
checklist), calibrated for India. See aladeen/knowledge/*.md.
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
    risk_free: float
    beta: float
    erp: float
    cost_of_debt_pre_tax: float
    tax_rate: float
    debt_to_capital: float

    @property
    def cost_of_equity(self) -> float:
        return self.risk_free + self.beta * self.erp

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


DEFAULT_SHIFTS = {
    "bear": ScenarioShift(growth_pp=-0.03, margin_pp=-0.02, wacc_pp=0.01, roe_pp=-0.03),
    "base": ScenarioShift(),
    "bull": ScenarioShift(growth_pp=0.02, margin_pp=0.015, wacc_pp=-0.005, roe_pp=0.02),
}


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
def peer_multiples(peers: list[dict], self_names: list[str]) -> dict:
    names = {n.lower() for n in self_names if n}
    pes, used = [], []
    sector_median = None
    for p in peers:
        nm = (p.get("Company") or "").lower()
        if nm.startswith("median"):
            sector_median = p
            continue
        if not nm or nm in names or any(n.startswith(nm) or nm.startswith(n) for n in names):
            continue
        pe = p.get("P/E")
        if pe is not None and 0 < pe < 150:
            pes.append(pe)
            used.append(p.get("Company"))
    return {"peer_pe_median": statistics.median(pes) if pes else None, "peers_used": used,
            "peer_count": len(pes), "sector_median_row": sector_median}


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
                  financial: bool, roe: float | None = None, bank_growth: float | None = None,
                  dividend_yield: float = 0.0, shifts: dict[str, ScenarioShift] | None = None,
                  graham_inputs: dict | None = None) -> ValuationResult:
    shifts = shifts or DEFAULT_SHIFTS
    w = cfg["dcf_weight"]
    probs = cfg["scenario_probabilities"]
    factors = cfg["scenario_multiple_factors"]
    res = ValuationResult(method="justified_pb" if financial else "fcff_dcf", cmp=cmp_,
                          shares_cr=shares_cr,
                          capital={**asdict(capital), "cost_of_equity": capital.cost_of_equity,
                                   "wacc": capital.wacc},
                          dividend_yield=dividend_yield)
    res.inputs = {"dcf": asdict(dcf_inputs) if dcf_inputs else None, "net_debt": net_debt,
                  "minority": minority, "eps_ttm": eps_ttm, "bvps": bvps, "roe": roe,
                  "bank_growth": bank_growth,
                  "shifts": {k: asdict(v) for k, v in shifts.items()}, "dcf_weight": w}

    mult_price = None
    if peers.get("peer_pe_median") and eps_ttm and eps_ttm > 0:
        mult_price = peers["peer_pe_median"] * eps_ttm
    res.multiples = {**peers, "eps_ttm": eps_ttm, "implied_price": mult_price}
    if mult_price is None:
        res.warnings.append("No usable peer P/E: target uses the intrinsic method only.")
        w = 1.0
    res.inputs["dcf_weight_used"] = w

    intrinsic: dict[str, float] = {}
    if financial:
        if roe is None or bvps is None:
            raise ValueError("Financial-sector valuation needs ROE and book value per share")
        g = min(bank_growth if bank_growth is not None else cfg["terminal_growth_cap"],
                cfg["terminal_growth_cap"])
        res.justified_pb = justified_pb(bvps, roe, g, capital.cost_of_equity)
        for s, sh in shifts.items():
            ke = capital.cost_of_equity + sh.wacc_pp
            intrinsic[s] = justified_pb(bvps, roe + sh.roe_pp, g, ke)["per_share"]
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

    for s in ("bear", "base", "bull"):
        mval = mult_price * factors[s] if mult_price else None
        blended = w * intrinsic[s] + (1 - w) * (mval or 0.0)
        res.scenarios[s] = {"intrinsic": intrinsic[s], "multiples": mval, "value": blended,
                            "probability": probs[s]}
    res.target_price = sum(v["value"] * v["probability"] for v in res.scenarios.values())
    res.upside = res.target_price / cmp_ - 1
    res.total_return = res.upside + dividend_yield
    res.band_rating = rating_from_return(res.total_return, cfg["rating_bands"])
    res.intrinsic_base = res.scenarios["base"]["value"]
    res.margin_of_safety = ((res.intrinsic_base - cmp_) / res.intrinsic_base
                            if res.intrinsic_base > 0 else -1.0)
    res.entry_price_for_mos = res.intrinsic_base * (1 - cfg["margin_of_safety"])
    if res.target_price <= 0:
        res.warnings.append("Target price is not positive: equity value is negative under these inputs.")

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
