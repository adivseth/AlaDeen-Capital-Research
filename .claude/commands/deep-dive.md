---
description: Deep-dive equity research on an Indian listed company (AlaDeen Capital Research process)
argument-hint: <company name or NSE/BSE ticker>
---

Perform a deep dive into the business of **$ARGUMENTS**.

Look into the macro and micro factors affecting the business, recent events in company history which will have an
impact on its business, any future events having a bearing on the company's business, analysis of the moat in the
business, and details of analysts tracking the stock with their rationale. Be unbiased in the research and do not
hallucinate on any fact; perform a cross-check of the facts. Do a comprehensive research from all angles.

Evaluate the business on its future prospects also, rather than just fundamentals / technicals, because a stock is
priced for what it is going to deliver in the future and not just its financials. Evaluate the sector it is in and
the prospects of the sector (direct / ancillary impact), the services it is providing, the customers it is
targeting, the projected revenue, and recent trends / news affecting the stock or sector.

There are various fundamental and valuation skills / plugins in Claude; use them.

Before finalising, assess whether complete and accurate research has been done. If not, do it.

Optimise AI model usage: use an orchestrator and sub-agents framework, where Opus does the brainwork and Sonnet /
Haiku are the workers.

## How to run it in this repo

1. Follow `CLAUDE.md`: start with `aladeen data <TICKER> --out results/<TICKER>/data` for verified figures and
   reconciliation; never do arithmetic in prose.
2. Use the connectors that are present (INDmoney, Alpha Vantage, Firecrawl / Exa, Google Sheets call log) as
   described in `CLAUDE.md`, and web search for analyst coverage, sector news and events. Name the source of every
   figure; mark anything that cannot be verified as "not found".
3. Use the `equity-valuation-research` skill for the valuation and the relevant financial-analysis / equity-research
   plugins where available.
4. Before the rating: bull vs bear debate, risk review (aggressive / neutral / conservative) and a kill fact. The
   rating follows the bands (BUY > 15%, HOLD 0–15%, SELL < 0% expected 12-month total return).
5. Run the `llm-council` skill on the finished report; close any gaps it finds, then publish the HTML report and add
   the call to the call log.
