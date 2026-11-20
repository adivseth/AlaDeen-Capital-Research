"""Assemble the verified fact pack that every agent works from.

The fact pack is collected once, by code, before any LLM is called. Agents read
markdown renderings of it; they never fetch numbers themselves. That keeps every
figure in the final report traceable to a source.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from aladeen.dataflows import authority, backups, yahoo
from aladeen.dataflows import documents as docs_mod
from aladeen.dataflows import logo as logo_mod
from aladeen.dataflows import news as news_mod
from aladeen.dataflows.http import DataUnavailable, Http
from aladeen.dataflows.screener import ScreenerClient
from aladeen.dataflows.symbols import Symbol, normalize


@dataclass
class FactPack:
    ticker: str
    yahoo_symbol: str
    exchange: str
    as_of: str
    benchmark: str
    company: dict[str, Any] = field(default_factory=dict)
    screener: dict[str, Any] = field(default_factory=dict)
    peers: list[dict] = field(default_factory=list)
    yahoo: dict[str, Any] = field(default_factory=dict)
    prices: pd.DataFrame = field(default_factory=pd.DataFrame)
    benchmark_prices: pd.DataFrame = field(default_factory=pd.DataFrame)
    news: list[dict] = field(default_factory=list)
    web: list[dict] = field(default_factory=list)  # Exa web research: analysts, sector, history
    documents: list[dict] = field(default_factory=list)  # includes "text"
    warnings: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    synthetic: bool = False

    captured_on: str | None = None
    fact_resolutions: list[dict] = field(default_factory=list)
    # The firm owner's rulings on annual facts the filings could not settle, keyed by authority.owner_key.
    owner_facts: dict[str, dict] = field(default_factory=dict)

    def resolve_facts(self) -> None:
        self.fact_resolutions = authority.apply_owner_facts(authority.resolve(self), self.owner_facts)

    # ------------------------------------------------------------ helpers
    @property
    def name(self) -> str:
        return self.company.get("name") or self.ticker

    def table(self, key: str) -> dict:
        table = self.screener.get("tables", {}).get(key, {"columns": [], "rows": {}})
        if key != "profit_loss" or not self.fact_resolutions:
            return table
        rows = {name: list(values) for name, values in table["rows"].items()}
        for fact in self.fact_resolutions:
            rows[fact["row"]][table["columns"].index(fact["period"])] = fact["value"]
        return {**table, "rows": rows}

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)

    # ------------------------------------------------------------ serialisation
    def to_json(self) -> str:
        d = asdict(self)
        d["prices"] = _df_to_records(self.prices)
        d["benchmark_prices"] = _df_to_records(self.benchmark_prices)
        return json.dumps(d, default=str)

    @classmethod
    def from_json(cls, text: str) -> FactPack:
        d = json.loads(text)
        d["prices"] = _records_to_df(d.get("prices"))
        d["benchmark_prices"] = _records_to_df(d.get("benchmark_prices"))
        fp = cls(**d)
        fp.resolve_facts()
        return fp

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> FactPack:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


def _df_to_records(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    out = {"index": [d.strftime("%Y-%m-%d") for d in df.index]}
    for c in df.columns:
        out[c] = [None if pd.isna(v) else float(v) for v in df[c]]
    return out


def _records_to_df(rec: dict | None) -> pd.DataFrame:
    if not rec:
        return pd.DataFrame()
    rec = dict(rec)
    idx = pd.to_datetime(rec.pop("index"))
    return pd.DataFrame(rec, index=idx)


def build_factpack(ticker: str, as_of: date, cfg: dict, *, http: Http | None = None,
                   progress=lambda msg: None) -> FactPack:
    sym: Symbol = normalize(ticker)
    snapshots = Path(cfg["home_dir"]) / "snapshots" / sym.yahoo if cfg.get("home_dir") else None
    if as_of < date.today() and snapshots is not None:
        candidates = sorted((p for p in snapshots.glob("*.json") if p.name[:10] <= as_of.isoformat()), reverse=True)
        if not candidates:
            raise DataUnavailable(f"No archived evidence captured by {as_of} for {sym.yahoo}")
        frozen = FactPack.load(candidates[0])
        frozen.warn(f"Historical replay uses the complete snapshot captured on {candidates[0].name[:10]}.")
        frozen.as_of = as_of.isoformat()
        return frozen
    http = http or Http(cache_dir=cfg["cache_dir"], timeout=cfg["http_timeout"])
    fp = FactPack(
        captured_on=date.today().isoformat(), ticker=sym.base, yahoo_symbol=sym.yahoo, exchange=sym.exchange, as_of=as_of.isoformat(),
        benchmark=cfg.get("benchmark") if sym.exchange == "NSE" else sym.benchmark,
    )
    if (date.today() - as_of).days > 7:
        fp.warn(
            "Analysis date is in the past: prices are point-in-time, but Screener fundamentals, "
            "documents and peer data are as fetched today and may include later information."
        )

    # 1. Screener: statements, shareholding, peers, document links
    progress("Screener.in: financial statements, shareholding, documents")
    sc = ScreenerClient(http)
    try:
        fp.screener = cfg.get("review_screener") or sc.company(sym.screener_slug)
        fp.sources.append({"name": "Screener.in company page", "url": fp.screener.get("url")})
        if not fp.screener.get("consolidated"):
            fp.warn("Screener shows standalone figures (no consolidated statements available).")
    except DataUnavailable as e:
        fp.warn(f"Screener unavailable: {e}")
    if fp.screener.get("warehouse_id"):
        try:
            fp.peers = sc.peers(fp.screener["warehouse_id"])
        except DataUnavailable as e:
            fp.warn(f"Peer table unavailable: {e}")

    # 2. Yahoo: prices (point-in-time) and snapshot
    progress("Yahoo Finance: 10-year prices and snapshot")
    try:
        fp.prices = yahoo.ohlcv(sym.yahoo, as_of, cfg["history_years"])
        fp.sources.append({"name": f"Yahoo Finance daily prices ({sym.yahoo})",
                           "url": f"https://finance.yahoo.com/quote/{sym.yahoo}/history"})
    except DataUnavailable as e:
        fp.warn(f"Yahoo prices unavailable ({e}).")
        av_key = backups.key(cfg, "alphavantage")
        if av_key:
            progress("Alpha Vantage: backup price history")
            try:
                fp.prices, note = backups.alpha_vantage_daily(sym.base, as_of, av_key)
                fp.sources.append({"name": f"{note} daily prices", "url": "https://www.alphavantage.co/"})
                fp.warn(f"Prices from the backup source: {note}.")
            except (DataUnavailable, ValueError, OSError) as e2:
                fp.warn(f"Alpha Vantage prices unavailable: {e2}")
        cid = fp.screener.get("company_id")
        if cid and (fp.prices is None or fp.prices.empty):
            try:
                ch = sc.price_history(cid, days=int(365.25 * cfg["history_years"]))
                df = pd.DataFrame({"close": ch["close"], "volume": ch["volume"]},
                                  index=pd.to_datetime(ch["dates"]))
                fp.prices = df[df.index.date <= as_of]
                fp.warn("Price history is Screener close/volume only (lower frequency, no OHLC).")
            except DataUnavailable as e2:
                fp.warn(f"Screener price history unavailable: {e2}")
    try:
        fp.benchmark_prices = yahoo.ohlcv(fp.benchmark, as_of, cfg["history_years"])
    except DataUnavailable as e:
        fp.warn(f"Benchmark {fp.benchmark} prices unavailable: {e}")
    try:
        fp.yahoo = yahoo.snapshot(sym.yahoo)
    except Exception as e:  # noqa: BLE001 - yfinance can raise anything
        fp.warn(f"Yahoo snapshot unavailable: {e}")

    # 3. Company identity and logo
    sc_ = fp.screener
    info = fp.yahoo.get("info", {})
    fp.company = {
        "name": sc_.get("name") or info.get("longName") or sym.base,
        "about": sc_.get("about") or info.get("longBusinessSummary"),
        "website": sc_.get("website") or info.get("website"),
        "classification": sc_.get("classification") or {"Sector": info.get("sector"),
                                                         "Industry": info.get("industry")},
        "indices": sc_.get("indices", []),
        "bse_code": sc_.get("bse_code"),
        "nse_symbol": sc_.get("nse_symbol") or (sym.base if sym.exchange == "NSE" else None),
        "pros": sc_.get("pros", []),
        "cons": sc_.get("cons", []),
    }
    fp.company["logo"] = logo_mod.logo_data_uri(http, sc_.get("logo_url")) or logo_mod.monogram_svg(
        fp.company["name"])

    # 4. News
    progress("News: Google News RSS")
    try:
        fp.news = news_mod.company_news(http, fp.company["name"], sym.base, as_of,
                                        cfg["news_lookback_days"])
        fp.sources.append({"name": "Google News RSS search", "url": "https://news.google.com"})
    except Exception as e:  # noqa: BLE001
        fp.warn(f"News feed unavailable: {e}")

    # 4b. Web research (optional, needs an Exa key): analyst coverage, sector outlook, company history
    if backups.key(cfg, "exa"):
        progress("Web research (Exa): analyst coverage, sector outlook, company history")
        fp.web = backups.web_research(fp.company["name"], cfg)
        fp.sources += [{"name": f"{w['title']} ({w['date'] or 'undated'})", "url": w["url"]} for w in fp.web]
        if not fp.web:
            fp.warn("Web research returned nothing; analyst coverage and sector outlook rely on other material.")

    # 5. Annual reports and concall transcripts
    if cfg.get("fetch_documents", True) and sc_.get("documents"):
        progress("Filings: annual reports and concall transcripts")
        docs = docs_mod.collect(http, sc_["documents"], cfg["max_annual_reports"],
                                cfg["max_concall_transcripts"], cfg["document_mode"],
                                cfg["document_char_budget"],
                                fallback=lambda url: backups.document_text(url, cfg),
                                max_presentations=cfg.get("max_presentations", 2))
        for d in docs:
            rec = d.as_dict()
            rec["filed_on"] = next((a.get("date") for a in sc_["documents"].get("announcements", [])
                                         if a.get("url") == d.url and a.get("date")), None)
            rec["text"] = d.text
            fp.documents.append(rec)
            if d.error:
                fp.warn(f"Could not read {d.title}: {d.error}")
            else:
                fp.sources.append({"name": d.title, "url": d.url})
    if sc_.get("documents"):
        gap = docs_mod.latest_call_gap(sc_["documents"])
        if gap:
            fp.warn(gap)
        anns = sc_["documents"].get("announcements", [])
        if anns and cfg.get("max_announcements_read", 5):
            progress("Exchange announcements: reading the newest filings")
            read = docs_mod.read_announcements(http, anns, cfg.get("max_announcements_read", 5),
                                               cfg.get("announcement_chars", 3000),
                                               fallback=lambda url: backups.document_text(url, cfg))
            if read < min(len(anns), cfg.get("max_announcements_read", 5)):
                fp.warn(f"Only {read} of the newest {min(len(anns), cfg.get('max_announcements_read', 5))} "
                        "exchange announcements could be read in full; the rest are titles only.")
    splits = fp.yahoo.get("splits") or {}
    recent = {d: r for d, r in splits.items() if (as_of - date.fromisoformat(d)).days <= 5 * 365}
    if recent:
        fp.warn("Corporate action: share split(s) " + ", ".join(f"{d} ({r:g}:1)" for d, r in recent.items())
                + ". Per-share history (EPS, book value, prices) must be on the post-split basis.")
    if not fp.yahoo.get("info", {}).get("targetMeanPrice") and not fp.web:
        fp.warn("No broker consensus target in the sources.")
    fp.resolve_facts()
    if snapshots is not None and not fp.prices.empty and fp.table("profit_loss").get("rows"):
        snapshots.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S%f")
        target = snapshots / f"{stamp}-{uuid4().hex}.json"
        tmp = target.with_suffix(".tmp")
        fp.save(tmp)
        tmp.replace(target)
    return fp
