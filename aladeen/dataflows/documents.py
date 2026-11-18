"""Annual reports and concall transcripts: download, extract text, select what to read.

``focused`` mode keeps the sections of an annual report that matter most to an
equity analyst (MD&A, auditor's report, related parties, contingent liabilities,
segments, borrowings, shareholding/pledge, remuneration) plus the full text of
each concall transcript, within a character budget. ``full`` mode keeps every page;
the filings analyst then reads the document in chunks.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from aladeen.dataflows.http import DataUnavailable, Http

ANNUAL_REPORT_KEYWORDS = {
    "management discussion": 5, "md&a": 5, "key audit matter": 5, "independent auditor": 4,
    "emphasis of matter": 6, "qualified opinion": 6, "related party": 5, "contingent liabilit": 5,
    "segment": 3, "borrowings": 3, "pledge": 5, "remuneration": 3, "outlook": 3, "capex": 3,
    "capital expenditure": 3, "order book": 4, "exceptional item": 5, "going concern": 6,
    "guarantee": 3, "subsidiar": 2, "risk management": 3, "dividend distribution": 2,
    "business responsibility": 2, "brsr": 2, "scope 1": 2, "greenhouse": 2,
}


@dataclass
class Document:
    kind: str  # annual_report | concall
    title: str
    url: str
    period: str | None = None
    pages: int = 0
    text: str = ""
    error: str | None = None
    selected_pages: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "url": self.url, "period": self.period,
            "pages": self.pages, "chars": len(self.text), "error": self.error,
            "selected_pages": self.selected_pages[:60],
        }


def extract_pages(pdf_bytes: bytes) -> list[str]:
    from pypdf import PdfReader

    if not pdf_bytes.startswith(b"%PDF"):
        raise DataUnavailable("Response is not a PDF (the host may block automated downloads)")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for p in reader.pages:
        try:
            pages.append(re.sub(r"[ \t]+", " ", p.extract_text() or ""))
        except Exception:  # damaged page
            pages.append("")
    return pages


def score_page(text: str) -> int:
    low = text.lower()
    return sum(w for k, w in ANNUAL_REPORT_KEYWORDS.items() if k in low)


def select_pages(pages: list[str], budget: int) -> tuple[str, list[int]]:
    ranked = sorted(range(len(pages)), key=lambda i: score_page(pages[i]), reverse=True)
    chosen: list[int] = []
    used = 0
    for i in ranked:
        if score_page(pages[i]) == 0:
            break
        if used + len(pages[i]) > budget:
            continue
        chosen.append(i)
        used += len(pages[i])
    chosen.sort()
    text = "\n".join(f"[page {i + 1}]\n{pages[i]}" for i in chosen)
    return text, [i + 1 for i in chosen]


def load_document(http: Http, kind: str, title: str, url: str, period: str | None,
                  mode: str, budget: int, fallback=None) -> Document:
    """``fallback(url) -> (text, source)`` is tried when the direct download fails (e.g. BSE blocks it)."""
    doc = Document(kind=kind, title=title, url=url, period=period)
    try:
        pages = extract_pages(http.get(url, binary=True))
    except Exception as e:
        if fallback is None:
            doc.error = str(e)
            return doc
        try:
            text, source = fallback(url)
        except Exception as e2:  # noqa: BLE001
            doc.error = f"{e}; backup: {e2}"
            return doc
        # shortcut: backup text has no page breaks, so 4,000-character chunks stand in for pages
        pages = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        doc.title = f"{title} (read via {source})"
    doc.pages = len(pages)
    if kind == "annual_report" and mode == "focused":
        doc.text, doc.selected_pages = select_pages(pages, budget)
    else:
        full = "\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages))
        doc.text = full if mode == "full" else full[:budget]
        doc.selected_pages = list(range(1, len(pages) + 1))
    return doc


def collect(http: Http, documents: dict, max_annual: int, max_concalls: int, mode: str,
            budget: int, fallback=None) -> list[Document]:
    out: list[Document] = []
    ars = sorted(documents.get("annual_reports", []), key=lambda d: d.get("year") or 0, reverse=True)
    for ar in ars[:max_annual]:
        out.append(load_document(http, "annual_report", ar["title"], ar["url"],
                                 str(ar.get("year")), mode, budget, fallback))
    calls = [c for c in documents.get("concalls", []) if c.get("transcript")]
    for c in calls[:max_concalls]:
        out.append(load_document(http, "concall", f"Concall transcript {c.get('period')}",
                                 c["transcript"], c.get("period"), mode, budget, fallback))
    return out
