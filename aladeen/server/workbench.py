"""Research follow-up tools using published runs and their frozen inputs."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from aladeen.dataflows import yahoo
from aladeen.dataflows.factpack import FactPack
from aladeen.dataflows.http import DataUnavailable, Http
from aladeen.dataflows.screener import ScreenerClient
from aladeen.dataflows.symbols import normalize
from aladeen.quant.engine import compute_quant, value_company

SIGNALS = {
    "Auditor change": r"auditor.{0,60}(resign|change)|resignation.{0,60}auditor",
    "Audit opinion": r"qualified opinion|adverse opinion|disclaimer of opinion",
    "Promoter pledge": r"pledge|encumbrance",
    "Related parties": r"related.party",
    "Results": r"financial results|quarterly results",
}


def filings(sc):
    items = sc.get("documents", {}).get("announcements", [])
    return {item["url"]: item for item in items if item.get("url")}


def report_changes(old, new):
    changes = []
    for group in ("quarters", "cash_flow", "profit_loss", "balance_sheet", "ratios"):
        before = old.get("tables", {}).get(group, {})
        after = new.get("tables", {}).get(group, {})
        for metric, values in after.get("rows", {}).items():
            prior = dict(zip(before.get("columns", []), before.get("rows", {}).get(metric, []), strict=False))
            for period, value in zip(after.get("columns", []), values, strict=False):
                if value is not None and value != prior.get(period):
                    changes.append(
                        dict(statement=group, metric=metric, period=period, previous=prior.get(period), actual=value)
                    )
    return changes


def portfolio_series(positions, quotes):
    # INR allocations are committed at the common inception close. All series share trading dates.
    frame = pd.concat(quotes, axis=1, join="inner").dropna().sort_index()
    if frame.empty or (frame <= 0).any().any():
        raise ValueError("No common positive adjusted closes for the selected period")
    relatives = frame / frame.iloc[0]
    cost = sum(p["amount"] for p in positions)
    nav = pd.Series(0.0, index=frame.index)
    rows = []
    for p in positions:
        holding = relatives[p["ticker"]] * p["amount"]
        nav += holding
        gain = float(holding.iloc[-1] - p["amount"])
        rows.append(
            {
                **p,
                "value": float(holding.iloc[-1]),
                "gain": gain,
                "contribution": gain / cost,
                "benchmark_return": float(relatives[p["benchmark"]].iloc[-1] - 1),
            }
        )
    sectors = {}
    for r in rows:
        r["weight"] = r["value"] / float(nav.iloc[-1])
        sectors[r["sector"]] = sectors.get(r["sector"], 0) + r["weight"]
    return dict(
        sectors=sectors,
        rows=rows,
        total_return=float(nav.iloc[-1] / cost - 1),
        drawdown=float((nav / nav.cummax() - 1).min()),
        start=str(nav.index[0].date()),
        end=str(nav.index[-1].date()),
    )


def router(mgr):
    api = APIRouter(prefix="/api/workbench")
    db = mgr.store.path

    def connect():
        conn = sqlite3.connect(db, timeout=10)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pins(run TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS snapshots(run TEXT REFERENCES runs(id) ON DELETE CASCADE, seen TEXT, data TEXT, PRIMARY KEY(run,seen));
            CREATE TABLE IF NOT EXISTS forecasts(run TEXT REFERENCES runs(id) ON DELETE CASCADE, period TEXT, metric TEXT, value REAL, seen TEXT,
                                                PRIMARY KEY(run, period, metric));
            CREATE TABLE IF NOT EXISTS positions(run TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE, amount REAL, benchmark TEXT);
        """)

    def record(run):
        rec = mgr.store.get(run)
        if not rec or rec["status"] != "done":
            raise HTTPException(404, "Published research unavailable")
        return rec

    def pack(rec):
        return FactPack.load(Path(rec["out_dir"]) / "factpack.json")

    def research(rec):
        return json.loads((Path(rec["out_dir"]) / "research.json").read_text(encoding="utf8"))

    @api.get("/pins")
    def pins():
        with connect() as c:
            return [r[0] for r in c.execute("SELECT run FROM pins") if mgr.store.get(r[0])]

    @api.put("/{run}/pin")
    def pin(run: str, enabled: bool = True):
        record(run)
        with connect() as c:
            c.execute("INSERT OR IGNORE INTO pins VALUES (?)" if enabled else "DELETE FROM pins WHERE run=?", (run,))
        return {"pinned": enabled}

    @api.post("/{run}/refresh")
    def refresh(run: str):
        rec = record(run)
        fp = pack(rec)
        try:
            sc = (
                fp.screener if fp.synthetic else ScreenerClient(Http(timeout=15)).company(normalize(rec["ticker"]).base)
            )
        except DataUnavailable as exc:
            raise HTTPException(502, str(exc)) from exc
        if not sc.get("tables", {}).get("quarters", {}).get("rows"):
            raise HTTPException(502, "Quarterly statement missing from refresh")
        if fp.screener.get("consolidated") != sc.get("consolidated"):
            raise HTTPException(422, "Statement basis changed between standalone and consolidated accounts")
        seen = datetime.now().astimezone().isoformat()
        with connect() as c:
            c.execute("INSERT INTO snapshots VALUES (?,?,?)", (run, seen, json.dumps(sc)))
        return {"seen": seen}

    @api.put("/{run}/forecast")
    def forecast(run: str, period: str, metric: str, value: float = Query(ge=-1e15, le=1e15)):
        fp = pack(record(run))
        quarters = fp.table("quarters")
        try:
            quarter = datetime.strptime(period, "%b %Y")
        except ValueError as exc:
            raise HTTPException(400, "Use a quarter ending month and year, e.g. Mar 2027") from exc
        if quarter.month not in (3, 6, 9, 12) or metric not in quarters.get("rows", {}):
            raise HTTPException(400, "Choose a reported metric and a fiscal quarter end")
        period = quarter.strftime("%b %Y")
        if period in quarters.get("columns", []) or quarter.date().replace(day=1) < date.today().replace(day=1):
            raise HTTPException(400, "Choose a current or future unreported quarter")
        try:
            with connect() as c:
                c.execute(
                    "INSERT INTO forecasts VALUES (?,?,?,?,?)",
                    (run, period, metric, value, datetime.now().astimezone().isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "A forecast is already recorded for this period and metric") from exc
        return {"saved": True}

    @api.get("/{run}/evidence")
    def evidence(run: str, snapshot: str = "", compare: str = ""):
        rec = record(run)
        fp = pack(rec)
        baseline = research(rec)
        with connect() as c:
            dates = [r[0] for r in c.execute("SELECT seen FROM snapshots WHERE run=? ORDER BY seen DESC", (run,))]
            chosen = snapshot or (dates[0] if dates else "archive")
            row = c.execute("SELECT data FROM snapshots WHERE run=? AND seen=?", (run, chosen)).fetchone()
        if chosen != "archive" and not row:
            raise HTTPException(404, "Snapshot unavailable")
        sc = json.loads(row[0]) if row else fp.screener
        prior = pack(record(compare)) if compare else fp
        if prior.yahoo_symbol != fp.yahoo_symbol or (compare and prior.as_of > fp.as_of):
            raise HTTPException(400, "Choose an earlier report for the same listing")
        old = research(record(compare)) if compare else baseline
        current, previous = filings(sc), filings(prior.screener)
        if row:
            with connect() as c:
                history = c.execute(
                    "SELECT data FROM snapshots WHERE run=? AND seen<=? ORDER BY seen DESC", (run, chosen)
                )
                for (saved,) in history:
                    for url, item in filings(json.loads(saved)).items():
                        current.setdefault(url, item)
        events = []
        for url, item in current.items():
            words = f"{item.get('title', '')} {item.get('summary', '')}"
            tags = [name for name, regex in SIGNALS.items() if re.search(regex, words, re.I)]
            events.append({**item, "signals": tags, "new": url not in previous})
        changes = report_changes(prior.screener, sc)

        def series(source, table, *keys):
            t = source.get("tables", {}).get(table, {})
            values = next((t["rows"][k] for k in keys if k in t.get("rows", {})), [])
            return dict(zip(t.get("columns", []), values, strict=False))

        sales = series(sc, "profit_loss", "Sales", "Revenue")
        old_years = [
            p
            for p in series(prior.screener, "profit_loss", "Sales", "Revenue")
            if re.fullmatch(r"[A-Za-z]{3} [0-9]{4}", p)
        ]
        projections = (old["valuation"].get("dcf") or {}).get("projections", [])
        forecast_review = []
        if old_years:
            month, year = old_years[-1].split()
            for f in projections:
                period = f"{month} {int(year) + f['year']}"
                actual = sales.get(period)
                forecast_review.append(
                    dict(
                        period=period,
                        forecast=round(f["revenue"], 2),
                        actual=actual,
                        variance=round(actual - f["revenue"], 2) if actual is not None else None,
                    )
                )
        cash = series(sc, "cash_flow", "Cash from Operating Activity", "Cash from Operating Activities")
        profit = series(sc, "profit_loss", "Net Profit")
        cash_conversion = [
            dict(period=p, cash=c, profit=profit[p])
            for p, c in cash.items()
            if c is not None and profit.get(p) is not None
        ]
        with connect() as c:
            estimates = c.execute(
                "SELECT period,metric,value,seen FROM forecasts WHERE run=? ORDER BY seen", (compare or run,)
            ).fetchall()
        quarter_review = []
        for period, metric, forecast, recorded in estimates:
            actual = series(sc, "quarters", metric).get(period) if row and recorded <= chosen else None
            quarter_review.append(
                dict(
                    period=period,
                    metric=metric,
                    forecast=forecast,
                    actual=actual,
                    variance=actual - forecast if actual is not None else None,
                )
            )
        return dict(
            quarter_review=quarter_review,
            forecast_review=forecast_review,
            cash_conversion=cash_conversion,
            dates=dates,
            selected=chosen,
            changes=changes,
            events=events,
            review=bool(changes or any(e["new"] for e in events)),
            kill_fact=(old.get("final") or {}).get("kill_fact"),
            tables=sc.get("tables", {}),
            source=sc.get("url"),
            peers=fp.peers,
            forecasts=(old.get("valuation", {}).get("dcf") or {}).get("projections", []),
            previous_target=old["valuation"].get("target_price"),
            target=baseline["valuation"].get("target_price"),
            previous_assumptions=old.get("assumptions"),
            assumptions=baseline.get("assumptions"),
        )

    @api.get("/watchlist")
    def watchlist():
        results = []
        for run in pins():
            rec = record(run)
            data = evidence(run)
            new = [e for e in data["events"] if e["new"]]
            governance = [e for e in new if set(e["signals"]) - {"Results"}]
            results.append(
                dict(
                    run=run,
                    company=rec["company"],
                    rating=rec["rating"],
                    kill_fact=data["kill_fact"],
                    latest=new[0]["title"] if new else None,
                    governance=len(governance),
                    status=(
                        "Awaiting refresh"
                        if not data["dates"]
                        else "Review needed"
                        if data["review"]
                        else "Reviewed data unchanged"
                    ),
                )
            )
        return results

    @api.post("/{run}/review")
    def review(run: str):
        rec = record(run)
        data = evidence(run)
        desks = ["filings", "fundamentals"]
        if any(e["new"] and set(e["signals"]) - {"Results"} for e in data["events"]):
            desks.append("governance")
        context = {
            "desks": desks,
            "thesis": json.dumps(
                {
                    "headline": rec["headline"],
                    "kill_fact": data["kill_fact"],
                    "changes": data["changes"][:30],
                    "filings": [e for e in data["events"] if e["new"]][:20],
                }
            ),
        }
        return {"id": mgr.start(rec["ticker"], demo=bool(rec["demo"]), review=context)}

    @api.post("/{run}/value")
    def value(run: str, premium: float = Query(ge=0, le=20)):
        rec = record(run)
        cfg = mgr.config()
        q = compute_quant(pack(rec), cfg, with_charts=False)
        assumptions = dict(research(rec).get("assumptions") or {})
        assumptions["cost_of_equity_premium"] = premium / 100
        result = value_company(q, cfg, assumptions)
        return dict(method=result.method, target=result.target_price, intrinsic=result.intrinsic_base)

    @api.put("/{run}/position")
    def position(run: str, amount: float = Query(ge=0, le=1e12), benchmark: str = "^NSEI"):
        rec = record(run)
        if not rec.get("call_id"):
            raise HTTPException(400, "Choose a research run with a filed call")
        if not re.fullmatch(r"[A-Za-z0-9^&._-]{1,40}", benchmark):
            raise HTTPException(400, "Invalid benchmark symbol")
        with connect() as c:
            if amount:
                c.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?)", (run, amount, benchmark))
            else:
                c.execute("DELETE FROM positions WHERE run=?", (run,))
        return {"saved": True}

    @api.get("/call-returns")
    def call_returns(call_id: str, sector_benchmark: str = Query(pattern=r"^[A-Za-z0-9^&._-]{1,40}$")):
        from aladeen.calllog.store import store_from_config

        row = next((r for r in store_from_config(mgr.config()).read() if r["call_id"] == call_id), None)
        if not row:
            raise HTTPException(404, "Call unavailable")
        start = date.fromisoformat(row["call_date"])
        end = date.today()
        quotes = {}
        try:
            for symbol in {row["ticker"], row["benchmark"], sector_benchmark}:
                df = yahoo.ohlcv(symbol, end, years=max(1, (end - start).days // 365 + 2))
                if "adj_close" not in df:
                    raise ValueError(f"Adjusted prices unavailable for {symbol}")
                quotes[symbol] = df["adj_close"]
            frame = pd.concat(quotes, axis=1, join="inner").dropna().sort_index()
            prior = frame.loc[: start.isoformat()]
            if prior.empty or frame.empty or (prior.iloc[-1] <= 0).any():
                raise ValueError("No common starting close")
            returns = (frame.iloc[-1] / prior.iloc[-1] - 1).to_dict()
            return dict(start=str(prior.index[-1].date()), end=str(frame.index[-1].date()), returns=returns)
        except (DataUnavailable, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.get("/sectors")
    def sectors():
        rows = []
        seen = set()
        for rec in sorted(mgr.store.list(), key=lambda r: (r["as_of"], r["created_at"]), reverse=True):
            if rec["status"] != "done":
                continue
            fp = pack(rec)
            if fp.yahoo_symbol in seen:
                continue
            seen.add(fp.yahoo_symbol)
            sector = (
                fp.company.get("classification", {}).get("Sector")
                or fp.yahoo.get("info", {}).get("sector")
                or "Unknown"
            )
            measures = dict(fp.screener.get("top_ratios", {}))
            for group in ("quarters", "ratios", "profit_loss"):
                table = fp.table(group)
                for metric, values in table.get("rows", {}).items():
                    if values and values[-1] is not None:
                        measures.setdefault(metric, values[-1])
            info = fp.yahoo.get("info", {})
            for key, label in [("priceToBook", "P/B (x)"), ("enterpriseToEbitda", "EV/EBITDA (x)")]:
                if info.get(key) is not None:
                    measures[label] = info[key]
            annual = fp.table("profit_loss")
            balance = fp.table("balance_sheet")
            profits = dict(zip(annual.get("columns", []), annual.get("rows", {}).get("Net Profit", []), strict=False))
            assets = balance.get("rows", {}).get("Total Assets", [])
            periods = balance.get("columns", [])
            if (
                len(assets) >= 2
                and len(periods) == len(assets)
                and all(assets[-2:])
                and profits.get(periods[-1]) is not None
            ):
                measures["ROA on average assets (%)"] = 200 * profits[periods[-1]] / sum(assets[-2:])
            rows.append(dict(company=fp.name, sector=sector, date=fp.as_of, metrics=measures))
        return rows

    @api.get("/positions")
    def positions():
        with connect() as c:
            rows = c.execute("SELECT run, amount, benchmark FROM positions ORDER BY run").fetchall()
        result = []
        for run, amount, benchmark in rows:
            rec = mgr.store.get(run)
            if rec:
                fp = pack(rec)
                result.append(
                    dict(
                        run=run,
                        ticker=fp.yahoo_symbol,
                        sector=fp.yahoo.get("info", {}).get("sector") or "Unknown",
                        available=datetime.fromtimestamp(rec["finished_at"]).date().isoformat(),
                        amount=amount,
                        benchmark=benchmark,
                    )
                )
        return result

    @api.get("/performance")
    def performance(start: date, end: date):
        holdings = positions()
        if (
            not holdings
            or start > end
            or end > date.today()
            or any(start.isoformat() <= p["available"] for p in holdings)
        ):
            raise HTTPException(
                400, "Select holdings and a start after every call was published, through today or earlier"
            )
        quotes = {}
        try:
            for symbol in {p[k] for p in holdings for k in ("ticker", "benchmark")}:
                bars = yahoo.ohlcv(symbol, end, years=max(1, (end - start).days // 365 + 1))
                if "adj_close" not in bars:
                    raise ValueError(f"Adjusted price history unavailable for {symbol}")
                quotes[symbol] = bars.loc[start.isoformat() :, "adj_close"]
            return portfolio_series(holdings, quotes)
        except (DataUnavailable, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    return api
