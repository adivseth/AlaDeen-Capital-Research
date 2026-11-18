"""Optional backup sources (Alpha Vantage, Firecrawl, Exa) with fake HTTP responses — no network."""

from datetime import date

import pytest

from aladeen.dataflows import backups
from aladeen.dataflows.documents import load_document
from aladeen.dataflows.http import DataUnavailable


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.ok = body, status, status < 400

    def json(self):
        return self.body


class Fake:
    """Returns queued responses and records each call."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append(kw.get("params"))
        return self.responses.pop(0)

    post = get


SERIES = {"Time Series (Daily)": {
    "2026-11-17": {"1. open": "100", "2. high": "110", "3. low": "95", "4. close": "105", "5. volume": "1000"},
    "2026-11-18": {"1. open": "105", "2. high": "112", "3. low": "101", "4. close": "111", "5. volume": "1200"},
    "2026-11-19": {"1. open": "111", "2. high": "113", "3. low": "108", "4. close": "109", "5. volume": "900"},
}}


def test_alpha_vantage_parses_and_stops_at_as_of():
    df, note = backups.alpha_vantage_daily("TCS", date(2026, 11, 18), "k", Fake(Resp(SERIES)))
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].tolist() == [105.0, 111.0]  # no look-ahead past the analysis date
    assert note == "Alpha Vantage TCS.BSE"


def test_alpha_vantage_premium_falls_back_to_compact_and_says_so():
    fake = Fake(Resp({"Information": "premium endpoint"}), Resp(SERIES))
    df, note = backups.alpha_vantage_daily("TCS", date(2026, 11, 19), "k", fake)
    assert [c["outputsize"] for c in fake.calls] == ["full", "compact"]
    assert "last 100 trading days" in note and len(df) == 3


def test_alpha_vantage_unknown_symbol_tries_other_form_then_fails():
    bad = {"Error Message": "Invalid API call"}
    fake = Fake(Resp(bad), Resp(bad))
    with pytest.raises(DataUnavailable, match="Invalid API call"):
        backups.alpha_vantage_daily("NOPE", date(2026, 11, 19), "k", fake)
    assert [c["symbol"] for c in fake.calls] == ["NOPE.BSE", "BSE:NOPE"]


def test_firecrawl_and_exa():
    assert backups.firecrawl_text("u", "k", Fake(Resp({"success": True, "data": {"markdown": "# AR"}}))) == "# AR"
    with pytest.raises(DataUnavailable):
        backups.firecrawl_text("u", "k", Fake(Resp({"success": False, "error": "blocked"})))
    assert backups.exa_text("u", "k", Fake(Resp({"results": [{"url": "u", "text": "hello"}]}))) == "hello"
    with pytest.raises(DataUnavailable):  # Exa answers 200 with a per-URL failure
        backups.exa_text("u", "k", Fake(Resp({"results": [], "statuses": [{"id": "u", "status": "error"}]})))


def test_document_text_needs_a_key(monkeypatch):
    for env in backups.KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(DataUnavailable, match="no Firecrawl or Exa key"):
        backups.document_text("u", {"api_keys": {}})


def test_load_document_uses_fallback_when_download_fails():
    class Blocked:
        def get(self, url, binary=False):
            raise DataUnavailable("HTTP 403")

    doc = load_document(Blocked(), "concall", "Concall Q2", "u", "Q2", "full", 10_000,
                        fallback=lambda url: ("x" * 9000, "Firecrawl"))
    assert doc.error is None and doc.title == "Concall Q2 (read via Firecrawl)" and doc.pages == 3
    doc = load_document(Blocked(), "concall", "Concall Q2", "u", "Q2", "full", 10_000)
    assert "403" in doc.error


def test_exa_search_and_web_material():
    from aladeen.dataflows.factpack import FactPack
    from aladeen.firm import context as cx

    body = {"results": [{"title": "Broker initiates BUY", "url": "https://x", "publishedDate": "2026-11-01T00:00:00Z",
                         "text": "Target 500 " * 300}]}
    res = backups.exa_search("q", "k", session=Fake(Resp(body)))
    assert res[0]["date"] == "2026-11-01" and len(res[0]["text"]) == 1500
    fp = FactPack(ticker="T", yahoo_symbol="T.NS", exchange="NSE", as_of="2026-11-19", benchmark="^NSEI",
                  web=[{"topic": "analysts", **res[0]}])
    assert "Broker initiates BUY" in cx.web_md(fp, "analysts")
    assert "needs an Exa key" in cx.web_md(fp, "sector")
