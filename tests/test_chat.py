import json

from fastapi.testclient import TestClient

from aladeen.server import chat
from aladeen.server.app import create_app


def test_chat_uses_only_finished_run_and_valid_evidence(tmp_path, monkeypatch):
    app = create_app(str(tmp_path))
    client = TestClient(app)
    store = app.state.mgr.store
    for ticker in ("ABC", "XYZ"):
        folder = tmp_path / ticker
        folder.mkdir()
        (folder / "research.json").write_text(json.dumps({"final": f"{ticker} thesis"}))
        store.insert(id=ticker, ticker=ticker, as_of="2026-01-01", out_dir=str(folder), status="running")
    payload = {"question": "Explain the thesis"}
    url = "/api/runs/ABC/chat"
    assert client.post("/api/runs/missing/chat", json=payload).status_code == 404
    assert client.post(url, json=payload).status_code == 409
    store.update("ABC", status="done")
    assert client.post(url, json={"question": "  "}).status_code == 422

    def respond(self, system, user, **kwargs):
        assert "ABC thesis" in user and "XYZ thesis" not in user
        return "The thesis is explained here [1]."

    monkeypatch.setattr(chat.LangChainRunner, "text", respond)
    result = client.post(url, json=payload).json()
    assert result["sources"] == [{"id": 1, "section": "research.json / final", "excerpt": "ABC thesis"}]
    assert "[1]" in result["answer"]
    monkeypatch.setattr(chat.LangChainRunner, "text", lambda *a, **kw: "Invented [99]")
    assert "could not verify" in client.post(url, json=payload).json()["answer"]


def test_preserves_price_dates_table_periods_and_filing_identity():
    prices = {"index": ["2026-01-02"], "close": [42]}
    assert list(chat.passages("prices", prices)) == [("prices / 2026-01-02", '{"close": 42}')]
    table = {"columns": ["Mar 2024", "Mar 2025"], "rows": {"Sales": [12, 16]}}
    assert list(chat.passages("P&L", table)) == [("P&L / Sales", '{"Mar 2024": 12, "Mar 2025": 16}')]
    doc = {"title": "Annual Report", "url": "https://example.com/report", "text": "Evidence " * 600}
    excerpts = [(key, text) for key, text in chat.passages("documents", doc) if "excerpt" in key]
    assert excerpts and all(doc["url"] in key and len(text) <= 1600 for key, text in excerpts)
