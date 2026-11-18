"""Score logged calls: price return vs benchmark, alpha, hit/miss after 12 months."""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import date

PriceFn = Callable[[str, date], tuple[date, float]]


def _f(x) -> float | None:
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def verdict(rating: str, stock_return: float, days: int, bands: dict) -> str:
    if days < 365:
        return "Too early (<12m)"
    r = rating.upper().split()[0] if rating else ""
    if r == "BUY":
        return "Hit" if stock_return > bands["buy"] else "Miss"
    if r == "HOLD":
        return "Hit" if bands["sell"] <= stock_return <= bands["buy"] else "Miss"
    if r in ("SELL", "AVOID", "REDUCE"):
        return "Hit" if stock_return < bands["sell"] else "Miss"
    return "Unrated"


def compute_row(row: dict, bands: dict) -> dict:
    g, k = _f(row.get("close_on_call_date")), _f(row.get("close_on_review_date"))
    i, l_ = _f(row.get("benchmark_close_on_call_date")), _f(row.get("benchmark_close_on_review_date"))
    if not row.get("call_date") or None in (g, k, i, l_) or not g or not i:
        row["verdict"] = row.get("verdict") or "Not scored"
        return row
    sr, br = k / g - 1, l_ / i - 1
    days = (date.fromisoformat(row["review_date"]) - date.fromisoformat(row["call_date"])).days
    row["stock_return"] = f"{sr:.4f}"
    row["benchmark_return"] = f"{br:.4f}"
    row["alpha"] = f"{sr - br:.4f}"
    row["verdict"] = verdict(row.get("rating", ""), sr, days, bands)
    return row


def default_price_fn(symbol: str, on: date) -> tuple[date, float]:
    """Split/bonus-adjusted close on the last trading day on or before ``on`` (Yahoo)."""
    from aladeen.dataflows import yahoo

    df = yahoo.ohlcv(symbol, on, years=0.1)
    return df.index[-1].date(), float(df["close"].iloc[-1])


def score(rows: list[dict], review_on: date, bands: dict, price_fn: PriceFn = default_price_fn,
          log=lambda m: None) -> tuple[list[dict], dict]:
    for row in rows:
        if not row.get("call_date"):
            row["verdict"] = "Not scored"
            continue
        try:
            d1, px = price_fn(row["ticker"], review_on)
            _, bx = price_fn(row["benchmark"], review_on)
        except Exception as e:  # noqa: BLE001
            log(f"{row.get('call_id')}: price unavailable ({e})")
            continue
        row["review_date"] = d1.isoformat()
        row["close_on_review_date"] = f"{px:.2f}"
        row["benchmark_close_on_review_date"] = f"{bx:.2f}"
        compute_row(row, bands)
    return rows, summarize(rows)


def summarize(rows: list[dict]) -> dict:
    scored = [r for r in rows if r.get("alpha") not in ("", None)]
    matured = [r for r in scored if r.get("verdict") in ("Hit", "Miss")]
    hits = [r for r in matured if r["verdict"] == "Hit"]
    by_rating: dict[str, list[float]] = defaultdict(list)
    for r in scored:
        by_rating[(r.get("rating") or "?").split()[0].upper()].append(float(r["alpha"]))
    return {
        "calls": len(rows),
        "scored": len(scored),
        "matured_12m": len(matured),
        "hits": len(hits),
        "hit_rate": len(hits) / len(matured) if matured else None,
        "avg_alpha_all": statistics.mean(float(r["alpha"]) for r in scored) if scored else None,
        "avg_alpha_by_rating": {k: statistics.mean(v) for k, v in by_rating.items()},
    }
