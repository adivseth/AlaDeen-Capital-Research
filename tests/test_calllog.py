from datetime import date

from aladeen.calllog import scoring
from aladeen.calllog.store import CSVStore, next_call_id, prior_calls

BANDS = {"buy": 0.15, "sell": 0.0}


def test_append_and_ids(tmp_path):
    st = CSVStore(tmp_path / "log.csv")
    r1 = st.append({"call_date": "2025-01-10", "company": "X", "ticker": "X.NS", "rating": "BUY"})
    r2 = st.append({"call_date": "2025-02-10", "company": "Y", "ticker": "Y.NS", "rating": "HOLD"})
    assert (r1["call_id"], r2["call_id"]) == ("AC-001", "AC-002")
    assert next_call_id(st.read()) == "AC-003"
    assert len(prior_calls(st.read(), "x.ns")) == 1


def test_scoring_hit_miss_and_too_early():
    prices = {("X.NS", "review"): 130.0, ("^NSEI", "review"): 110.0, ("Y.NS", "review"): 90.0}

    def price_fn(sym, on):
        return on, prices[(sym, "review")]

    rows = [
        {"call_id": "AC-001", "call_date": "2025-01-10", "ticker": "X.NS", "rating": "BUY",
         "close_on_call_date": "100", "benchmark": "^NSEI", "benchmark_close_on_call_date": "100"},
        {"call_id": "AC-002", "call_date": "2025-01-10", "ticker": "Y.NS", "rating": "SELL",
         "close_on_call_date": "100", "benchmark": "^NSEI", "benchmark_close_on_call_date": "100"},
        {"call_id": "AC-003", "call_date": "2026-06-01", "ticker": "X.NS", "rating": "BUY",
         "close_on_call_date": "100", "benchmark": "^NSEI", "benchmark_close_on_call_date": "100"},
        {"call_id": "AC-004", "call_date": "", "ticker": "X.NS", "rating": "BUY"},
    ]
    rows, summary = scoring.score(rows, date(2026, 11, 18), BANDS, price_fn=price_fn)
    assert rows[0]["verdict"] == "Hit" and float(rows[0]["alpha"]) == 0.2
    assert rows[1]["verdict"] == "Hit"  # SELL and the stock fell
    assert rows[2]["verdict"] == "Too early (<12m)"
    assert rows[3]["verdict"] == "Not scored"
    assert summary["matured_12m"] == 2 and summary["hit_rate"] == 1.0


def test_hold_band():
    assert scoring.verdict("HOLD", 0.05, 400, BANDS) == "Hit"
    assert scoring.verdict("HOLD", 0.30, 400, BANDS) == "Miss"
    assert scoring.verdict("BUY (High Risk)", 0.16, 400, BANDS) == "Hit"
