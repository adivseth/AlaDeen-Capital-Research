# Sector-Specific Valuation Reference
## Source: Damodaran – Investment Valuation (Chapters 21–24)

---

## Table of Contents
1. [Financial Service Firms (Banks, NBFCs)](#1-financial-service-firms-banks-nbfcs)
2. [Asset Management Companies (AMCs)](#2-asset-management-companies-amcs)
3. [Negative Earnings Firms](#3-negative-earnings-firms)
4. [Young / Start-up Firms](#4-young--start-up-firms)
5. [Private Firms](#5-private-firms)
6. [Cyclical Firms](#6-cyclical-firms)
7. [Real Estate](#7-real-estate)
8. [Infrastructure / Utilities](#8-infrastructure--utilities)
9. [Pharma / Biotech](#9-pharma--biotech)

---

## 1. Financial Service Firms (Banks, NBFCs)

**Damodaran: Ch. 21 — "The definition of debt changes for financial service firms."**

### Why standard DCF doesn't work
- Debt is a raw material (deposits are liabilities that generate assets = loans)
- FCFF is not meaningful; FCFE is used directly
- Regulatory capital constraints limit growth
- Interest income and expense are both operational (cannot separate financing from operations)

### Recommended Approach: Excess Return Model or Dividend Discount Model

**Approach 1: DDM (preferred for stable banks)**
```
Value = DPS_1 / (Ke – g)    (Gordon Growth, for stable bank)

DPS_1 = EPS × Payout Ratio = ROE × BV × Payout Ratio

g_sustainable = ROE × (1 – Payout Ratio)

Check: If g > Ke → unsustainable; reduce g to Ke – margin
```

**Approach 2: P/B vs. ROE (Relative)**
```
P/B = (ROE – g) / (Ke – g)

Banks with ROE = 18%, Ke = 12%, g = 12% → P/B = 6/0 = undefined
(Very high growth bank commands very high P/B → danger zone)

Practical rule:
  P/B ~ ROE / Ke  (rough and ready for quick screen)
  
  If ROE = 15%, Ke = 12% → Fair P/B ≈ 1.25×
  If ROE = 18%, Ke = 12% → Fair P/B ≈ 1.5×
  If ROE = 25%, Ke = 12% → Fair P/B ≈ 2.1×
```

### Key Metrics for Banks (India)
```
Net Interest Margin (NIM) = Net Interest Income / Average Interest-Earning Assets
CASA Ratio                = (Current + Savings Deposits) / Total Deposits
Gross NPA Ratio           = Gross NPA / Gross Advances
Net NPA Ratio             = Net NPA / Net Advances
Credit Cost               = Provisions / Average Loans
Return on Assets (RoA)    = PAT / Average Assets
Return on Equity (RoE)    = PAT / Average Net Worth
Tier 1 Capital Ratio      = Tier 1 Capital / Risk-Weighted Assets (RBI min: 8.5%)
PCR (Provision Coverage)  = Provisions / Gross NPAs
```

**P/ABV (Price-to-Adjusted Book Value):**
```
ABV = Book Value – Net NPA × (1 – PCR)
     (Adjusted for credit risk in loan book)

Compare P/ABV to ROA/ROE to determine premium/discount
```

---

## 2. Asset Management Companies (AMCs)

### Primary Valuation Approach: % of AUM + P/E

**AUM-Based Approach:**
```
Value = AUM × Revenue Yield × P/E_of_revenue_stream
      OR
Value = AUM × Earnings Yield
      = AUM × (Net Margin × Total Expense Ratio)

Typical metrics (India, FY24):
  Management fee (TER, net of distributor commission): 0.5–1.0% of AUM
  EBITDA margin: 40–55% (very capital-light business)
  P/AUM: 3–5% (listed Indian AMCs trade in this range)
```

**P/E Approach:**
```
Earnings = AUM × Revenue Yield × Net Margin
P/E for AMC: 25–40× (premium for fee income stability and growth)
```

**Key Drivers:**
- AUM growth (linked to equity market returns + industry penetration)
- SIP book (monthly systematic investment plan flows = recurring, sticky)
- Market share in equity funds (higher margin than debt/liquid)
- Operating leverage (high fixed cost; incremental AUM → high PAT growth)

---

## 3. Negative Earnings Firms

**Damodaran: Ch. 22 — "Standard models do not work when current earnings are negative."**

### Option 1: DCF with Normalised Earnings
```
1. Project when the firm reaches normal earnings (profitability timeline)
2. Estimate normalised EBIT at that point (use sector margin benchmarks)
3. Run DCF from that "steady state" year
4. Discount back to today at an appropriately higher WACC (reflecting early-stage risk)
```

### Option 2: EV/Revenue Multiple
```
EV = EV/Revenue × Revenue

Apply sector multiple from comparable profitable firms
Adjust downward for higher risk, lower margins of this firm vs. peers
```

### Option 3: Venture Capital / Stage-Gate Method
```
Value = Terminal Year Earnings / Target P/E  ÷  (1 + Target Return)^n

E.g., Year 5 target earnings = ₹100 Cr; sector P/E = 20; required return = 30%
Value today = (100 × 20) / (1.30)^5 = 2000 / 3.71 = ₹539 Cr
```

### Critical inputs for negative-earnings firms:
- **Revenue growth rate**: highest importance; everything else follows
- **Path to margins**: when does gross margin turn positive? EBITDA? PAT?
- **Burn rate**: how long can the company survive on current cash?
- **Cost of capital**: Use a high WACC (18–25%) to reflect startup risk; reduce as firm matures

---

## 4. Young / Start-up Firms

**Damodaran: Ch. 23**

### Key challenges:
- No operating history
- High growth with high uncertainty
- Most likely outcome may be failure (survival bias in optimistic forecasts)

### Damodaran's Recommended Approach:
1. **Build a narrative** → what does success look like?
2. **Translate narrative to financial projections**:
   - Revenue in mature phase (TAM × Market share)
   - Margins in mature phase (best-in-class peers)
   - Reinvestment needs (capex + WC to sustain growth)
3. **Assign failure probability**:
   - Probability of reaching profitability = p
   - Value if successful = V_success
   - Value = p × V_success + (1–p) × V_failure (liquidation value)
4. **Discount at high WACC** (20–30%); reduce to sector WACC as firm matures

### India context — fintech, SaaS startups:
- Compare to listed comparable (Paytm, Zomato, Nykaa for market sentiment)
- Use EV/Revenue as market "consensus" but build intrinsic DCF for fair view
- **Never use current negative EBITDA as base** for multiples → use forward EBITDA (if credible)

---

## 5. Private Firms

**Damodaran: Ch. 24**

### Adjustments for private firm valuation:
1. **Illiquidity discount**: Private firms lack market liquidity
   - Typical discount: 20–30% off comparable public company value
   - Smaller companies: up to 40%
   - Near-IPO stage: 10–15%

2. **Key-man risk**: If business depends on 1–2 people
   - Reflect in higher cost of equity or explicit risk premium

3. **Control premium** (for acquisitions): 20–40% over minority market value

4. **Beta estimation**: Use sector average unlevered beta; re-lever for firm's capital structure
   ```
   β_levered = β_unlevered × [1 + (1–t) × D/E]
   ```

5. **WACC for private firm**: Add small firm premium (2–4%) to standard CAPM
   ```
   Ke = Rf + β × ERP + Size Premium
   ```

### Net Asset Value (for holding companies and conglomerates)
```
NAV = Sum of: 
  Listed subsidiaries at market value
+ Unlisted subsidiaries at fair value (DCF or last funding round)
+ Standalone parent assets
– Holding company debt
– Holding company discount (typically 20–40% for lack of control + liquidity)
```

---

## 6. Cyclical Firms

**Key sectors in India**: Metals, cement, auto, chemicals, oil & gas, power

### The Mistake to Avoid:
Valuing at peak-cycle EPS → will look cheap at top; expensive at bottom.

### Recommended Approach:
```
Use mid-cycle (normalised) earnings, not current EPS.

Normalised EBIT Margin = Average of past 7–10 year EBIT margin
Normalised EPS         = Normalised EBIT × (1–t) / Shares – Interest/Shares
Normalised P/E         = Current Price / Normalised EPS
```

**Commodity-specific adjustments:**
| Metal | Reference price basis |
|-------|----------------------|
| Steel | HRC spot price (benchmark: ~$600–800/t through cycle) |
| Aluminium | LME 3-month average |
| Copper | LME spot |
| Coal | Australian thermal coal benchmark |

**EV/tonne and EV/capacity are common sector metrics.**

---

## 7. Real Estate

### Net Asset Value (NAV) Approach
```
NAV = Gross Development Value (GDV) – Development Costs – Unsold inventory residual risk

GDV = Σ (Area to be developed × Realisation per sqft)

Development Cost = Land cost + Construction cost + Selling & marketing + Corporate overhead

Developer Margin = GDV – Total Costs
```

**Discounted Cash Flow (cash received basis):**
```
FCF = Collections in year t – Costs in year t
Discount at WACC (typically 13–16% for Indian real estate given risk)
```

**Key metrics:**
```
Presales (new bookings value) → forward-looking demand indicator
Collections (cash collected) → actual cash conversion
Net debt / Pre-sales → balance sheet stress measure
EBITDA per sqft                → margin per unit
Inventory / Presales           → how many years of supply in hand
```

---

## 8. Infrastructure / Utilities

### Characteristics:
- Long-lived assets with regulated or contracted returns
- High upfront capex; low operating cost
- Stable, visible cash flows once commissioned

### DCF Approach:
```
FCFF = Revenue (contracted) – Operating Cost – Tax – Change in Regulated Asset Base

Terminal Value: Use perpetuity (projects have very long lives); g = inflation (3–5%)
WACC: Lower than industrial (project finance rates); typically 9–12% for India
```

**Key metrics:**
| Metric | Use |
|--------|-----|
| DSCR (Debt Service Coverage Ratio) | Lender stress test; ≥ 1.3× preferred |
| PLF (Plant Load Factor) | Capacity utilisation for power plants |
| EV/MW (for power) | Sector-level comparison |
| EV/km (for road/rail) | Sector-level comparison |
| RAB multiple (for regulated utilities) | P/RAB = 1 is theoretical fair value |

---

## 9. Pharma / Biotech

### Established Pharma (generic/domestic formulations)
- Standard DCF / EV-EBITDA works
- Normalise for US FDA-related one-offs (import alerts, 483 observations)
- Adjust for R&D capitalisation vs. expensing

### Biotech / Novel Drug Discovery
```
Risk-adjusted NPV (rNPV) = Σ [NCF_t × Probability of Success_phase × Discount Factor]

Phase success probabilities (industry average):
  Phase I   → Phase II:  50–65%
  Phase II  → Phase III: 30–45%
  Phase III → Approval:  50–70%
  Overall Phase I → Approval: ~10–15%
```

**India pharma-specific:**
- ANDA pipeline (US generics) → value per ANDA = $1–5M depending on competition
- Contract Manufacturing (CDMO): Value on EV/EBITDA (20–30×) or EV/Revenue
- Domestic branded generics: P/E 25–35× (pricing power, chronic therapy dominance)
