"""Resolve annual statement cells using scope-matched rows from exchange filings."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Accept only rows whose full label, units and column dates can be identified.
LABELS = {
    "revenue from operations": "Revenue",
    "profit attributable to owners of the company": "PAT",
    "profit attributable to owners of the parent": "PAT",
    "profit attributable to equity shareholders of the company": "PAT",
    "profit for the year": "Standalone PAT",
    "total equity dividend attributable to the financial year": "Dividend",
    "dividend payout ratio": "Dividend Payout %",
}
DATE = re.compile(r"(?:31(?:st)?\s+mar(?:ch)?[,]?\s+|mar(?:ch)?\s+31[,]?\s+)(20\d{2})", re.I)
AMOUNT = r"(?:-?\d[\d,]*(?:\.\d+)?|\(\d[\d,]*(?:\.\d+)?\))"
UNIT = re.compile(r"(?:₹|inr|rupees|rs\.?)\s*(?:in\s+)?(crores?|lakhs?|millions?)\b", re.I)


def filed_rows(pages):
    rows = []
    for page, text in enumerate(pages, 1):
        # A narrative percentage is a lead to check, never an accepted calculation.
        for line in text.splitlines():
            if re.search(r"dividend pay[ -]?out", line, re.I) and re.search(r"\d(?:\.\d+)?\s*%", line):
                rows.append(dict(metric="Payout mention", line=line.strip(), page=page))
        titles = set(
            re.findall(
                r"\b(consolidated|standalone)\s+(?:statement of profit and loss|financial ratios|financial statements)\b",
                text.lower(),
            )
        )
        if len(titles) != 1:
            continue
        scope = titles.pop()
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for label, metric in LABELS.items():
                match = re.fullmatch(r"(?:[ivx]+\.?\s+)?" + label + r"\s+(.+)", line.strip(), re.I)
                if not match:
                    continue
                if (
                    metric in ("PAT", "Standalone PAT", "Revenue")
                    and "statement of profit and loss" not in text.lower()
                ):
                    continue
                header = "\n".join(lines[:i])
                if re.search(r"quarter ended|three months ended|six months ended|nine months ended", header, re.I):
                    continue
                years = DATE.findall(header)
                if not years or len(years) != len(set(years)) or "year ended" not in header.lower():
                    continue
                units = {v.lower().rstrip("s") for v in UNIT.findall(header)}
                if metric == "Standalone PAT" and scope != "standalone":
                    continue
                percent = metric == "Dividend Payout %"
                cells = match[1].split()
                if len(cells) == len(years) + 1 and re.search(r"\bnote\b", header, re.I) and cells[0].isdigit():
                    cells = cells[1:]
                if len(cells) != len(years) or not all(
                    re.fullmatch(AMOUNT + ("%" if percent else ""), c) for c in cells
                ):
                    continue
                if not percent and len(units) != 1:
                    continue
                scale = 1 if percent else {"crore": 1, "lakh": 0.01, "million": 0.1}[next(iter(units))]
                for year, cell in zip(years, cells, strict=True):
                    value = float(cell.strip("()%").replace(",", "")) * (-1 if cell.startswith("(") else 1)
                    rows.append(
                        dict(
                            metric="PAT" if metric == "Standalone PAT" else metric,
                            scope=scope,
                            period=f"Mar {year}",
                            value=value * scale,
                            page=page,
                            line=line.strip(),
                            unit="%" if percent else "INR crore",
                            header=header[-750:],
                        )
                    )
    return rows


def resolve(fp):
    table = fp.screener.get("tables", {}).get("profit_loss", {})
    scope = "consolidated" if fp.screener.get("consolidated") else "standalone"
    # IR copies qualify when both company profiles independently identify the same official domain.
    domains = {"bseindia.com", "nseindia.com"}
    issuer = (urlparse(fp.screener.get("website") or "").hostname or "").removeprefix("www.")
    other_site = (urlparse(fp.yahoo.get("info", {}).get("website") or "").hostname or "").removeprefix("www.")
    if issuer and issuer == other_site:
        domains.add(issuer)
    evidence = {}
    payout_mentions = {}
    for doc in fp.documents:
        url = urlparse(doc.get("url") or "")
        if (
            doc.get("kind") != "annual_report"
            or doc.get("error")
            or url.scheme != "https"
            or not any(
                url.hostname == h or (url.hostname or "").endswith("." + h) for h in domains
            )
        ):
            continue
        # Undated filings are admissible only from a point-in-time capture.
        if (doc.get("filed_on") or fp.captured_on or fp.as_of) > fp.as_of:
            continue
        for row in doc.get("filed_rows", []):
            if row["metric"] == "Payout mention":
                year = str(doc.get("period") or "")
                if year.isdigit() and not re.search(r"policy|target|face value|at least|minimum", row["line"], re.I):
                    payout_mentions.setdefault(f"Mar {year}", []).append(
                        {**row, "url": doc["url"], "title": doc["title"]}
                    )
                continue
            if row["scope"] == scope:
                key = row["metric"], row["period"]
                evidence.setdefault(key, []).append(
                    {
                        **row,
                        "url": doc["url"],
                        "title": doc["title"],
                        "edition": str(doc.get("period") or ""),
                        "filed_on": doc.get("filed_on") or "",
                    }
                )
    records = []
    for i, period in enumerate(table.get("columns", [])):
        if not re.fullmatch(r"Mar 20\d\d", period):
            continue
        end = period[-4:] + "-03-31"
        if end > fp.as_of:
            continue
        for metric, labels, yahoo in (
            ("Revenue", ("Sales", "Revenue"), "Total Revenue"),
            ("PAT", ("Net Profit",), "Net Income"),
            ("Dividend Payout %", ("Dividend Payout %",), None),
        ):
            row = next((r for r in labels if r in table["rows"]), None)
            if not row or i >= len(table["rows"][row]):
                continue
            vendor = table["rows"][row][i]
            other = fp.yahoo.get("annual_income", {}).get(yahoo, {}).get(end)
            feeds = {"Screener": vendor}
            if other is not None:
                feeds["Yahoo"] = other / 1e7
            sources = list(evidence.get((metric, period), []))
            if metric == "Dividend Payout %":
                for div in evidence.get(("Dividend", period), []):
                    for pat in evidence.get(("PAT", period), []):
                        if div["url"] == pat["url"] and pat["value"] > 0:
                            sources.append(
                                {
                                    **div,
                                    "value": 100 * div["value"] / pat["value"],
                                    "unit": "%",
                                    "line": f"{div['line']} / {pat['line']} (p.{pat['page']}) × 100",
                                }
                            )
            if sources:
                edition = max((s["edition"], s["filed_on"]) for s in sources)
                sources = [s for s in sources if (s["edition"], s["filed_on"]) == edition]
            values = {round(s["value"], 6) for s in sources}
            conflict = (
                vendor is not None and other is not None and abs(vendor - other / 1e7) > max(5, abs(vendor) * 0.03)
            )
            mentions = payout_mentions.get(period, []) if metric == "Dividend Payout %" else []
            disputed_mentions = [
                m
                for m in mentions
                if vendor is not None
                and any(abs(float(v) - vendor) > 0.5 for v in re.findall(r"(\d+(?:\.\d+)?)\s*%", m["line"]))
            ]
            if not sources and not conflict and not disputed_mentions:
                continue
            value = sources[0]["value"] if len(values) == 1 else None
            records.append(
                dict(
                    metric=metric,
                    row=row,
                    period=period,
                    scope=scope,
                    value=value,
                    unit="%" if not yahoo else "INR crore",
                    feeds=feeds,
                    evidence=sources or disputed_mentions,
                    status="verified" if value is not None else "unresolved",
                )
            )
    return records


def summary(record):
    source = record["evidence"]
    detail = (
        f"{record['value']:g} {record['unit']} ({source[0]['url']}, PDF p.{source[0]['page']})"
        if record["status"] == "verified"
        else "unresolved; a scope-matched filed figure is required"
    )
    return f"{record['period']} {record['scope']} {record['metric']}: {detail}"
