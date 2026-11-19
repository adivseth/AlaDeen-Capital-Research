"""Optional backup sources, used only when the primary source fails and the user has added a key.

- Alpha Vantage (prices): https://www.alphavantage.co/documentation/  TIME_SERIES_DAILY
- Firecrawl (documents):  POST https://api.firecrawl.dev/v2/scrape  (PDF -> markdown)
- Exa (documents):        POST https://api.exa.ai/contents           (urls -> text)
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import requests

from aladeen.dataflows.http import DataUnavailable

KEY_ENV = {"alphavantage": "ALPHAVANTAGE_API_KEY", "firecrawl": "FIRECRAWL_API_KEY", "exa": "EXA_API_KEY"}
TIMEOUT = 90


def key(cfg: dict, name: str) -> str | None:
    return (cfg.get("api_keys") or {}).get(name) or os.environ.get(KEY_ENV[name]) or None


# ---------------------------------------------------------------------------- Alpha Vantage
def _av_series(payload: dict) -> pd.DataFrame | None:
    ts = payload.get("Time Series (Daily)")
    if not ts:
        return None
    df = pd.DataFrame.from_dict(ts, orient="index")
    df = df.rename(columns=lambda c: c.split(". ", 1)[-1]).astype(float)
    df.index = pd.to_datetime(df.index)
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def alpha_vantage_daily(base: str, as_of: date, api_key: str, session=requests) -> tuple[pd.DataFrame, str]:
    """Daily OHLCV up to ``as_of``. Returns (frame, source note). Tries the BSE symbol forms Alpha Vantage accepts."""
    last = "no data"
    for symbol in (f"{base}.BSE", f"BSE:{base}"):
        for size in ("full", "compact"):  # full history may need a premium key; compact = last 100 days
            r = session.get("https://www.alphavantage.co/query", timeout=TIMEOUT, params={
                "function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": size, "apikey": api_key})
            payload = r.json() if r.ok else {}
            df = _av_series(payload)
            if df is not None:
                df = df[df.index.date <= as_of]
                note = "" if size == "full" else " (last 100 trading days only: full history needs a premium key)"
                return df, f"Alpha Vantage {symbol}{note}"
            last = (payload.get("Error Message") or payload.get("Information") or payload.get("Note")
                    or f"HTTP {r.status_code}")
            if "Error Message" in payload:
                break  # unknown symbol: compact would fail too
    raise DataUnavailable(f"Alpha Vantage: {last}")


# ---------------------------------------------------------------------------- documents
def firecrawl_text(url: str, api_key: str, session=requests) -> str:
    r = session.post("https://api.firecrawl.dev/v2/scrape", timeout=TIMEOUT,
                     headers={"Authorization": f"Bearer {api_key}"},
                     json={"url": url, "formats": ["markdown"]})
    body = r.json() if r.ok else {}
    text = (body.get("data") or {}).get("markdown") if body.get("success") else None
    if not text:
        raise DataUnavailable(f"Firecrawl could not read {url}: {body.get('error') or f'HTTP {r.status_code}'}")
    return text


def exa_text(url: str, api_key: str, session=requests) -> str:
    r = session.post("https://api.exa.ai/contents", timeout=TIMEOUT, headers={"x-api-key": api_key},
                     json={"urls": [url], "text": True})
    body = r.json() if r.ok else {}
    text = next((x.get("text") for x in body.get("results") or [] if x.get("text")), None)
    if not text:  # Exa can answer 200 with a per-URL failure in "statuses"
        raise DataUnavailable(f"Exa could not read {url}: {body.get('statuses') or f'HTTP {r.status_code}'}")
    return text


def exa_search(query: str, api_key: str, n: int = 5, session=requests, chars: int = 1500) -> list[dict]:
    """Web search via Exa (POST /search). Returns [{title, url, date, text}] with text trimmed."""
    r = session.post("https://api.exa.ai/search", timeout=TIMEOUT, headers={"x-api-key": api_key},
                     json={"query": query, "numResults": n, "contents": {"text": True}})
    if not r.ok:
        raise DataUnavailable(f"Exa search failed: HTTP {r.status_code}")
    return [{"title": x.get("title") or "", "url": x.get("url") or "", "date": (x.get("publishedDate") or "")[:10],
             "text": (x.get("text") or "")[:chars]} for x in r.json().get("results") or []]


# topic -> query; "{name}" is the company name
WEB_TOPICS = {
    "analysts": "{name} share brokerage analyst rating target price rationale",
    "sector": "{name} sector industry outlook India growth drivers regulation",
    "history": "{name} company history key events acquisitions regulatory actions management changes",
}


def web_research(name: str, cfg: dict) -> list[dict]:
    """One Exa search per topic. Empty when no Exa key. Each item carries its topic."""
    k = key(cfg, "exa")
    if not k:
        return []
    out = []
    for topic, q in WEB_TOPICS.items():
        try:
            out += [{"topic": topic, **x} for x in exa_search(q.format(name=name), k, n=cfg.get("web_results", 6),
                                                               chars=cfg.get("web_text_chars", 4000))]
        except (DataUnavailable, requests.RequestException, ValueError):
            continue  # a failed topic is reported as missing by the desk that needed it
    return out


def document_text(url: str, cfg: dict) -> tuple[str, str]:
    """Text of a document via Firecrawl, then Exa. Returns (text, source name)."""
    errors = []
    for name, fn in (("firecrawl", firecrawl_text), ("exa", exa_text)):
        k = key(cfg, name)
        if not k:
            continue
        try:
            return fn(url, k), name.title()
        except (DataUnavailable, requests.RequestException, ValueError) as e:
            errors.append(str(e))
    raise DataUnavailable("; ".join(errors) or "no Firecrawl or Exa key in Settings")
