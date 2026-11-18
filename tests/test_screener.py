import json

from aladeen.dataflows.screener import (
    parse_chart,
    parse_company_page,
    parse_number,
    parse_peers,
)
from aladeen.dataflows.symbols import normalize
from tests.conftest import FIXTURES


def test_parse_number_indian_formats():
    assert parse_number("23,36,016") == 2336016
    assert parse_number("26%") == 26
    assert parse_number("-1,807") == -1807
    assert parse_number("") is None
    assert parse_number("—") is None


def test_company_page_tables(tcs_html):
    p = parse_company_page(tcs_html)
    assert p["name"] == "Tata Consultancy Services Ltd"
    assert p["consolidated"] is True and p["company_id"] and p["warehouse_id"]
    assert p["top_ratios"]["Market Cap"] > 0
    pl = p["tables"]["profit_loss"]
    assert pl["columns"][-1] == "TTM"
    assert {"Sales", "Operating Profit", "Net Profit", "EPS in Rs"} <= set(pl["rows"])
    assert all(len(v) == len(pl["columns"]) for v in pl["rows"].values())
    assert "Total Assets" in p["tables"]["balance_sheet"]["rows"]
    assert "CFO/EBITDA" in p["tables"]["cash_flow"]["rows"]  # long tooltip label trimmed
    assert "Promoters" in p["tables"]["shareholding"]["rows"]
    assert "Compounded Sales Growth" in p["tables"]["growth"]


def test_company_documents(tcs_html):
    d = parse_company_page(tcs_html)["documents"]
    assert d["annual_reports"] and d["annual_reports"][0]["year"]
    assert any("transcript" in c for c in d["concalls"])
    assert d["announcements"][0]["date"]


def test_peers(tcs_peers_html):
    peers = parse_peers(tcs_peers_html)
    assert len(peers) >= 3
    assert "P/E" in peers[0]


def test_chart():
    data = json.loads((FIXTURES / "screener_chart_tcs.json").read_text())
    ch = parse_chart(data)
    assert len(ch["dates"]) == len(ch["close"]) == len(ch["volume"]) > 100


def test_symbols():
    assert normalize("tcs").yahoo == "TCS.NS"
    assert normalize("532540").yahoo == "532540.BO"
    assert normalize("NSE:M&M").base == "M&M"
    assert normalize("RELIANCE.NS").benchmark == "^NSEI"
