# Multiples & Relative Valuation Reference
## Source: Aswath Damodaran – Investment Valuation (Chapters 17–20)

---

## Table of Contents
1. [The Four-Step Process](#1-the-four-step-process)
2. [Equity Multiples](#2-equity-multiples)
3. [Enterprise Value Multiples](#3-enterprise-value-multiples)
4. [Sector-Specific Multiples](#4-sector-specific-multiples)
5. [Comparable Selection](#5-comparable-selection)
6. [Cross-Country Valuation](#6-cross-country-valuation)

---

## 1. The Four-Step Process

Damodaran's disciplined approach to every multiple:

```
Step 1: DEFINE the multiple consistently
        (Numerator and denominator must be on the same capital basis)

Step 2: DESCRIBE the distribution
        (Mean, median, range — use median, not mean, for skewed distributions)

Step 3: ANALYZE the fundamentals
        (What growth rate, margin, and risk does this multiple embed?)

Step 4: APPLY with control variables
        (Compare to peers adjusting for key differences)
```

---

## 2. Equity Multiples

### Price-to-Earnings (P/E)

**Definition (consistent):**
```
P/E = Market Price per Share / EPS
Use: Trailing P/E (LTM EPS) or Forward P/E (NTM consensus EPS)
Never mix: Market cap with EBITDA in numerator
```

**Fundamental drivers:**
```
P/E = Payout Ratio × (1+g) / (Ke – g)

Simplification: Higher P/E ↔ Higher growth, lower risk, higher payout
PEG Ratio = P/E / g  (annualised growth rate)
PEG < 1 → potentially undervalued vs. growth
```

**Damodaran's warning on P/E:**
- Firms with negative earnings → P/E undefined; use EV/EBITDA or EV/Revenue
- Cyclical firms → use normalised P/E (10-year average EPS)
- Firms with high leverage → P/E distorted; compare EV multiples instead

**Indian context — Screener.in useful fields:**
- TTM P/E (trailing 12 months)
- Sector P/E from NSE website
- Normalise by stripping exceptional items in EPS

---

### Price-to-Book (P/B)

**Definition:**
```
P/B = Market Price per Share / Book Value per Share

Book Value = Total Equity (Ind AS) excluding goodwill on impairment testing
```

**Fundamental driver:**
```
P/B = ROE × Payout Ratio × (1+g) / (Ke – g)

Or simplified: P/B = (ROE – g) / (Ke – g)
```

**Key insight (Damodaran):** 
A company with ROE = Ke should trade at P/B = 1.0.
- P/B > 1 is justified only if ROE > Ke
- P/B < 1 → either ROE < Ke (value trap) or true bargain (Graham territory)

**Graham's criterion:** P/B × P/E ≤ 22.5 (from *The Intelligent Investor*)

---

### PEG Ratio

```
PEG = P/E / Expected EPS Growth Rate (%)

Rule of thumb (Peter Lynch, endorsed by Graham framework):
PEG < 1.0  → Potentially undervalued
PEG = 1.0  → Fairly valued
PEG > 1.5  → Potentially expensive
```

**Limitations:** PEG ignores risk and assumes linearity of value with growth. Use as a secondary check, not standalone.

---

### Price-to-Sales (P/S)

```
P/S = Market Cap / Revenue

Or EV/Revenue = Enterprise Value / Revenue (more consistent)
```

**Fundamental driver:**
```
P/S = Net Profit Margin × P/E

High P/S is justified only if high margins AND high growth are sustainable.
```

**Use cases:** Early-stage companies, loss-making companies, comparison within sector (e.g., SaaS, FMCG, retail).

---

## 3. Enterprise Value Multiples

### EV/EBITDA

**Definition (must be consistent):**
```
EV = Market Cap + Debt + Minority Interest + Preferred Stock – Cash
EBITDA = Earnings Before Interest, Tax, Depreciation, Amortisation

EV/EBITDA = EV / EBITDA
```

**Why EV/EBITDA is preferred over P/E:**
- Unaffected by capital structure (debt levels)
- Works for negative-PAT companies
- Useful for cross-border comparison (pre-tax, pre-interest)

**Fundamental drivers:**
```
EV/EBITDA = (1 – t) × [1 – (g/ROC)] / (WACC – g)

Where reinvestment rate = g/ROC
```

**Typical India ranges (indicative, FY24):**
| Sector | EV/EBITDA Range |
|--------|----------------|
| IT Services | 15–25× |
| Consumer FMCG | 25–40× |
| Pharmaceuticals | 12–20× |
| Auto | 8–14× |
| Cement | 10–16× |
| Banks (use P/B instead) | — |
| Infrastructure | 8–14× |
| Chemicals | 12–20× |

---

### EV/EBIT

```
EV/EBIT = Enterprise Value / EBIT
```
Use when comparing companies with significantly different depreciation policies (capital intensity differences). More conservative than EV/EBITDA.

---

### EV/Revenue (EV/Sales)

Use for:
- High-growth loss-making companies (fintech, SaaS)
- Revenue-based acquisition valuation
- Cross-sector screening (not comparable across different margin businesses)

---

## 4. Sector-Specific Multiples

| Sector | Primary Multiple | Why |
|--------|----------------|-----|
| Banks & NBFCs | P/B, P/ABV | Asset quality risk in book value |
| Insurance | P/EV (Embedded Value), VNB multiple | Life insurance-specific |
| Real Estate | P/NAV (Net Asset Value) | Asset-based; book value unreliable |
| Telecom | EV/EBITDA, EV/Subscriber | Network economics |
| Oil & Gas | EV/boe (barrel of oil equivalent), EV/EBITDA | Reserve-based |
| Retail | EV/EBITDA (same-store), EV/sqft | Operational efficiency |
| Hospitals | EV/Bed, EV/EBITDA | Capacity utilisation |
| Asset Managers (AMCs) | P/AUM (% of AUM), P/E | Fee income stable |

---

## 5. Comparable Selection

### Universe Selection Criteria
1. **Same industry** (primary filter)
2. **Similar size** (market cap within 50–300% range)
3. **Similar growth profile** (if high-growth firm, don't compare to stable peers)
4. **Similar leverage** (or use EV multiples to neutralise)
5. **Same geography** (or apply country premium)

### Regression-Based Approach (Damodaran)
For large peer sets, run regression:

```
P/E = a + b × (Growth Rate) + c × (Beta) + d × (Payout Ratio)

Then: Predicted P/E = a + b×g + c×β + d×payout

If Actual P/E < Predicted P/E → potentially undervalued
```

### Adjusting for Differences
```
Adjusted P/E = Actual P/E × (Peer_average_growth / Company_growth)
                           × (Company_ROE / Peer_average_ROE)
```

---

## 6. Cross-Country Valuation

When comparing Indian companies to global peers, adjust for:

1. **Country Risk Premium**: India's equity risk premium is ~6–8% vs US ~4.5–5%. Indian stocks should trade at a discount to US peers, all else equal.

2. **Growth differential**: India's long-term nominal GDP growth (~11–12%) vs US (~4–5%). This justifies higher multiples for Indian businesses with domestic exposure.

3. **Net formula:**
```
India P/E premium over US = (India GDP growth – US GDP growth) / (India Ke – US Ke)

If growth differential > risk differential → Indian premium justified
```

4. **Currency risk**: For export-oriented companies, INR depreciation trend benefits revenues but increases USD debt cost.
