# Configuration

Precedence: defaults in `aladeen/config.py` < environment variables (and `.env`) < the dashboard Settings page
(`~/.aladeen/settings.json`) < overrides passed to `load_config()`. Most settings below can be changed in Settings.

## Market inputs — review before use

| Key | Env | Default | Source / note |
|---|---|---|---|
| `risk_free_rate` | `ALADEEN_RISK_FREE_RATE` | 0.0722 | RBI-reported yield on the benchmark 10Y G-Sec (6.94% GS 2036) for 11-Nov-2026. Update it when you run. |
| `equity_risk_premium` | `ALADEEN_EQUITY_RISK_PREMIUM` | 0.07 | India total ERP (mature-market ERP + country risk premium). Published estimates for early 2026 ranged ~6–9%; Damodaran publishes updates in January and July. |
| `tax_rate` | — | 0.2517 | Section 115BAA rate. |
| `terminal_growth_cap` | — | 0.065 | Long-run nominal GDP proxy; terminal growth is capped here. |
| `rating_bands` | — | buy 0.15 / sell 0.0 | Expected 12-month total return bands. |
| `dcf_weight` | — | 0.6 | Weight of the intrinsic value in each scenario; the rest is the peer multiple. |
| `scenario_probabilities` | — | 0.2 / 0.6 / 0.2 | Bear / base / bull. Must sum to 1. |
| `scenario_multiple_factors` | — | 0.8 / 1.0 / 1.15 | Applied to the peer-multiple value per scenario. |
| `margin_of_safety` | — | 0.33 | Entry price = base value × (1 − MoS). |
| `tv_share_warning` | — | 0.80 | Warn when terminal value exceeds this share of EV. |

## LLMs

| Key | Env | Default |
|---|---|---|
| `llm_provider` | `ALADEEN_LLM_PROVIDER` | `anthropic` |
| `deep_think_llm` | `ALADEEN_DEEP_MODEL` | `claude-opus-5-5` |
| `quick_think_llm` | `ALADEEN_QUICK_MODEL` | `claude-sonnet-5-5` |
| `deep_provider`, `quick_provider` | `ALADEEN_DEEP_PROVIDER`, `ALADEEN_QUICK_PROVIDER` | same as `llm_provider` |
| `backend_url` | `ALADEEN_BACKEND_URL` | provider default |
| `temperature` | `ALADEEN_TEMPERATURE` | 0.2 (dropped automatically for models that reject it) |
| `max_tokens` | `ALADEEN_MAX_TOKENS` | 8000 |

## Workflow and data

| Key | Env / flag | Default |
|---|---|---|
| `desks` | Settings | all six |
| `cio_revision_rounds` | Settings | 1 (how often the CIO may send memos back) |
| `max_debate_rounds` | `ALADEEN_MAX_DEBATE_ROUNDS` | 1 |
| `run_council` | `ALADEEN_NO_COUNCIL=1` | on |
| `log_calls` | Settings | on |
| `fetch_documents` | Settings | on |
| `document_mode` | `ALADEEN_DOCUMENT_MODE` | `focused` |
| `max_annual_reports` / `max_concall_transcripts` | — | 5 / 4 |
| `history_years` | — | 10 |
| `news_lookback_days` | — | 90 |

## Paths

| Key | Env | Default |
|---|---|---|
| `home_dir` | `ALADEEN_HOME` | `~/.aladeen` |
| `cache_dir` | — | `~/.aladeen/cache` (HTTP cache, 12-hour TTL) |
| `results_dir` | `ALADEEN_RESULTS_DIR` | `~/.aladeen/research` |
| `call_log_path` | `ALADEEN_CALL_LOG` | `~/.aladeen/call_log.csv` |
| `gsheets_spreadsheet_id` | `ALADEEN_GSHEETS_ID` | none (CSV log) |
| `gsheets_credentials` | `ALADEEN_GSHEETS_CREDENTIALS` | none |
| `port` / `host` | `ALADEEN_PORT` / `ALADEEN_HOST` | 8765 / 127.0.0.1 |

Backup data sources (optional): `ALPHAVANTAGE_API_KEY`, `FIRECRAWL_API_KEY`, `EXA_API_KEY`, or the same keys in
Settings → Backup data sources. They are used only when Yahoo Finance or a BSE document download fails.

API keys entered in Settings are stored in `~/.aladeen/settings.json` (created with mode 600). Keys in the
environment or `.env` also work; a key saved in Settings takes precedence.
