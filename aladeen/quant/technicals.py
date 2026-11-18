"""Technical indicators and price statistics computed from daily bars."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(s, fast) - ema(s, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(s, n)
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + k * sd, "lower": mid - k * sd})


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, 1)
    atr_n = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def add_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    c = df["close"]
    for n in (20, 50, 100, 200):
        df[f"sma{n}"] = sma(c, n)
    df["ema20"] = ema(c, 20)
    df["rsi14"] = rsi(c)
    df = df.join(macd(c))
    bb = bollinger(c)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bb["upper"], bb["mid"], bb["lower"]
    if {"high", "low"}.issubset(df.columns):
        df["atr14"] = atr(df)
        df["adx14"] = adx(df)
    return df


def _ret(c: pd.Series, days: int) -> float | None:
    end = c.index[-1]
    start_target = end - pd.Timedelta(days=days)
    past = c[c.index <= start_target]
    if past.empty:
        return None
    return float(c.iloc[-1] / past.iloc[-1] - 1)


def trailing_returns(c: pd.Series) -> dict[str, float | None]:
    spans = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "3Y": 1095, "5Y": 1826, "10Y": 3652}
    out = {}
    for k, d in spans.items():
        r = _ret(c, d)
        yrs = d / 365.25
        out[k] = r if r is None or yrs <= 1 else (1 + r) ** (1 / yrs) - 1  # CAGR beyond 1 year
    return out


def max_drawdown(c: pd.Series) -> tuple[float, str, str]:
    peak = c.cummax()
    dd = c / peak - 1
    trough = dd.idxmin()
    peak_date = c[:trough].idxmax()
    return float(dd.min()), peak_date.date().isoformat(), trough.date().isoformat()


def beta(stock: pd.Series, bench: pd.Series, years: int = 2) -> float | None:
    """2-year weekly beta vs benchmark (template convention)."""
    cutoff = stock.index[-1] - pd.Timedelta(days=int(365.25 * years))
    s = stock[stock.index >= cutoff].resample("W-FRI").last().pct_change(fill_method=None)
    b = bench[bench.index >= cutoff].resample("W-FRI").last().pct_change(fill_method=None)
    j = pd.concat([s, b], axis=1, join="inner").dropna()
    if len(j) < 40:
        return None
    cov = np.cov(j.iloc[:, 0], j.iloc[:, 1])
    return float(cov[0, 1] / cov[1, 1])


def crosses(df: pd.DataFrame, lookback_days: int = 3652) -> list[dict]:
    if "sma50" not in df or "sma200" not in df:
        return []
    d = df[["sma50", "sma200"]].dropna()
    d = d[d.index >= d.index[-1] - pd.Timedelta(days=lookback_days)] if len(d) else d
    above = d["sma50"] > d["sma200"]
    flips = above.ne(above.shift()) & above.shift().notna()
    return [{"date": i.date().isoformat(), "type": "golden cross" if above[i] else "death cross"}
            for i in d.index[flips]]


def summarize(prices: pd.DataFrame, bench: pd.DataFrame | None = None) -> dict[str, Any]:
    if prices is None or prices.empty:
        return {"available": False}
    df = add_indicators(prices)
    last = df.iloc[-1]
    c = df["close"]
    one_year = c[c.index >= c.index[-1] - pd.Timedelta(days=365)]
    daily = c.pct_change(fill_method=None).dropna()
    s: dict[str, Any] = {
        "available": True,
        "as_of": c.index[-1].date().isoformat(),
        "start": c.index[0].date().isoformat(),
        "observations": len(c),
        "close": float(last["close"]),
        "high_52w": float(one_year.max()),
        "low_52w": float(one_year.min()),
        "returns": trailing_returns(c),
        "volatility_1y": float(daily.tail(252).std() * math.sqrt(252)) if len(daily) > 60 else None,
        "max_drawdown_10y": max_drawdown(c),
        "avg_volume_3m": float(df["volume"].tail(63).mean()) if "volume" in df else None,
        "indicators": {},
        "crosses": crosses(df)[-6:],
    }
    for k in ["sma20", "sma50", "sma100", "sma200", "ema20", "rsi14", "macd", "signal", "hist",
              "bb_upper", "bb_lower", "atr14", "adx14"]:
        if k in df and not pd.isna(last.get(k)):
            s["indicators"][k] = float(last[k])
    ind = s["indicators"]
    sig = []
    if "sma200" in ind:
        sig.append(f"Price {'above' if s['close'] > ind['sma200'] else 'below'} 200-DMA "
                   f"({(s['close'] / ind['sma200'] - 1) * 100:+.1f}%)")
    if "sma50" in ind and "sma200" in ind:
        sig.append(f"50-DMA {'above' if ind['sma50'] > ind['sma200'] else 'below'} 200-DMA")
    if "rsi14" in ind:
        r = ind["rsi14"]
        zone = "overbought (>70)" if r > 70 else "oversold (<30)" if r < 30 else "neutral (30-70)"
        sig.append(f"RSI(14) {r:.1f}: {zone}")
    if "macd" in ind and "signal" in ind:
        sig.append(f"MACD {'above' if ind['macd'] > ind['signal'] else 'below'} signal line")
    if "adx14" in ind:
        sig.append(f"ADX(14) {ind['adx14']:.1f}: {'trending' if ind['adx14'] > 25 else 'weak/no trend'}")
    s["signals"] = sig
    if bench is not None and not bench.empty:
        bc = bench["close"]
        s["benchmark_returns"] = trailing_returns(bc)
        s["beta_2y_weekly"] = beta(c, bc)
        s["relative_1y"] = (None if s["returns"]["1Y"] is None or s["benchmark_returns"]["1Y"] is None
                            else s["returns"]["1Y"] - s["benchmark_returns"]["1Y"])
    return s


def short_term_check(prices: pd.DataFrame, bench: pd.DataFrame | None, windows=(5, 10)) -> dict:
    """Price change over the last N trading days vs the benchmark."""
    out: dict[str, Any] = {}
    if prices is None or prices.empty:
        return out
    c = prices["close"]
    for n in windows:
        if len(c) <= n:
            continue
        r = float(c.iloc[-1] / c.iloc[-1 - n] - 1)
        row: dict[str, Any] = {"from": c.index[-1 - n].date().isoformat(),
                               "to": c.index[-1].date().isoformat(), "stock": r}
        if bench is not None and not bench.empty:
            b = bench["close"]
            b = b[b.index <= c.index[-1]]
            b_start = b[b.index <= c.index[-1 - n]]
            if len(b_start):
                br = float(b.iloc[-1] / b_start.iloc[-1] - 1)
                row["benchmark"] = br
                row["relative"] = r - br
        out[f"{n}d"] = row
    if "volume" in prices:
        v = prices["volume"]
        out["volume_10d_vs_3m"] = float(v.tail(10).mean() / v.tail(63).mean()) if len(v) > 63 else None
    return out
