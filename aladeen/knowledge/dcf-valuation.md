# DCF Valuation Reference
## Source: Aswath Damodaran – Investment Valuation (2nd Ed.)

---

## Table of Contents
1. [Choosing: FCFF vs FCFE vs DDM](#1-choosing-fcff-vs-fcfe-vs-ddm)
2. [Estimating Cash Flows](#2-estimating-cash-flows)
3. [Estimating Growth](#3-estimating-growth)
4. [Cost of Capital (WACC)](#4-cost-of-capital-wacc)
5. [Terminal Value](#5-terminal-value)
6. [Putting It Together](#6-putting-it-together)
7. [Dividend Discount Model (DDM)](#7-dividend-discount-model-ddm)
8. [Sensitivity Analysis](#8-sensitivity-analysis)

---

## 1. Choosing: FCFF vs FCFE vs DDM

| Model | Use When | Discount Rate |
|-------|----------|--------------|
| **FCFF** (Free Cash Flow to Firm) | Leveraged firm; capital structure changing; or you want EV | WACC |
| **FCFE** (Free Cash Flow to Equity) | Stable capital structure; focus on equity value directly | Cost of Equity (Ke) |
| **DDM** (Dividend Discount Model) | Mature dividend-paying companies; financial firms (banks) | Cost of Equity (Ke) |

**Damodaran's Guidance**: If D/E is changing, use FCFF. If the firm pays out close to FCFE as dividends, DDM and FCFE will converge.

---

## 2. Estimating Cash Flows

### FCFF Formula
```
FCFF = EBIT × (1 – Tax Rate) + Depreciation – Capex – ΔNWC

Where:
  EBIT (1–t)        = NOPAT (Net Operating Profit After Tax)
  Depreciation      = Non-cash charge added back
  Capex             = Capital expenditure (gross, from cash flow statement)
  ΔNWC              = Change in Non-Cash Working Capital
                    = (Current Assets – Cash) – (Current Liabilities – Short-term Debt)
```

**Reinvestment Rate:**
```
Reinvestment Rate = (Capex – Depreciation + ΔNWC) / NOPAT
Expected Growth (FCFF) = ROC × Reinvestment Rate
```

### FCFE Formula
```
FCFE = Net Income + Depreciation – Capex – ΔNWC + Net Borrowing

Or equivalently:
FCFE = FCFF – Interest × (1 – Tax Rate) + Net Borrowing
```

**Reinvestment Rate for FCFE:**
```
Equity Reinvestment Rate = (Capex – Depreciation + ΔNWC – Net Borrowing) / Net Income
Expected Growth (FCFE) = ROE × Equity Reinvestment Rate
```

### Adjustments for Indian Companies
- Use **Ind AS 116** capitalised lease obligations: add right-of-use asset depreciation back, subtract lease principal payments (treat as debt repayment in FCFE)
- **Goodwill amortisation**: not required under Ind AS, but test for impairment — normalise for companies with large M&A histories
- **Deferred Tax**: use cash tax rate where possible; large DTA/DTL movements distort NOPAT
- **Minority interest**: if consolidating subsidiaries, adjust FCFF for minority's share of reinvestment

---

## 3. Estimating Growth

### Methods (in order of reliability)

**Method 1: Fundamental Growth**
```
g = Reinvestment Rate × ROC          (for FCFF / firm-level)
g = Equity Reinvestment Rate × ROE   (for FCFE / equity-level)
```
*This is Damodaran's preferred method — growth that is not backed by reinvestment is not sustainable.*

**Method 2: Historical Growth**
- Use geometric mean of EPS or revenue over 5–10 years
- Adjust for one-off items, cyclicality, and structural changes
- **Warning**: High historical growth does not guarantee future growth

**Method 3: Analyst Estimates**
- Use consensus estimates for next 2–3 years if available
- For Indian stocks: Bloomberg, Motilal Oswal, Kotak Research

### Growth Phases

| Phase | Duration | Characteristics |
|-------|----------|----------------|
| **High growth** | 5–10 years | Reinvestment rate high; ROC > WACC |
| **Transition** | 3–5 years | Growth declining; ROC converging to WACC |
| **Stable growth** | Perpetuity | g ≤ nominal GDP; ROC = WACC (no excess returns) |

**India cap**: Stable growth rate ≤ 6–7% (nominal GDP). Using 8–10% in perpetuity inflates value significantly.

---

## 4. Cost of Capital (WACC)

### Cost of Equity (CAPM)
```
Ke = Rf + β × (ERP) + Country Risk Premium (optional)

Where:
  Rf  = Risk-free rate (India: 10-yr G-Sec ~ 7.0–7.2%)
  β   = Beta (use 2-yr monthly or 5-yr weekly vs. Nifty 50)
  ERP = Equity Risk Premium
        India: ~7–8% (Damodaran's implied ERP for India, Jan 2024)
        Alternatively: Damodaran India ERP from his website (update annually)
  CRP = Country Risk Premium (already embedded in ERP for India)
```

**Beta adjustments:**
- Use **bottom-up beta**: unlevered industry beta × (1 + (1–t) × D/E)
- Damodaran provides industry-level betas at pages.stern.nyu.edu/~adamodar/
- For young/unlisted companies: use sector average beta

### Cost of Debt
```
Kd = Pre-tax cost of debt × (1 – Tax Rate)

Pre-tax Kd = Yield on company's rated bonds, OR
           = Risk-free rate + Default spread (based on Interest Coverage Ratio)

Interest Coverage = EBIT / Interest Expense
Default spreads table (Damodaran):
  ICR > 8.5x  → AAA → spread ~0.5%
  ICR 4–8.5x  → AA/A → spread 1–2%
  ICR 2–4x    → BBB/BB → spread 2–4%
  ICR < 2x    → B or below → spread 4–8%+
```

### WACC Formula
```
WACC = Ke × [E / (E+D)] + Kd × (1–t) × [D / (E+D)]

Use market values (not book values) for E and D.
For D: include interest-bearing debt + capitalised leases.
```

---

## 5. Terminal Value

**Damodaran's warning**: Terminal value typically represents 60–80%+ of DCF value. Small changes in assumptions have outsized impact. Always stress-test.

### Gordon Growth Model (Going Concern)
```
Terminal Value_n = FCFF_{n+1} / (WACC – g_stable)

Where:
  FCFF_{n+1} = FCFF in first year of stable phase
  g_stable   = Stable growth rate (≤ nominal GDP growth)

FCFF_{n+1} = EBIT_{n+1} × (1–t) × (1 – Reinvestment Rate_stable)

Stable Reinvestment Rate = g_stable / ROC_stable
```

**Common error**: Using high ROC in stable phase. In competitive equilibrium, ROC should converge to WACC. Excess ROC in stable phase = hidden optimism.

### Stable Phase ROC
- If firm has durable competitive advantage (moat): ROC = 1.2–1.5× WACC
- Average competitive firm: ROC = WACC (no value creation in terminal phase)
- Commodity/regulated firm: ROC may equal or be below WACC

### Exit Multiple Approach
```
Terminal Value = EV/EBITDA_exit × EBITDA_{year n}
```
Use this as a cross-check, not a primary method. The exit multiple must be consistent with growth and return assumptions.

### Liquidation Value
```
Terminal Value = Book Value of Assets × (1 + Inflation)^life_of_assets
```
Use for asset-heavy companies in terminal decline (e.g., old-economy capital-intensive firms).

---

## 6. Putting It Together

### DCF Equity Value (FCFF approach)
```
Enterprise Value = Σ [FCFF_t / (1+WACC)^t] + Terminal Value / (1+WACC)^n

Equity Value = EV – Net Debt – Minority Interest + Associates/Investments at Fair Value

Per Share Value = Equity Value / Diluted Shares Outstanding
```

**Net Debt = Gross Debt + Capitalised Leases – Cash & Equivalents**

Do NOT subtract full cash if it is trapped (e.g., overseas subsidiaries in India), partially restricted, or needed for operations (operating cash buffer = ~2% of revenue).

### DCF Equity Value (FCFE approach)
```
Equity Value = Σ [FCFE_t / (1+Ke)^t] + Terminal Value / (1+Ke)^n

Per Share Value = Equity Value / Diluted Shares Outstanding
```

---

## 7. Dividend Discount Model (DDM)

Best suited for: Mature dividend-paying companies (FMCG, utilities, financial services).

### Gordon Growth Model (Single-stage DDM)
```
Value = D₁ / (Ke – g)

Where D₁ = DPS₀ × (1+g)
```

### Two-Stage DDM
```
Value = Σ [DPS_t / (1+Ke)^t]  (years 1 to n)
      + [DPS_{n+1} / (Ke – g_stable)] / (1+Ke)^n

DPS_t = DPS₀ × (1+g_high)^t
```

### H-Model (gradual decline in growth)
```
Value = [DPS₀ × (1+g_stable)] / (Ke – g_stable)
      + [DPS₀ × H × (g_high – g_stable)] / (Ke – g_stable)

Where H = half-life of high growth period
```

### Dividend Payout Check
- If payout ratio < FCFE yield significantly → DDM undervalues; use FCFE model
- If payout ratio > 100% of earnings → unsustainable; normalise
- Graham's rule: Companies paying a stable 40–60% of earnings are preferred

---

## 8. Sensitivity Analysis

Always produce a sensitivity table on two key variables:

**For FCFF:**
| | WACC –1% | WACC Base | WACC +1% |
|---|---|---|---|
| g –0.5% | | | |
| g Base | | | |
| g +0.5% | | | |

**Interpretation:**
- If fair value range (across all 9 cells) is within ±20% of base case → moderate confidence
- If range spans >40% → high sensitivity; present base/bull/bear cases
- Flag the top 2–3 value drivers and their impact per 1% change

**Bull/Base/Bear Framework:**
| Scenario | Revenue growth | Margins | WACC | Stable g |
|----------|---------------|---------|------|----------|
| Bull     | +200 bps | +150 bps | –50 bps | Base |
| Base     | Consensus | Consensus | CAPM | Nominal GDP |
| Bear     | –200 bps | –150 bps | +50 bps | Base–50 bps |
