"""Company news from the Google News RSS feed (no API key needed)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from aladeen.dataflows.http import Http


def parse_rss(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src_el = it.find("source")
        try:
            dt = parsedate_to_datetime(pub) if pub else None
        except (TypeError, ValueError):
            dt = None
        source = src_el.text.strip() if src_el is not None and src_el.text else ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        items.append(
            {"title": title, "url": link, "date": dt.date().isoformat() if dt else None, "source": source}
        )
    return items


_SUFFIX = re.compile(r"\s+(ltd\.?|limited|pvt\.?|private)$", re.I)


def short_name(company: str) -> str:
    """'Kotak Mahindra Bank Ltd' -> 'Kotak Mahindra Bank' (news rarely carries the legal suffix)."""
    name = company.strip()
    while _SUFFIX.search(name):
        name = _SUFFIX.sub("", name).strip()
    return name


def queries(company: str, symbol: str) -> list[str]:
    n = short_name(company)
    return [f'"{n}"', f'"{n}" results OR quarter OR RBI OR rating', f'"{symbol}" share price']


def company_news(http: Http, company: str, symbol: str, as_of: date, lookback_days: int = 90,
                 limit: int = 40) -> list[dict]:
    items: list[dict] = []
    for q in queries(company, symbol):
        url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            items += parse_rss(http.get(url))
        except Exception:  # noqa: BLE001 - one failed query should not lose the others
            continue
    lo = as_of - timedelta(days=lookback_days)
    keep = []
    seen = set()
    for it in items:
        if not it["date"]:
            continue
        d = datetime.fromisoformat(it["date"]).date()
        if lo <= d <= as_of and it["title"].lower() not in seen:
            seen.add(it["title"].lower())
            keep.append(it)
    keep.sort(key=lambda x: x["date"], reverse=True)
    return keep[:limit]
