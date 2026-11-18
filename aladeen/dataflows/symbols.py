"""Ticker normalisation for Indian listings.

Accepted inputs: ``TCS``, ``TCS.NS``, ``NSE:TCS``, ``500325`` (BSE code), ``500325.BO``, ``BSE:500325``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Symbol:
    raw: str
    base: str  # NSE symbol or BSE numeric code
    exchange: str  # NSE | BSE

    @property
    def yahoo(self) -> str:
        return f"{self.base}.NS" if self.exchange == "NSE" else f"{self.base}.BO"

    @property
    def screener_slug(self) -> str:
        return self.base

    @property
    def benchmark(self) -> str:
        return "^NSEI" if self.exchange == "NSE" else "^BSESN"

    @property
    def display(self) -> str:
        return f"{self.exchange}: {self.base}"


_VALID = re.compile(r"^[A-Z0-9&\-]{1,20}$")


def normalize(ticker: str) -> Symbol:
    t = ticker.strip().upper().replace(" ", "")
    if not t:
        raise ValueError("Empty ticker")
    exchange = None
    if ":" in t:
        ex, t = t.split(":", 1)
        exchange = {"NSE": "NSE", "BSE": "BSE", "NS": "NSE", "BO": "BSE"}.get(ex)
        if exchange is None:
            raise ValueError(f"Unknown exchange prefix in {ticker!r}")
    if t.endswith(".NS"):
        t, exchange = t[:-3], "NSE"
    elif t.endswith(".BO"):
        t, exchange = t[:-3], "BSE"
    if exchange is None:
        exchange = "BSE" if t.isdigit() else "NSE"
    if not _VALID.match(t):
        raise ValueError(f"Invalid ticker {ticker!r}")
    return Symbol(raw=ticker, base=t, exchange=exchange)


def safe_component(text: str) -> str:
    """Make a string safe to use as a file or folder name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "ticker"
