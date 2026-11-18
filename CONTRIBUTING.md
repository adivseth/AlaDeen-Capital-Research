# Contributing

Thank you for helping. Useful contributions, roughly in order of impact:

1. **Data sources:** NSE F&O open interest and participant data, bulk/block deals, promoter pledge (SAST),
   credit-rating actions, results calendar. Add a module in `aladeen/dataflows/`; never let an LLM fetch numbers.
2. **Parser robustness:** Screener.in layout changes; banks, NBFCs and insurers; companies without
   consolidated statements.
3. **Valuation:** FCFE and DDM paths, SOTP for holding companies, NAV for real estate, cyclical normalisation.
4. **Evaluation:** a backtest over the call log (hit rate and alpha by rating, sector and model).

## Rules

- Code computes; agents judge. No arithmetic in prompts or agent output.
- Every new figure in the report must be traceable to the fact pack, so the number audit can check it.
- Tests must run offline. Use fixtures in `tests/fixtures/` and the synthetic company in `aladeen/demo.py`.
- `pytest` and `ruff check aladeen tests` must pass.
- Do not commit API keys, `.env`, service-account files or generated reports of real companies.

## Development setup

```bash
pip install -e ".[dev]"
pytest
aladeen demo
```
