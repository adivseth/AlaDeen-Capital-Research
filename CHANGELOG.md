# Changelog

## Unreleased

- **Try again for failed research.** A stopped research can be continued under the same id from the run page,
  the archive or `aladeen retry [RUN_ID]`. Each AI answer is journaled (`journal.jsonl`) and the fact pack is frozen,
  so the retry reuses all finished work and runs only what is left. Works after a closed dashboard and after
  switching provider or key. New endpoint `POST /api/runs/{id}/retry`.
- **Dashboard redesign ("The Research Desk").** New visual identity: a printed research bulletin crossed with a
  trading-floor board. Paper and ink with one vermilion accent, Fraunces / IBM Plex type, rubber-stamp ratings,
  ticker-tape masthead, desk-code floor board, pneumatic memo capsules, a telegraph-style activity wire and ledger
  rows. Replaces the sidebar, gradients, emoji and cartoon avatars. Behaviour is unchanged.

## 0.1.0 — 2026-11-19

First public release.

- Browser dashboard (`aladeen TICKER`): new research, live office of agents at work, report viewer with
  HTML/PDF download, research archive, call log with scoring, and a Settings page (AI provider, models,
  API keys, desks, rounds, council, documents, valuation inputs, branding).
- CIO-led research firm: mandate, six research desks in parallel, CIO review with send-backs, valuation
  analyst, bull/bear debate with CIO ruling and kill fact, Chief Risk Officer, CIO decision, compliance
  (rating bands and number audit), independent five-advisor council, publishing.
- Providers: Anthropic Claude, OpenAI, Google Gemini, xAI Grok, DeepSeek, Moonshot (Kimi), Alibaba Qwen, Mistral,
  Z.ai (GLM), Meta Llama API, Xiaomi MiMo (direct), OpenRouter, Ollama, any OpenAI-compatible server.
- Research brief in Settings (the owner's standing instructions, read by the CIO and every desk); wider desk
  coverage: macro/micro factors, sector prospects and ancillary effects, services and customers, company history,
  future prospects, analyst coverage with rationale (via Exa web research).
- Council follow-up: when the council finds the research incomplete, the gaps go back to the desks and the CIO
  re-signs the decision before publishing.
- `/deep-dive <company>` command for Claude Code.
- Optional backup data sources: Alpha Vantage (prices), Firecrawl and Exa (annual reports, concalls).
- Data: Screener.in parser, Yahoo Finance prices, Google News RSS, BSE annual reports and concall transcripts,
  company logos.
- Quant engine: reconciliation checks, CAGRs, TTM, technical indicators and 10-year charts, FCFF DCF with
  sensitivity grid, justified P/B for financials, peer multiples, Graham checks, probability-weighted scenarios.
- 13-section HTML report with appendices; research file (markdown) and JSON outputs.
- Call log (CSV or Google Sheets) scored against the Nifty 50. Offline test suite, Docker.
