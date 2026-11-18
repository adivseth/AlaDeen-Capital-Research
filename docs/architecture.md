# Architecture

AlaDeen Capital Research is a small research firm made of AI agents, led by a Chief Investment Officer, with a
local browser dashboard. Its central design choice is the split between **code that produces numbers** and
**agents that produce judgement**.

```
aladeen TCS ──► CLI ──► dashboard (FastAPI, 127.0.0.1:8765) ──► RunManager ──► ResearchRun (thread)
                                 ▲                                                  │
                     browser SPA │◄── long-poll /api/runs/{id}/events ◄── EventLog ◄┘
```

## The research run (`aladeen/firm/orchestrator.py`)

| Phase | Who | What |
|---|---|---|
| Data collection | Data & Quant Desk (code) | Builds the `FactPack`; reconciliation, ratios, technicals, charts. |
| CIO mandate | CIO (senior model) | Key questions, one brief per enabled desk, watch items. |
| Desk research | six desks (analyst model), in parallel | Memos on the material each desk needs. |
| CIO review | CIO + Compliance | Number audit of the memos; CIO accepts or sends back with notes (`cio_revision_rounds`). |
| Valuation | Valuation Analyst + engine | Analyst proposes assumptions; `quant/valuation.py` computes. Failure falls back to defaults and is disclosed. |
| Bull vs bear | advocates + CIO | Openings and rebuttals; CIO rules, names the kill fact. |
| Risk office | Chief Risk Officer | Aggressive / neutral / conservative lenses, risk rating. |
| CIO decision | CIO | `FinalCall`. |
| Compliance | code | Rating forced to the bands; final number audit. |
| Independent council | five advisors + chair | Reviews the signed report (optional). |
| Publication | Publishing Editor (code) | Report, research file, JSON; call-log row. |

Each step emits events (`phase`, `agent`, `message`, `log`, `company`, `done`, `error`) to an `EventLog`. The
dashboard draws the office from them; finished runs replay from `events.json`.

## Layers

| Layer | Package | AI? | Responsibility |
|---|---|---|---|
| Data | `aladeen.dataflows` | no | Fetch and parse; build the `FactPack`. |
| Quant | `aladeen.quant` | no | Statements, reconciliation, indicators, charts, valuation engine, number audit. |
| Firm | `aladeen.firm` | yes | Roster, prompts with house rules, schemas, staff, orchestrator, events. |
| Dashboard | `aladeen.server`, `aladeen.web` | no | API, run manager, SQLite archive, single-page app. |
| Output | `aladeen.report`, `aladeen.calllog` | no | HTML report, research file, call log. |

## Guarantees

1. **Agents never compute.** The Valuation Analyst returns assumptions; the engine does the maths. The CIO's
   rating is replaced by the band rating when they disagree, and the override is recorded.
2. **Every number is audited.** `quant/audit.py` matches numbers in agent text against the material that agent
   was given. Unmatched numbers go to the CIO and to the report appendix.
3. **Reconciliation is visible.** Accounting identities and cross-source checks are reported, never silently
   corrected.
4. **Point-in-time prices.** Price history stops at the analysis date.

## Extending

- **New data source:** a module in `aladeen/dataflows/`, a `FactPack` field, a renderer in `firm/context.py`,
  and the material for the desk in `firm/staff.py`.
- **New desk:** add it to `DESKS` (`config.py`), `ROSTER` (`firm/roster.py`), a role in `firm/prompts.py`,
  material in `staff.desk_material`, and a block in the report template.
- **Different AI:** choose it in Settings, or pass any object with `text()` and `structured()` as `runner=`
  to `ResearchRun`.
