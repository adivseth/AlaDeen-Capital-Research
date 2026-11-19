from datetime import date, timedelta

import pandas as pd
import pytest

from aladeen.dataflows.factpack import build_factpack
from aladeen.dataflows.http import DataUnavailable
from aladeen.demo import synthetic_factpack
from aladeen.server.workbench import portfolio_series, report_changes


def test_changes_match_periods_and_keep_zero():
    def snapshot(periods, sales):
        return {"tables": {"quarters": {"columns": periods, "rows": {"Sales": sales}}}}

    changes = report_changes(snapshot(["Q1", "Q2"], [10, 9]), snapshot(["Q2", "Q3"], [8, 0]))
    assert [(r["period"], r["previous"], r["actual"]) for r in changes] == [("Q2", 9, 8), ("Q3", None, 0)]


def test_portfolio_drawdown_and_attribution():
    days = pd.date_range("2025-03-01", periods=3)
    quotes = {
        k: pd.Series(values, index=days)
        for k, values in {"A": [100, 70, 125], "B": [50, 50, 50], "Index": [100, 95, 107]}.items()
    }
    positions = [dict(ticker=t, sector=t, amount=10000, benchmark="Index") for t in ("A", "B")]
    result = portfolio_series(positions, quotes)
    assert result["total_return"] == pytest.approx(0.125)
    assert result["drawdown"] == pytest.approx(-0.15)
    assert sum(r["contribution"] for r in result["rows"]) == pytest.approx(result["total_return"])
    assert sum(result["sectors"].values()) == pytest.approx(1)


def test_historical_replay_excludes_later_captures(cfg, tmp_path):
    cutoff = date.today() - timedelta(days=5)
    folder = tmp_path / "home" / "snapshots" / "DEMO.NS"
    folder.mkdir(parents=True)
    synthetic_factpack().save(folder / f"{date.today()}T120000.json")
    with pytest.raises(DataUnavailable, match="No archived evidence"):
        build_factpack("DEMO", cutoff, cfg)
    synthetic_factpack(cutoff).save(folder / f"{cutoff}T120000.json")
    fp = build_factpack("DEMO", cutoff, cfg)
    assert fp.as_of == str(cutoff)
    assert fp.prices.index.max().date() <= cutoff
