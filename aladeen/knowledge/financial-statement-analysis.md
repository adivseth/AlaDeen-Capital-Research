# Financial Statement Analysis Reference
## Source: Graham & Dodd – Security Analysis (6th Ed.), Chapters 31–45
##         Damodaran – Investment Valuation, Chapters 3, 9–10

---

## Table of Contents
1. [Income Statement Analysis](#1-income-statement-analysis)
2. [Cash Flow Analysis](#2-cash-flow-analysis)
3. [Balance Sheet Analysis](#3-balance-sheet-analysis)
4. [Key Ratio Framework](#4-key-ratio-framework)
5. [Red Flags Checklist](#5-red-flags-checklist)
6. [Normalising Earnings](#6-normalising-earnings)

---

## 1. Income Statement Analysis

### Revenue Quality
```
Revenue Growth (YoY) = (Revenue_t – Revenue_{t-1}) / Revenue_{t-1}
Revenue CAGR (5-yr)  = (Revenue_5 / Revenue_0)^(1/5) – 1

Quality checks:
  - Is revenue growth organic or acquisition-driven?
  - Compare to industry volume growth; excess = market share gain or pricing
  - Check receivable days growth vs. revenue growth
  - Channel-stuffing signal: Inventory + Receivables growing faster than revenue
```

### EBITDA and EBIT
```
EBITDA Margin = EBITDA / Revenue
EBIT Margin   = EBIT / Revenue

Watch:
  - Capitalising operating expenses to inflate EBITDA (inflate Capex instead)
  - Adjusting "one-time" restructuring charges every year (normalise them)
  - ESOP charges excluded from adjusted EBITDA (real cost to shareholders; include)
```

### Depreciation as a Quality Signal
```
Depreciation Rate = Depreciation / Gross Block

Compare to:
  - Previous years (declining rate = asset life extension = profit inflation)
  - Peers (should be similar for similar asset types)
  - Asset additions (new Capex should increase depreciation proportionally)

Companies Act 2013 (India): Prescribed useful lives under Schedule II
If company uses longer life than Schedule II → conservative signal
```

### Other Income
```
Other Income Quality:
  - Interest income on cash → acceptable (deduct for enterprise-level analysis)
  - Gains on asset sales → non-recurring; strip out
  - Forex gains → non-recurring; strip out
  - Dividend from subsidiaries → substitute for dividends where policy differs
  
Adjusted PAT = Reported PAT 
              – Other Income net of tax (where non-operating)
              + Exceptional losses (stripped out by management)
              – Exceptional gains (stripped out by management)
```

---

## 2. Cash Flow Analysis

### OCF vs. Reported PAT (The Core Quality Check)

```
Cash Conversion Ratio = OCF / PAT

> 1.0   → Cash earnings exceed reported earnings → Quality signal
0.7–1.0 → Acceptable range
< 0.7   → Accrual-based earnings may be inflated → Investigate working capital
< 0.5   → Serious concern
```

**Forensic Check: Accruals**
```
Accruals = (PAT – OCF)

Accruals Ratio = Accruals / Average Net Assets

Interpretation:
  High positive accruals = paper profits, not cash profits → RED FLAG
  Negative accruals     = underreported earnings on cash basis → POSITIVE
```

### Free Cash Flow (FCF) Generation
```
FCF = OCF – Capex (maintenance only)

Maintenance Capex Estimate:
  = Depreciation × (1 + inflation rate)
  For asset-heavy industries, use replacement cost rather than book depreciation

FCF Yield = FCF / Market Cap × 100%
  > 5% → good yield
  > 8% → excellent
  < 2% → expensive or low cash generation
```

### Working Capital Analysis
```
Days Sales Outstanding (DSO)  = (Debtors / Revenue) × 365
Days Inventory Outstanding    = (Inventory / COGS) × 365
Days Payable Outstanding      = (Creditors / COGS) × 365

Cash Conversion Cycle = DSO + DIO – DPO
```

**Rising CCC over time** → Working capital deteriorating; cash flow stress.

**Negative CCC** (e.g., retail, FMCG) → Customers pay before company pays suppliers = **powerful business model signal** (Damodaran: "negative working capital companies are self-funding their growth").

---

## 3. Balance Sheet Analysis

### Asset Quality

**Goodwill and Intangibles:**
```
Tangible Book Value = Total Equity – Goodwill – Other Intangibles – DTA (net)

Goodwill / Total Assets > 20% → heavily acquisition-driven; impairment risk
Check: Are acquired companies still performing as expected?
       Has goodwill grown each year without impairment → possible evergreening
```

**Investments (India-specific):**
```
Types:
  - Subsidiaries (consolidate)
  - Associates (equity method)
  - Joint ventures (proportionate or equity method)
  - Mutual funds / treasury investments (mark-to-market under Ind AS 109)

Check: Are inter-company loans/advances classified as investments? (Related-party risk)
```

**Capital Work-in-Progress (CWIP):**
```
CWIP / Gross Block > 30% and growing → major expansion underway
CWIP stagnant for 3+ years → possible capitalised sunk cost; impairment risk
CWIP to Gross Block conversion rate = annual additions / CWIP (should be > 0)
```

### Liability Analysis

**Debt Quality:**
```
Short-term Debt / Total Debt > 40% → Refinancing risk; rolling over frequently
Term Loan repayment schedule → Check for bullet repayments; debt maturity cliff

Net Debt = Total Debt + Capitalised Leases – Cash
Net Debt / EBITDA:
  < 1.5× → Conservative
  1.5–3.0× → Moderate
  3.0–5.0× → High; limited headroom
  > 5.0× → Distressed / speculative
```

**Contingent Liabilities:**
```
Disclose in notes (Ind AS 37): Tax disputes, legal cases, guarantees given
Conservative practice: Add 20–30% of contingent liabilities to debt for analysis
```

---

## 4. Key Ratio Framework

### Profitability Ratios
```
Return on Equity (ROE)    = PAT / Average Equity
Return on Capital (ROCE)  = EBIT (1–t) / (Equity + Debt – Cash)
Return on Assets (ROA)    = PAT / Average Total Assets
EBITDA Margin             = EBITDA / Revenue
Net Profit Margin         = PAT / Revenue
```

### DuPont Decomposition of ROE
```
ROE = Net Profit Margin × Asset Turnover × Equity Multiplier
    = (PAT/Revenue) × (Revenue/Assets) × (Assets/Equity)

Analyse which driver is dominant:
  Margin-driven ROE     → Pricing power, brand, high-value products
  Turnover-driven ROE   → Asset efficiency, lean operations (e.g., retail)
  Leverage-driven ROE   → Financial leverage; ROCE may be low; check sustainability
```

### Efficiency Ratios
```
Asset Turnover = Revenue / Average Total Assets  (higher = more efficient)
Fixed Asset Turnover = Revenue / Net Fixed Assets
Inventory Turnover   = COGS / Average Inventory
Debtor Turnover      = Revenue / Average Debtors
```

### Leverage and Coverage Ratios
```
Debt-to-Equity        = Total Debt / Equity
Interest Coverage     = EBIT / Interest Expense     (Graham minimum: 5×)
Debt Service Coverage = (PAT + Interest + Dep) / (Interest + Principal repayment)
Net Debt / EBITDA     = Net Debt / EBITDA
```

### Liquidity Ratios
```
Current Ratio  = Current Assets / Current Liabilities  (Graham minimum: 2.0)
Quick Ratio    = (CA – Inventory) / CL               (minimum: 1.0)
Cash Ratio     = Cash / CL                            (stress test)
```

---

## 5. Red Flags Checklist

Run this checklist on every company before committing to a valuation:

**Earnings Quality Red Flags:**
- [ ] Cash Conversion Ratio < 0.7 for 3+ consecutive years
- [ ] Accruals Ratio > 10% consistently
- [ ] Other income > 20% of reported PAT
- [ ] Exceptional items (gains) recurring every year
- [ ] Depreciation rate declining without asset life change disclosure
- [ ] Auditor change without explanation (qualification, disagreement)
- [ ] Qualified/Emphasis of Matter in audit report
- [ ] Related party transactions: loans to promoter entities
- [ ] Inventory build-up without proportional revenue growth
- [ ] Rising DSO with flat or declining revenue

**Balance Sheet Red Flags:**
- [ ] Promoter pledge > 50% of holdings
- [ ] CWIP growing without capitalization (potential evergreening)
- [ ] Goodwill growing through serial acquisitions without impairment tests disclosed
- [ ] Large DTA that may not be realizable
- [ ] Contingent liabilities > 50% of net worth
- [ ] Short-term debt > 50% of total debt (rollover risk)
- [ ] Working capital loans as percentage of sales growing

**Corporate Governance Red Flags (Security Analysis, Ch. 47):**
- [ ] Promoter group transactions with listed entity at non-arm's-length prices
- [ ] Excessive management remuneration vs. PAT (> 5% of PAT for promoter families)
- [ ] Voting rights disproportionate to economic rights (complex holding structures)
- [ ] Insider selling while company narrative is bullish
- [ ] Audit committee independence questionable

---

## 6. Normalising Earnings

### Purpose
Graham: Never value a company on one year's earnings. Use **normalised earnings** — the earnings the company can generate through the business cycle under average conditions.

### Method 1: Simple Average
```
Normalised EPS = Average of past 5–7 years' adjusted EPS
              (strip one-offs, use adjusted PAT)
```

### Method 2: Margin × Revenue Approach
```
Normalised EPS = Normalised Revenue × Normalised Net Margin / Shares

Where:
  Normalised Revenue = Current or near-term revenue (not depressed/inflated)
  Normalised Margin  = Average margin over full cycle (avoid peak/trough year)
```

### Method 3: EBIT-based (for cyclical companies)
```
Normalised EBIT = Average EBIT margin × Current Revenue
Normalised PAT  = Normalised EBIT × (1 – Effective Tax Rate) – Interest
Normalised EPS  = Normalised PAT / Shares
```

### Sectors requiring special normalisation:
| Sector | Normalisation Note |
|--------|--------------------|
| Steel / Commodities | Use mid-cycle price assumption, not spot |
| Auto | Use 85–90% capacity utilisation baseline |
| Banks | Normalise credit cost (LLP) at through-cycle average ~1.5–2% |
| Real Estate | Use delivery-year accounting; spread over project lifecycle |
| IT Services | Remove forex hedging gains/losses; strip for clean operating margin |
| Pharma | Exclude one-time US FDA resolution gains |
