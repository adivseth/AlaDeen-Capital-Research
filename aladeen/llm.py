"""LLM access: a provider factory and a small runner interface the agents use.

Agents call ``runner.text(...)`` or ``runner.structured(...)``. Swapping the runner swaps
the model provider, or replaces the models entirely (``OfflineRunner`` for tests and the
offline demo), without touching agent code.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from aladeen.config import PROVIDER_BASE_URL, PROVIDER_IDS, PROVIDER_KEY_ENV

T = TypeVar("T", bound=BaseModel)

PROVIDERS = PROVIDER_IDS
_KEY_ENV = PROVIDER_KEY_ENV
_BASE_URL = PROVIDER_BASE_URL


class Runner(Protocol):
    def text(self, system: str, user: str, *, tier: str = "quick", name: str = "") -> str: ...

    def structured(self, system: str, user: str, schema: type[T], *, tier: str = "quick",
                   name: str = "") -> T: ...


def make_chat_model(provider: str, model: str, cfg: dict, use_temperature: bool = True):
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r}; choose from {', '.join(PROVIDERS)}")
    if provider != "anthropic" and model.startswith("claude-"):
        raise ValueError(
            f"Provider is {provider!r} but the model is {model!r}. Set ALADEEN_DEEP_MODEL and "
            "ALADEEN_QUICK_MODEL (or deep_think_llm / quick_think_llm) to that provider's model names.")
    key_env = _KEY_ENV.get(provider)
    key = (cfg.get("api_keys") or {}).get(provider) or (os.environ.get(key_env) if key_env else None)
    if key_env and not key:
        raise RuntimeError(f"No API key for {provider}. Add it in the dashboard Settings page "
                           f"(or set {key_env}).")
    temp = {"temperature": cfg["temperature"]} if use_temperature else {}
    common = {"max_retries": cfg["llm_max_retries"], **temp}
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, max_tokens=cfg["max_tokens"], api_key=key, **common)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, max_output_tokens=cfg["max_tokens"], google_api_key=key,
                                      **common)
    from langchain_openai import ChatOpenAI

    base_url = cfg.get("backend_url") or _BASE_URL.get(provider)
    if provider == "openai_compatible" and not base_url:
        raise ValueError("openai_compatible needs backend_url / ALADEEN_BACKEND_URL")
    api_key = key or os.environ.get("OPENAI_API_KEY") or "not-needed"
    return ChatOpenAI(model=model, max_tokens=cfg["max_tokens"], base_url=base_url, api_key=api_key,
                      **common)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif isinstance(b, str):
                parts.append(b)
        return "".join(parts)
    return str(content)


def _extract_json(text: str) -> Any:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start:end + 1])


def _unsupported_response_format(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) != 400:
        return False
    message = str(exc).lower()
    return ("response_format" in message
            and any(term in message for term in ("unavailable", "not available", "not supported",
                                                 "unsupported", "does not support", "unknown parameter")))


class LangChainRunner:
    """Runs prompts on LangChain chat models with two tiers: ``deep`` and ``quick``."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._models: dict[str, Any] = {}
        self._plain_json_tiers: set[str] = set()
        self._no_temp: set[str] = set()
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def _model(self, tier: str):
        with self._lock:
            if tier not in self._models:
                provider = (self.cfg.get(f"{tier}_provider") or self.cfg["llm_provider"]).lower()
                model = self.cfg["deep_think_llm" if tier == "deep" else "quick_think_llm"]
                self._models[tier] = make_chat_model(provider, model, self.cfg,
                                                     use_temperature=tier not in self._no_temp)
            return self._models[tier]

    def _invoke(self, tier: str, messages, structured: type[BaseModel] | None = None):
        for attempt in range(2):
            model = self._model(tier)
            runnable = model.with_structured_output(structured) if structured else model
            try:
                return runnable.invoke(messages)
            except Exception as e:  # some reasoning models reject temperature
                if attempt == 0 and "temperature" in str(e).lower() and tier not in self._no_temp:
                    with self._lock:
                        self._no_temp.add(tier)
                        self._models.pop(tier, None)
                    continue
                raise
        raise RuntimeError("unreachable")

    def _log(self, name: str, tier: str, t0: float, resp: Any = None) -> None:
        usage = getattr(resp, "usage_metadata", None) or {}
        with self._lock:
            self.calls.append({"agent": name, "tier": tier, "seconds": round(time.time() - t0, 1),
                               "input_tokens": usage.get("input_tokens"),
                               "output_tokens": usage.get("output_tokens")})

    def text(self, system: str, user: str, *, tier: str = "quick", name: str = "") -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        t0 = time.time()
        resp = self._invoke(tier, [SystemMessage(system), HumanMessage(user)])
        self._log(name, tier, t0, resp)
        return _content_to_text(resp.content).strip()

    def structured(self, system: str, user: str, schema: type[T], *, tier: str = "quick",
                   name: str = "") -> T:
        from langchain_core.messages import HumanMessage, SystemMessage

        t0 = time.time()
        msgs = [SystemMessage(system), HumanMessage(user)]
        with self._lock:
            use_native = tier not in self._plain_json_tiers
        if use_native:
            try:
                out = self._invoke(tier, msgs, structured=schema)
                if isinstance(out, dict):
                    out = schema.model_validate(out)
                if isinstance(out, schema):
                    self._log(name, tier, t0)
                    return out
            except Exception as exc:
                if _unsupported_response_format(exc):
                    with self._lock:
                        self._plain_json_tiers.add(tier)
                elif not isinstance(exc, (ValidationError, NotImplementedError, ValueError, TypeError)):
                    raise
        # Fallback: ask for JSON explicitly and validate it
        schema_json = json.dumps(schema.model_json_schema())
        msgs = [SystemMessage(system + "\n\nReturn ONLY a JSON object that matches this JSON schema:\n"
                              + schema_json), HumanMessage(user)]
        resp = self._invoke(tier, msgs)
        self._log(name, tier, t0, resp)
        return schema.model_validate(_extract_json(_content_to_text(resp.content)))


class OfflineRunner:
    """Deterministic runner for tests and the offline demo. No network, no API key.

    ``responder(name, schema_or_None, system, user)`` returns a string (text calls) or a
    pydantic instance / dict (structured calls).
    """

    def __init__(self, responder: Callable[[str, type[BaseModel] | None, str, str], Any], delay: float = 0.0):
        self.responder = responder
        self.delay = delay  # seconds per call, so the dashboard demo shows agents at work
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def text(self, system: str, user: str, *, tier: str = "quick", name: str = "") -> str:
        with self._lock:
            self.calls.append({"agent": name, "tier": tier})
        if self.delay:
            time.sleep(self.delay)
        return str(self.responder(name, None, system, user))

    def structured(self, system: str, user: str, schema: type[T], *, tier: str = "quick",
                   name: str = "") -> T:
        with self._lock:
            self.calls.append({"agent": name, "tier": tier})
        if self.delay:
            time.sleep(self.delay)
        out = self.responder(name, schema, system, user)
        return out if isinstance(out, schema) else schema.model_validate(out)
