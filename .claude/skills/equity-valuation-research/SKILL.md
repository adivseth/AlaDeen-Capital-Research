---
name: equity-valuation-research
description: "Equity valuation, stock research and investment analysis for Indian (and other) listed companies, grounded in Damodaran (Investment Valuation), Graham (The Intelligent Investor) and Graham & Dodd (Security Analysis), with a bull-vs-bear debate, risk review and a scored call log. Use whenever asked to value a stock, run a DCF/DDM, compute multiples, assess intrinsic value or margin of safety, screen stocks, analyse financial statements or earnings quality, compute WACC, build an investment thesis, compare peers, or score past research calls ('score my calls')."
---

# Equity valuation research

Sources: Damodaran – *Investment Valuation*; Graham – *The Intelligent Investor*; Graham & Dodd – *Security
Analysis*. The debate, risk review and call-log steps mirror the AlaDeen Capital Research process.

In this repo, the `aladeen` CLI does the data collection and all arithmetic. Use it; do not compute figures
in prose. The methodology references live in `aladeen/knowledge/` (relative to the repo root).

## Quick dispatch

| Task | Reference (`aladeen/knowledge/`) | Tool |
|---|---|---|
| DCF / FCFF / FCFE, WACC, terminal value | `dcf-valuation.md` | `aladeen value TICKER` |
| Multiples, peers | `multiples-valuation.md` | peer table in `aladeen data` |
| Intrinsic value, margin of safety, Graham screens | `value-investing-framework.md` | Graham block in the report |
| Earnings quality, balance sheet, red flags | `financial-statement-analysis.md` | reconciliation in `aladeen data` |
| Banks, NBFCs, AMCs, insurers, cyclicals, real estate, startups | `sector-valuation.md` | justified P/B for financials |
| Full research note | all | `aladeen research TICKER` |
| Score past calls | this file | `aladeen score` |
| Quarterly update | this file | `aladeen track TICKER` |

## Master workflow

```
Step 0  Read prior calls on the company (call log) and their lessons.
Step 1  Qualitative: business, moat, management, industry.
Step 2  Financial statements: earnings quality, 5-10 year trends, balance sheet, CFO vs PAT.
Step 3  Intrinsic value: FCFF DCF (or justified P/B for financials); DDM where relevant.
Step 4  Relative value: P/E, EV/EBITDA, P/B vs ROE against peers.
Step 5  Margin of safety vs intrinsic value; Graham checks.
Step 6  Bull vs bear debate (one opening each + one rebuttal each).
Step 7  Risk review (aggressive / neutral / conservative) and final call.
Step 8  Output: the report.  Then run the llm-council skill on it.
Step 9  Log the call.
```

### Step 6: Bull vs bear

1. Bull case (≤300 words): strongest case for owning the stock, every claim tied to a verified figure or source.
2. Bear case (≤300 words): must address every governance flag, any CFO/PAT gap, and the terminal-value share
   of the DCF and the downside value.
3. One rebuttal each.
4. Record what survived, what did not, and the **kill fact**: the one checkable fact that would overturn the call.

No new numbers in the debate. Anything not verified in Steps 1–5 is verified or removed.

### Step 7: Risk review and final call

- Aggressive: what would justify a bigger position or higher target?
- Neutral: is the rating consistent with the valuation and the debate?
- Conservative: realistic loss in the bear case; entry price for an adequate margin of safety?

Final call: rating (bands below), fair value, entry zone, position size (Starter / Full / Avoid), why the
losing side lost, and the kill fact (carried into every quarterly tracker).

### Rating definitions (expected 12-month total return)

| Rating | Band |
|---|---|
| BUY | > 15% |
| HOLD | 0% to 15% |
| SELL / AVOID | < 0% |

Qualifiers ("High Risk", "Selective") may be added; they do not change the band.

## Call log and scoring

`~/.aladeen/call_log.csv` (or a Google Sheet; see `docs/call-log.md`). Columns: call_id, call_date, company,
ticker (Yahoo format: `.NS`, `.BO`), rating, target_price, close_on_call_date, benchmark (`^NSEI` for NSE,
`^BSESN` for BSE-only), benchmark_close_on_call_date, review_date, close_on_review_date,
benchmark_close_on_review_date, stock_return, benchmark_return, alpha, verdict, lesson, report_file, notes.

Scoring (`aladeen score`): prices are split- and bonus-adjusted closes; returns are price-only. Calls younger
than 365 days read "Too early (<12m)". For demergers, add the value of the demerged shares received per
original share and say so in `notes`. Write a one-line lesson per scored call: what played out, what did not,
and whether the kill fact occurred. Never guess a missing date or price.

## Short-term check (quarterly tracker)

Last 5–10 trading days vs the benchmark, exchange announcements in the window, credit-rating actions,
promoter pledge changes, upcoming events, and whether the kill fact occurred. It informs entry timing only.
It changes the 12-month rating only if the kill fact occurs or the thesis inputs change.

## Graham's defensive checklist (India-adapted)

Adequate size (revenue > ₹500 Cr) · current ratio ≥ 2 · positive EPS for 10 years · dividends for 10 years ·
≥33% growth in 3-year average EPS over the decade · P/E ≤ 15× 3-year average EPS · P/E × P/B ≤ 22.5.
Graham formula: V = EPS × (8.5 + 2g) × 4.4 / Y, with Y = current Indian AAA / 10Y G-Sec yield.

## India calibrations

| Parameter | India |
|---|---|
| Risk-free rate | 10Y G-Sec yield (check the current value) |
| Equity risk premium | Damodaran India total ERP (≈6–9% in recent estimates) |
| Tax | 25.17% (Sec 115BAA) or 34.94% (old regime) |
| Stable growth cap | ≈ nominal GDP growth (6–7%) |
| Leases | Ind AS 116: lease liabilities are debt |

## Common mistakes to flag

P/E without growth (check PEG) · terminal value > 80% of EV · mixing FCFF with cost of equity · receivables
growing faster than revenue · off-balance-sheet debt (guarantees, contingent liabilities) · not normalising
one-offs · EV multiples on equity earnings · unverified numbers in the debate · scoring without
corporate-action adjustments.
