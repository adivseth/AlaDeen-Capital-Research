# AlaDeen Capital Research — guidance for Claude Code

This repo is an AI research firm for Indian listed companies: a CIO agent leads research desks, and a local
browser dashboard shows the work. When a user asks you to
research, value or track an Indian stock, use the tools here rather than computing figures yourself.

## How to research a company

1. **Data and checks first (no LLM):** `aladeen data TICKER --out results/TICKER/data` writes
   `factpack.json` and `factsheet.md`. Read the fact sheet. Note reconciliation mismatches and data caveats.
2. **Full research (needs an API key):** `aladeen TICKER` opens the dashboard and runs the firm; use
   `aladeen research TICKER --headless` when there is no browser. Output goes to `~/.aladeen/research/<run id>/`
   (`report.html`, `research.json`, `transcript.md`, `factpack.json`, `events.json`) and a call-log row is added.
   Without an API key, use `aladeen value TICKER` for the deterministic valuation and write the
   qualitative sections yourself, following `.claude/skills/equity-valuation-research/SKILL.md`.
3. **Quarterly update:** `aladeen track TICKER` (short-term check, announcements, prior call, kill fact).
4. **"Score my calls":** `aladeen score`, then report the hit rate and alpha by rating.

## Rules

- Never do arithmetic in prose. Every figure comes from the fact pack or the valuation engine. If you need a
  new calculation, write Python that reads `factpack.json` and run it.
- Flag governance issues prominently. Treat Screener ratios with suspicion where reconciliation fails.
- The rating must follow the bands: BUY > 15%, HOLD 0–15%, SELL < 0% expected 12-month total return.
- Before the final rating: bull vs bear debate, the risk office (aggressive / neutral / conservative), and a kill fact. Then run the
  `llm-council` skill on the finished report.
- Reports are not investment advice; the authors are not SEBI-registered. Keep the disclaimer.

## Code map

See [docs/architecture.md](docs/architecture.md).

| Path | What it is |
|---|---|
| `aladeen/dataflows/` | Screener.in parser, Yahoo prices, Google News, BSE documents, logo, `FactPack` |
| `aladeen/quant/` | Statements, reconciliation, technicals, charts, valuation engine, number audit |
| `aladeen/firm/` | The firm: roster, prompts (house rules), schemas, staff, CIO orchestrator (`ResearchRun`), event log |
| `aladeen/server/` | FastAPI dashboard API, run manager, SQLite research archive |
| `aladeen/web/` | Dashboard single-page app (HTML/CSS/JS, no build step) |
| `aladeen/calllog/` | Call log (CSV or Google Sheets) and scoring |
| `aladeen/report/` | Jinja2 HTML report template and renderer |
| `aladeen/knowledge/` | Methodology notes injected into prompts |
| `tests/` | Offline tests: fixtures, synthetic data, scripted agents |

Run `pytest` and `ruff check aladeen tests` before committing.
