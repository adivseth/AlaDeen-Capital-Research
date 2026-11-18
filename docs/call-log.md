# Call log and scoring

Every rated call is recorded so the research can be judged on results, not on prose.

## Columns (A–S)

| Col | Field | Filled by |
|---|---|---|
| A | `call_id` (AC-001, AC-002, …) | `research` |
| B | `call_date` (YYYY-MM-DD, the report date) | `research` |
| C | `company` | `research` |
| D | `ticker` (Yahoo format: `TCS.NS`, `532540.BO`) | `research` |
| E | `rating` (BUY / HOLD / SELL, with qualifier) | `research` |
| F | `target_price` | `research` |
| G | `close_on_call_date` | `research` |
| H | `benchmark` (`^NSEI` for NSE, `^BSESN` for BSE-only) | `research` |
| I | `benchmark_close_on_call_date` | `research` |
| J | `review_date` | `score` |
| K | `close_on_review_date` | `score` |
| L | `benchmark_close_on_review_date` | `score` |
| M | `stock_return` | `score` (CSV) / sheet formula |
| N | `benchmark_return` | `score` (CSV) / sheet formula |
| O | `alpha` | `score` (CSV) / sheet formula |
| P | `verdict` | `score` (CSV) / sheet formula |
| Q | `lesson` | you (or Claude) after scoring |
| R | `report_file` | `research` |
| S | `notes` (corporate actions, data caveats) | `research` / you |

Verdict: "Too early (<12m)" until 365 days have passed; then "Hit" or "Miss" against the rating bands
(BUY hit if price return > 15%, HOLD hit if 0–15%, SELL hit if < 0%).

## Backends

- **CSV (default):** `~/.aladeen/call_log.csv`. All columns are written by code.
- **Google Sheets (optional):** `pip install "aladeen-capital-research[sheets]"`, create a service account,
  share the sheet with it, then set `ALADEEN_GSHEETS_ID` and `ALADEEN_GSHEETS_CREDENTIALS`. The first row must
  hold headers in the A–S order. Put formulas in M–P; **the code never writes M–P on a sheet**. Example
  formulas for row 2:
  - M2 `=IF(AND(G2<>"",K2<>""),K2/G2-1,"")`
  - N2 `=IF(AND(I2<>"",L2<>""),L2/I2-1,"")`
  - O2 `=IF(AND(M2<>"",N2<>""),M2-N2,"")`
  - P2 `=IF(B2="","Not scored",IF(J2-B2<365,"Too early (<12m)",IF(LEFT(E2,3)="BUY",IF(M2>0.15,"Hit","Miss"),IF(LEFT(E2,4)="HOLD",IF(AND(M2>=0,M2<=0.15),"Hit","Miss"),IF(M2<0,"Hit","Miss")))))`

## Scoring rules

- Prices are split- and bonus-adjusted closes (Yahoo `Close`), on the last trading day on or before the date.
- Returns are price-only; note material dividends in `notes`.
- Demergers: add the value of demerged shares received per original share to the review price, and record
  the method in `notes`.
- Never guess a missing call date or price; leave the row "Not scored".

`aladeen score` prints the hit rate for matured calls and the average alpha by rating.
