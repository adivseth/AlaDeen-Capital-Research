"""Configuration: defaults < environment variables < dashboard settings < explicit overrides.

Market inputs (risk-free rate, equity risk premium) are dated defaults. Review them in the
dashboard Settings page before relying on a valuation.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# Direct providers. OpenAI-compatible ones are reached at the official base URL below
# (each taken from the provider's own API docs); "Server URL" in Settings overrides it, e.g. for another region.
PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "moonshot": "MOONSHOT_API_KEY",
    "qwen": "DASHSCOPE_API_KEY", "mistral": "MISTRAL_API_KEY", "zai": "ZAI_API_KEY", "meta": "LLAMA_API_KEY",
    "xiaomi": "MIMO_API_KEY", "openrouter": "OPENROUTER_API_KEY",
}
PROVIDER_BASE_URL = {
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "moonshot": "https://api.moonshot.ai/v1",  # China: https://api.moonshot.cn/v1
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",  # Singapore; US/China endpoints differ
    "mistral": "https://api.mistral.ai/v1",
    "zai": "https://api.z.ai/api/paas/v4",  # China: https://open.bigmodel.cn/api/paas/v4
    "meta": "https://api.llama.com/compat/v1",  # Llama API's OpenAI-compatibility endpoint
    "xiaomi": "https://api.xiaomimimo.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}
PROVIDER_IDS = (*PROVIDER_KEY_ENV, "ollama", "openai_compatible")
DESKS = ["fundamentals", "business", "governance", "filings", "news", "technical"]

DEFAULT_CONFIG: dict[str, Any] = {
    # ---------------------------------------------------------------- AI models
    # anthropic | openai | google | xai | openrouter | ollama | openai_compatible
    "llm_provider": "anthropic",
    "deep_provider": None,  # optional: a different provider for the senior tier
    "quick_provider": None,
    # Senior tier: CIO, valuation analyst, chief risk officer, council chair.
    "deep_think_llm": "claude-opus-5-5",
    # Analyst tier: research desks, bull and bear advocates, council advisors.
    "quick_think_llm": "claude-sonnet-5-5",
    "backend_url": None,
    "temperature": 0.2,
    "max_tokens": 8000,
    "llm_max_retries": 3,
    # ---------------------------------------------------------------- Firm workflow
    "desks": list(DESKS),
    "cio_revision_rounds": 1,  # times the CIO may send memos back for revision
    "max_debate_rounds": 1,  # rebuttal rounds after the opening bull and bear cases
    "run_council": True,  # independent 5-advisor council after CIO sign-off
    "log_calls": True,
    "output_language": "English",
    # ---------------------------------------------------------------- Data
    "history_years": 10,
    "benchmark": "^NSEI",  # Nifty 50
    "news_lookback_days": 90,
    "max_annual_reports": 5,
    "max_concall_transcripts": 4,
    "document_mode": "focused",  # focused | full
    "document_char_budget": 60000,
    "filings_chars_per_document": 30000,  # focused mode: per document; the latest call/deck is read in full
    "max_presentations": 2,  # investor presentations of the latest quarters
    "max_announcements_read": 5,  # newest exchange announcements read in full
    "announcement_chars": 3000,
    "web_results": 6,  # Exa results per web-research topic
    "web_text_chars": 4000,
    "fetch_documents": True,
    "http_timeout": 30,
    # ---------------------------------------------------------------- Valuation
    # India 10Y G-Sec yield. RBI reported 7.22% on 11-Nov-2026 (6.94% GS 2036).
    "risk_free_rate": 0.0722,
    # India total equity risk premium (includes the country risk premium): Damodaran, January 2026.
    "equity_risk_premium": 0.0708,
    # India sovereign default spread (Damodaran, January 2026). Netted off the G-Sec yield to get the
    # INR riskless rate, because the total ERP above already prices country risk. Set 0 to disable.
    "country_default_spread": 0.0187,
    "blume_adjust_beta": True,  # adjusted beta = 0.67 x regression beta + 0.33
    "roll_forward_target": True,  # 12-month target = value today x (1 + Ke) - year-1 dividend
    # The CIO must explain or revise a target this far from both the price and the broker consensus.
    "reality_check_threshold": 0.25,
    "tax_rate": 0.2517,
    "terminal_growth_cap": 0.065,
    "dcf_weight": 0.6,
    "scenario_probabilities": {"bear": 0.2, "base": 0.6, "bull": 0.2},
    "scenario_multiple_factors": {"bear": 0.8, "base": 1.0, "bull": 1.15},
    "margin_of_safety": 0.33,
    "tv_share_warning": 0.80,
    "rating_bands": {"buy": 0.15, "sell": 0.0},
    # ---------------------------------------------------------------- Dashboard
    "host": "127.0.0.1",
    "port": 8765,
    "open_browser": True,
    # ---------------------------------------------------------------- Paths
    "home_dir": str(Path.home() / ".aladeen"),
    "results_dir": None,  # defaults to <home_dir>/research
    "cache_dir": None,  # defaults to <home_dir>/cache
    "call_log_path": None,  # defaults to <home_dir>/call_log.csv
    "gsheets_spreadsheet_id": None,
    "gsheets_worksheet": "Calls",
    "gsheets_credentials": None,
    # ---------------------------------------------------------------- Research brief
    # The owner's standing instructions: the CIO and every desk read them on every research.
    "research_brief": """Perform a deep dive into the business of the company. Look into the macro and micro factors affecting the business, recent events in the company's history that will have an impact on its business, any future events bearing on the business, an analysis of the moat, and the analysts tracking the stock with their rationale. Be unbiased, do not invent any fact, and cross-check facts. Research comprehensively, from all angles.
Evaluate the business on its future prospects, not just its fundamentals and technicals, because a stock is priced for what it is going to deliver in the future, not just for its past financials. Evaluate the sector and its prospects (direct and ancillary impact), the services the company provides, the customers it targets, the projected revenue, and recent trends and news affecting the stock or the sector.
Before finalising, assess whether complete and accurate research has been done. If not, do it.""",
    # After the independent council, send its gaps back to the desks once and re-sign the decision.
    "council_followup": True,
    "council_recheck": True,  # after a follow-up that changed memos, the council reviews once more
    "block_incomplete_reports": True,  # still incomplete after that: publish as a draft, do not log the call
    # A decision-changing conflict pauses the research until the owner rules on it (dashboard or `aladeen resolve`).
    # Off: the desk work is published as a draft at once and the call is not logged.
    "hold_for_owner": True,
    # Rulings on a company are reused by its next research for this many days (0: every research asks afresh).
    "carry_rulings_days": 90,
    "reality_check_revision": True,  # a target far from price and consensus goes back to the analyst once
    "cio_valuation_challenge": True,  # the CIO may dispute the valuation once before signing
    # Call IDs continue from this number when the local log is behind a shared sheet (e.g. 24 -> AC-025).
    "call_id_floor": 0,
    # ---------------------------------------------------------------- Report
    "firm_name": "AlaDeen Capital Research",
    "analyst_name": "AlaDeen Capital Research AI team",
}

# Keys the dashboard Settings page may change (plus "api_keys").
EDITABLE = [
    "llm_provider", "deep_provider", "quick_provider", "deep_think_llm", "quick_think_llm", "backend_url",
    "temperature", "max_tokens", "desks", "cio_revision_rounds", "max_debate_rounds", "run_council",
    "log_calls", "output_language", "fetch_documents", "document_mode", "max_annual_reports",
    "max_concall_transcripts", "news_lookback_days", "risk_free_rate", "equity_risk_premium", "country_default_spread",
    "blume_adjust_beta", "roll_forward_target", "reality_check_threshold", "tax_rate",
    "terminal_growth_cap", "dcf_weight", "scenario_probabilities", "scenario_multiple_factors",
    "margin_of_safety", "rating_bands", "firm_name", "analyst_name", "port", "open_browser",
    "research_brief", "council_followup", "council_recheck", "block_incomplete_reports", "hold_for_owner",
    "carry_rulings_days",
    "reality_check_revision",
    "cio_valuation_challenge", "call_id_floor", "filings_chars_per_document", "max_presentations",
    "max_announcements_read", "web_results", "web_text_chars",
]

_ENV_MAP: dict[str, tuple[str, type]] = {
    "ALADEEN_LLM_PROVIDER": ("llm_provider", str),
    "ALADEEN_DEEP_PROVIDER": ("deep_provider", str),
    "ALADEEN_QUICK_PROVIDER": ("quick_provider", str),
    "ALADEEN_DEEP_MODEL": ("deep_think_llm", str),
    "ALADEEN_QUICK_MODEL": ("quick_think_llm", str),
    "ALADEEN_BACKEND_URL": ("backend_url", str),
    "ALADEEN_TEMPERATURE": ("temperature", float),
    "ALADEEN_MAX_TOKENS": ("max_tokens", int),
    "ALADEEN_MAX_DEBATE_ROUNDS": ("max_debate_rounds", int),
    "ALADEEN_RISK_FREE_RATE": ("risk_free_rate", float),
    "ALADEEN_EQUITY_RISK_PREMIUM": ("equity_risk_premium", float),
    "ALADEEN_DOCUMENT_MODE": ("document_mode", str),
    "ALADEEN_HOME": ("home_dir", str),
    "ALADEEN_RESULTS_DIR": ("results_dir", str),
    "ALADEEN_CALL_LOG": ("call_log_path", str),
    "ALADEEN_GSHEETS_ID": ("gsheets_spreadsheet_id", str),
    "ALADEEN_GSHEETS_CREDENTIALS": ("gsheets_credentials", str),
    "ALADEEN_FIRM_NAME": ("firm_name", str),
    "ALADEEN_PORT": ("port", int),
    "ALADEEN_HOST": ("host", str),
}


def _deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def settings_path(home_dir: str | None = None) -> Path:
    home = Path(home_dir or os.environ.get("ALADEEN_HOME") or DEFAULT_CONFIG["home_dir"]).expanduser()
    return home / "settings.json"


def read_settings(home_dir: str | None = None) -> dict[str, Any]:
    p = settings_path(home_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_config(overrides: dict[str, Any] | None = None, use_env: bool = True,
                use_settings: bool = True) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if use_env:
        try:
            from dotenv import load_dotenv

            load_dotenv(override=False)
        except ImportError:  # pragma: no cover
            pass
        for env, (key, typ) in _ENV_MAP.items():
            val = os.environ.get(env)
            if val not in (None, ""):
                cfg[key] = typ(val)
        if os.environ.get("ALADEEN_NO_COUNCIL"):
            cfg["run_council"] = False
    if overrides and overrides.get("home_dir"):
        cfg["home_dir"] = overrides["home_dir"]
    cfg["api_keys"] = {}
    if use_settings:
        saved = read_settings(cfg["home_dir"])
        _deep_update(cfg, {k: v for k, v in saved.items() if k in EDITABLE and v is not None})
        cfg["api_keys"] = {k: v for k, v in (saved.get("api_keys") or {}).items() if v}
    if overrides:
        _deep_update(cfg, {k: v for k, v in overrides.items() if v is not None})
    home = Path(cfg["home_dir"]).expanduser()
    cfg["home_dir"] = str(home)
    cfg["results_dir"] = str(Path(cfg["results_dir"]).expanduser()) if cfg["results_dir"] else str(home / "research")
    cfg["cache_dir"] = cfg["cache_dir"] or str(home / "cache")
    cfg["call_log_path"] = cfg["call_log_path"] or str(home / "call_log.csv")
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict[str, Any]) -> None:
    probs = cfg["scenario_probabilities"]
    if abs(sum(probs.values()) - 1.0) > 1e-6:
        raise ValueError(f"Scenario probabilities must sum to 1, got {probs}")
    if not 0 <= cfg["dcf_weight"] <= 1:
        raise ValueError("DCF weight must be between 0 and 1")
    if cfg["terminal_growth_cap"] >= cfg["risk_free_rate"] + cfg["equity_risk_premium"]:
        raise ValueError("Terminal growth cap must be below the cost of equity")
    if cfg["document_mode"] not in ("focused", "full"):
        raise ValueError("Document mode must be 'focused' or 'full'")
    for key in ("llm_provider", "deep_provider", "quick_provider"):
        if cfg.get(key) and cfg[key] not in PROVIDER_IDS:
            raise ValueError(f"Unknown AI provider {cfg[key]!r}; choose from {', '.join(PROVIDER_IDS)}")
    if len(cfg.get("research_brief") or "") > 8000:
        raise ValueError("The research brief is too long (max 8,000 characters)")
    unknown = [d for d in cfg["desks"] if d not in DESKS]
    if unknown:
        raise ValueError(f"Unknown research desks: {unknown}")
    if not cfg["desks"]:
        raise ValueError("Select at least one research desk")
