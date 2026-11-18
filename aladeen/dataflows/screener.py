"""Screener.in client and HTML parser.

Screener publishes 10+ years of standardised Indian financial statements, quarterly
results, shareholding, peers and links to annual reports and concall transcripts
(hosted on BSE). Its derived ratios can occasionally be wrong; the quant layer
re-computes key figures and flags disagreements rather than trusting them.

Use responsibly: the client caches pages and makes only a handful of requests per run.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from aladeen.dataflows.http import DataUnavailable, Http

BASE = "https://www.screener.in"


def parse_number(text: str | None) -> float | None:
    """'1,23,456' -> 123456.0 ; '26%' -> 26.0 ; '-1,807' -> -1807.0 ; '' -> None."""
    if text is None:
        return None
    t = text.strip().replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").strip()
    t = t.replace("−", "-")
    if t in ("", "-", "--", "—"):
        return None
    m = re.match(r"^[+-]?\d+(\.\d+)?$", t)
    return float(t) if m else None


def _clean_label(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s*\+$", "", text).strip()


def _parse_table(table) -> dict[str, Any]:
    head = table.find("thead")
    if head:
        columns = [th.get_text(" ", strip=True) for th in head.find_all("th")][1:]
        body_rows = table.find("tbody").find_all("tr") if table.find("tbody") else []
    else:  # some tables put headers in the first row
        trs = table.find_all("tr")
        columns = [th.get_text(" ", strip=True) for th in trs[0].find_all("th")][1:] if trs else []
        body_rows = trs[1:]
    rows: dict[str, list[float | None]] = {}
    for tr in body_rows:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        # First text node only: Screener appends "+" buttons and tooltips to some labels
        label = _clean_label(next(iter(tds[0].stripped_strings), ""))
        if not label or label.lower().startswith("raw pdf"):
            continue
        rows[label] = [parse_number(td.get_text(" ", strip=True)) for td in tds[1:]]
    return {"columns": columns, "rows": rows}


def parse_company_page(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, Any] = {"source": "screener.in"}

    h1 = soup.find("h1")
    out["name"] = h1.get_text(" ", strip=True) if h1 else None
    info = soup.find(id="company-info")
    out["warehouse_id"] = info.get("data-warehouse-id") if info else None
    out["consolidated"] = (info.get("data-consolidated") == "true") if info else None
    m = re.search(r"/api/company/(\d+)/add/", html)
    out["company_id"] = m.group(1) if m else None

    top = soup.find(id="top")
    img = top.find("img") if top else None
    out["logo_url"] = img.get("src") if img and img.get("src", "").startswith("http") else None
    out["website"] = None
    links: dict[str, str] = {}
    if top:
        for a in top.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if "bseindia.com" in href:
                links["bse"] = href
                code = re.search(r"BSE:\s*(\d+)", text)
                if code:
                    out["bse_code"] = code.group(1)
            elif "nseindia.com" in href:
                links["nse"] = href
                code = re.search(r"NSE:\s*([A-Z0-9&-]+)", text)
                if code:
                    out["nse_symbol"] = code.group(1)
            elif href.startswith("http") and "screener" not in href and out["website"] is None:
                out["website"] = href
    out["links"] = links

    about = soup.select_one(".company-profile .about")
    out["about"] = about.get_text(" ", strip=True) if about else None

    ratios: dict[str, Any] = {}
    ul = soup.find(id="top-ratios")
    if ul:
        for li in ul.find_all("li"):
            name = li.find(class_="name")
            val = li.find(class_="value")
            if not name or not val:
                continue
            nums = [parse_number(s.get_text()) for s in val.find_all(class_="number")]
            ratios[_clean_label(name.get_text())] = nums[0] if len(nums) == 1 else nums
    out["top_ratios"] = ratios

    def section_tables(sid: str):
        sec = soup.find("section", id=sid)
        return sec.find_all("table") if sec else []

    tables: dict[str, Any] = {}
    for key, sid in [
        ("quarters", "quarters"),
        ("profit_loss", "profit-loss"),
        ("balance_sheet", "balance-sheet"),
        ("cash_flow", "cash-flow"),
        ("ratios", "ratios"),
    ]:
        tabs = section_tables(sid)
        tables[key] = _parse_table(tabs[0]) if tabs else {"columns": [], "rows": {}}
    # Compounded growth tables under P&L (10Y / 5Y / 3Y / TTM)
    growth: dict[str, dict[str, float | None]] = {}
    for t in section_tables("profit-loss")[1:]:
        head = t.find("th")
        title = head.get_text(" ", strip=True) if head else None
        if not title:
            continue
        vals = {}
        for tr in t.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) == 2:
                vals[tds[0].get_text(" ", strip=True).rstrip(":")] = parse_number(tds[1].get_text())
        growth[title] = vals
    tables["growth"] = growth
    shp = soup.find(id="quarterly-shp")
    tables["shareholding"] = _parse_table(shp.find("table")) if shp else {"columns": [], "rows": {}}
    out["tables"] = tables

    analysis = soup.find("section", id="analysis")
    out["pros"] = [li.get_text(" ", strip=True) for li in analysis.select(".pros li")] if analysis else []
    out["cons"] = [li.get_text(" ", strip=True) for li in analysis.select(".cons li")] if analysis else []

    peers = soup.find("section", id="peers")
    out["classification"] = (
        {a.get("title"): a.get_text(" ", strip=True) for a in peers.select("p.sub a[title]")} if peers else {}
    )
    bench = peers.find(id="benchmarks") if peers else None
    out["indices"] = [a.get_text(" ", strip=True) for a in bench.find_all("a")] if bench else []

    out["documents"] = _parse_documents(soup)
    return out


def _parse_documents(soup) -> dict[str, list[dict]]:
    docs: dict[str, list[dict]] = {"announcements": [], "annual_reports": [], "credit_ratings": [], "concalls": []}
    sec = soup.find("section", id="documents")
    if not sec:
        return docs
    ann = sec.find(id="company-announcements-tab")
    if ann:
        for a in ann.select("ul.list-links a[href]"):
            meta = a.find("div")
            t = a.find("time")
            title = a.get_text(" ", strip=True)
            summary = meta.get_text(" ", strip=True) if meta else ""
            if summary and title.endswith(summary):
                title = title[: -len(summary)].strip()
            docs["announcements"].append(
                {
                    "title": title,
                    "url": a["href"],
                    "date": t.get("datetime", "")[:10] if t else None,
                    "summary": summary.split(" - ", 1)[-1] if summary else "",
                }
            )
    ar = sec.select_one(".annual-reports")
    if ar:
        for a in ar.select("a[href]"):
            title = a.get_text(" ", strip=True)
            year = re.search(r"(19|20)\d{2}", title)
            docs["annual_reports"].append(
                {"title": title, "url": a["href"], "year": int(year.group(0)) if year else None}
            )
    cr = sec.select_one(".credit-ratings")
    if cr:
        for a in cr.select("a[href]"):
            docs["credit_ratings"].append({"title": a.get_text(" ", strip=True), "url": a["href"]})
    cc = sec.select_one(".concalls")
    if cc:
        for li in cc.select("ul.list-links > li"):
            period_el = li.find("div")
            item = {"period": period_el.get_text(" ", strip=True) if period_el else None}
            for a in li.find_all("a", href=True):
                label = a.get_text(" ", strip=True).lower()
                if "transcript" in label:
                    item["transcript"] = a["href"]
                elif label == "ppt":
                    item["ppt"] = a["href"]
                elif label == "rec":
                    item["recording"] = a["href"]
                elif label == "notes":
                    item["notes"] = a["href"]
            docs["concalls"].append(item)
    return docs


def parse_peers(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []
    trs = table.find_all("tr")
    if not trs:
        return []
    headers = [re.sub(r"\s+", " ", th.get_text(" ", strip=True)) for th in trs[0].find_all("th")]
    peers = []
    for tr in trs[1:]:
        tds = tr.find_all("td")
        if len(tds) != len(headers):
            continue
        row: dict[str, Any] = {}
        for h, td in zip(headers, tds, strict=False):
            a = td.find("a")
            if h == "Company":
                row["Company"] = td.get_text(" ", strip=True)
                row["url"] = a["href"] if a else None
            elif h != "S.No.":
                row[h] = parse_number(td.get_text(" ", strip=True))
        if row.get("Company"):
            peers.append(row)
    return peers


def parse_chart(data: dict) -> dict[str, list]:
    """Screener chart API -> {'dates': [...], 'close': [...], 'volume': [...]}."""
    out: dict[str, list] = {"dates": [], "close": [], "volume": []}
    vols: dict[str, float] = {}
    for ds in data.get("datasets", []):
        if ds.get("metric") == "Price":
            for d, v in ds["values"]:
                out["dates"].append(d)
                out["close"].append(float(v))
        elif ds.get("metric") == "Volume":
            for item in ds["values"]:
                vols[item[0]] = float(item[1])
    out["volume"] = [vols.get(d) for d in out["dates"]]
    return out


class ScreenerClient:
    def __init__(self, http: Http):
        self.http = http

    def search(self, query: str) -> list[dict]:
        from urllib.parse import quote

        return self.http.get_json(f"{BASE}/api/company/search/?q={quote(query)}")

    def company(self, slug: str, consolidated: bool = True) -> dict[str, Any]:
        """Fetch a company page. Falls back to standalone when consolidated is empty."""
        urls = [f"{BASE}/company/{slug}/consolidated/", f"{BASE}/company/{slug}/"]
        if not consolidated:
            urls = urls[::-1]
        last: Exception | None = None
        for url in urls:
            try:
                page = parse_company_page(self.http.get(url))
            except DataUnavailable as e:
                last = e
                continue
            if page["tables"]["profit_loss"]["rows"]:
                page["url"] = url
                return page
        raise DataUnavailable(f"Screener has no financials for {slug}: {last or 'empty tables'}")

    def peers(self, warehouse_id: str) -> list[dict]:
        return parse_peers(self.http.get(f"{BASE}/api/company/{warehouse_id}/peers/"))

    def price_history(self, company_id: str, days: int = 3650, consolidated: bool = True) -> dict:
        url = (
            f"{BASE}/api/company/{company_id}/chart/?q=Price-Volume&days={days}"
            f"&consolidated={'true' if consolidated else ''}"
        )
        return parse_chart(self.http.get_json(url))
