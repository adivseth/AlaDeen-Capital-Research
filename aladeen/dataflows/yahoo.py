"""Yahoo Finance via yfinance: daily OHLCV, company snapshot and a statement cross-check."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from aladeen.dataflows.http import DataUnavailable

_INFO_KEYS = [
    "longName", "shortName", "sector", "industry", "website", "currency", "marketCap",
    "sharesOutstanding", "beta", "totalCash", "totalDebt", "dividendYield", "trailingPE",
    "priceToBook", "enterpriseValue", "enterpriseToEbitda", "averageVolume", "averageVolume10days",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "bookValue", "trailingEps", "heldPercentInsiders",
    "heldPercentInstitutions", "longBusinessSummary", "fullTimeEmployees",
    "targetMeanPrice", "targetMedianPrice", "targetHighPrice", "targetLowPrice", "numberOfAnalystOpinions",
    "recommendationKey",
]


def ohlcv(symbol: str, as_of: date, years: int = 10) -> pd.DataFrame:
    """Daily bars up to and including ``as_of`` (no look-ahead). Index: DatetimeIndex."""
    import yfinance as yf

    start = as_of - timedelta(days=int(365.25 * years) + 5)
    try:
        df = yf.Ticker(symbol).history(
            start=start.isoformat(), end=(as_of + timedelta(days=1)).isoformat(), auto_adjust=False
        )
    except Exception as e:  # yfinance raises many types
        raise DataUnavailable(f"Yahoo price history failed for {symbol}: {e}") from e
    if df is None or df.empty:
        raise DataUnavailable(f"Yahoo returned no prices for {symbol}")
    df = df.rename(columns=str.lower)
    keep = [c for c in ["open", "high", "low", "close", "adj close", "volume"] if c in df.columns]
    df = df[keep].rename(columns={"adj close": "adj_close"})
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[df["close"].notna()]
    df = df[df.index.date <= as_of]
    return df


def snapshot(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    t = yf.Ticker(symbol)
    out: dict[str, Any] = {"symbol": symbol}
    try:
        info = t.info or {}
        out["info"] = {k: info.get(k) for k in _INFO_KEYS if info.get(k) is not None}
    except Exception as e:
        out["info"] = {}
        out["info_error"] = str(e)
    try:  # corporate actions: per-share history must be read with these in mind
        sp = t.splits
        out["splits"] = {str(d.date()): float(r) for d, r in sp.items()} if sp is not None and len(sp) else {}
        dv = t.dividends
        out["dividends"] = ({str(d.date()): float(x) for d, x in dv.tail(12).items()}
                            if dv is not None and len(dv) else {})
    except Exception as e:  # noqa: BLE001
        out["actions_error"] = str(e)
    try:
        fin = t.financials
        if fin is not None and not fin.empty:
            rows = {}
            for label in ["Total Revenue", "Net Income", "EBITDA", "Operating Income"]:
                if label in fin.index:
                    rows[label] = {str(c.date()): _f(v) for c, v in fin.loc[label].items()}
            out["annual_income"] = rows
    except Exception as e:
        out["financials_error"] = str(e)
    try:
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            col = bs.columns[0]
            pick = {}
            for label in [
                "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments",
                "Other Short Term Investments", "Total Debt", "Minority Interest",
                "Stockholders Equity", "Current Assets", "Current Liabilities",
                "Total Liabilities Net Minority Interest", "Ordinary Shares Number",
            ]:
                if label in bs.index:
                    pick[label] = _f(bs.loc[label, col])
            out["balance_sheet_latest"] = {"date": str(col.date()), "values": pick}
    except Exception as e:
        out["balance_sheet_error"] = str(e)
    return out


def _f(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
