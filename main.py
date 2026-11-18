"""Minimal Python example: run a research without the dashboard. Needs an AI provider key (see Settings)."""

from datetime import date

from aladeen import load_config
from aladeen.firm.orchestrator import ResearchRun

cfg = load_config()
state = ResearchRun(cfg, "TCS", date.today()).run()
print(state["final"]["rating"], round(state["valuation"]["target_price"], 2), "->", state["paths"]["report"])
