"""Command line: ``aladeen TCS`` opens the dashboard and starts the research.

Other commands: ``dashboard``, ``demo``, ``retry``, ``resolve``, ``data``, ``value``, ``track``, ``calls``, ``score``, ``config``.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aladeen import __version__
from aladeen.config import load_config

app = typer.Typer(add_completion=False, no_args_is_help=False, rich_markup_mode="rich",
                  help="AlaDeen Capital Research — an AI research firm for NSE/BSE companies.\n\n"
                       "Run [bold]aladeen TCS[/] to open the dashboard and start researching TCS.")
console = Console()

BANNER = (f"[bold #3730a3]AlaDeen Capital Research[/] v{__version__}\n"
          "[dim]An AI research firm for Indian listed companies, led by an AI Chief Investment Officer.\n"
          "Research only — not investment advice.[/]")

COMMANDS = {"research", "retry", "resolve", "dashboard", "demo", "data", "value", "track", "calls", "score", "config"}


def _date(s: str | None) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else date.today()


def _cfg(**over):
    return load_config({k: v for k, v in over.items() if v is not None})


# ---------------------------------------------------------------------------- dashboard plumbing
def _http():
    import requests

    s = requests.Session()
    s.trust_env = False  # never send localhost calls through a proxy
    return s


def _base(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _ping(port: int) -> bool | None:
    """True = our dashboard is up, False = port taken by something else, None = nothing listening."""
    import requests

    try:
        r = _http().get(_base(port) + "/api/health", timeout=1.5)
        return r.ok and r.json().get("app") == "AlaDeen Capital Research"
    except requests.ConnectionError:
        return None
    except (requests.RequestException, ValueError):
        return False


def _ensure_dashboard(port: int, host: str = "127.0.0.1") -> bool:
    """Make sure the dashboard is serving on ``port``. Returns True if this process started it."""
    state = _ping(port)
    if state:
        return False
    if state is False:
        console.print(f"[red]Port {port} is in use by another program.[/] Use --port, or change the port in Settings.")
        raise typer.Exit(2)
    import uvicorn

    from aladeen.server.app import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True, name="dashboard").start()
    for _ in range(100):
        if _ping(port):
            return True
        time.sleep(0.1)
    console.print("[red]The dashboard did not start.[/]")
    raise typer.Exit(1)


def _open(url: str, browser: bool) -> None:
    console.print(f"Dashboard: [link={url}]{url}[/link]")
    if browser:
        try:
            webbrowser.open(url, new=2)
        except webbrowser.Error:
            console.print("[dim]Could not open a browser — copy the link above.[/]")


def _print_event(e: dict) -> None:
    from aladeen.firm.roster import PHASES, TITLES

    phase_titles = {p["id"]: p["title"] for p in PHASES}
    t = e.get("type")
    if t == "phase" and e.get("status") != "done":
        console.print(f"\n[bold #3730a3]▶ {phase_titles.get(e.get('phase'), e.get('phase'))}[/]")
    elif t == "message":
        console.print(f"  [#0f766e]{TITLES.get(e.get('agent'), e.get('agent'))} → "
                      f"{TITLES.get(e.get('to'), e.get('to'))}:[/] {e.get('text', '')}")
    elif t == "agent" and e.get("status") == "working" and e.get("task"):
        console.print(f"  [dim]{TITLES.get(e.get('agent'), e.get('agent'))}: {e['task']}[/]")
    elif t == "log":
        console.print(f"  [dim]{TITLES.get(e.get('agent'), e.get('agent'))}: {e.get('text', '')}[/]")
    elif t == "error":
        console.print(f"\n[bold red]Research stopped: {e.get('text')}[/]")
    elif t == "hold":
        console.print(f"\n[bold #b7791f]{e.get('text')}[/]")


def _follow(port: int, run_id: str) -> dict:
    """Mirror the office in the terminal until the run ends; return the final archive record."""
    http, since = _http(), 0
    while True:
        try:
            res = http.get(f"{_base(port)}/api/runs/{run_id}/events", params={"since": since, "wait": 15},
                           timeout=30).json()
        except Exception:  # noqa: BLE001 - transient; retry
            time.sleep(1)
            continue
        for e in res["events"]:
            since = e["seq"] + 1
            _print_event(e)
        if res["closed"]:
            break
    rec: dict = {}
    for _ in range(40):
        rec = http.get(f"{_base(port)}/api/runs/{run_id}", timeout=10).json()
        if rec["status"] != "running":
            break
        time.sleep(0.5)
    return rec


def _summary(rec: dict, url: str | None) -> None:
    if rec.get("status") == "awaiting":
        where = f"Rule on them in the dashboard ({url}) or here: " if url else "Rule on them here: "
        console.print(Panel(f"[bold]{rec.get('headline') or 'Paused for your ruling'}[/]\n\nThe firm will not value "
                            "the company or sign a call on conflicting evidence.\n"
                            f"{where}[bold]aladeen resolve {rec['id']}[/]",
                            title="Research paused", border_style="#b7791f"))
        return
    if rec.get("status") != "done":
        again = (f"\n\n[bold]Continue the same research (finished work is kept):[/] aladeen retry {rec['id']}"
                 if rec.get("id") else "")
        console.print(Panel(f"[red]{rec.get('error') or 'Research did not finish.'}[/]{again}",
                            title="Research stopped", border_style="red"))
        return
    t = Table(show_header=False, box=None)
    t.add_row("Company", rec["company"])
    t.add_row("Rating", f"[bold]{rec['rating'] or 'Pending'}[/] {rec.get('qualifier') or ''}")
    if rec.get("target_price") is not None:
        t.add_row("CMP / Target", f"₹{rec['cmp']:,.2f} / ₹{rec['target_price']:,.2f} ({rec['upside'] * 100:+.1f}%)")
    if rec.get("headline"):
        t.add_row("Headline", rec["headline"])
    if rec.get("council_verdict"):
        t.add_row("Council", rec["council_verdict"])
    t.add_row("Files", rec["out_dir"])
    if url:
        t.add_row("Report", url)
    console.print(Panel(t, title="Report published", border_style="#0f9d8a"))


def _hold(started: bool, port: int) -> None:
    if not started:
        return
    console.print(f"\n[bold]Dashboard running at {_base(port)}[/] — press [bold]Ctrl+C[/] to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        console.print("Stopped.")


def _launch(ticker: str, as_of: str | None, demo: bool, port: int | None, browser: bool | None, follow: bool) -> None:
    cfg = _cfg()
    port = port or cfg["port"]
    browser = cfg["open_browser"] if browser is None else browser
    started = _ensure_dashboard(port, cfg["host"])
    r = _http().post(_base(port) + "/api/research", json={"ticker": ticker, "as_of": as_of, "demo": demo}, timeout=30)
    if not r.ok:
        console.print(f"[red]{r.json().get('detail', r.text)}[/]")
        raise typer.Exit(2)
    run_id = r.json()["id"]
    url = f"{_base(port)}/#/run/{run_id}"
    _open(url, browser)
    if follow:
        _summary(_follow(port, run_id), url)
    _hold(started, port)


def _headless(ticker: str, on: str | None, demo: bool) -> None:
    from aladeen.server.runs import RunManager

    mgr = RunManager()
    _headless_follow(mgr, mgr.start(ticker, on, demo=demo))


def _headless_follow(mgr, run_id: str) -> None:
    """Mirror a run started by ``mgr`` in this terminal until it ends."""
    since = 0
    while True:
        res = mgr.events(run_id, since, 15)
        for e in res["events"]:
            since = e["seq"] + 1
            _print_event(e)
        if res["closed"]:
            break
    rec: dict = {}
    for _ in range(40):
        rec = mgr.store.get(run_id) or {}
        if rec.get("status") != "running":
            break
        time.sleep(0.5)
    _summary(rec, None)
    console.print(f"[dim]It is in your research archive — open it with: aladeen dashboard  (id {run_id})[/]")


# ---------------------------------------------------------------------------- commands
@app.command()
def research(
    ticker: str = typer.Argument(..., help="NSE symbol (TCS), BSE code (532540) or TCS.NS / 532540.BO"),
    on: str | None = typer.Option(None, "--date", help="Analysis date YYYY-MM-DD (default today)"),
    port: int | None = typer.Option(None, help="Dashboard port (default from Settings, 8765)"),
    browser: bool | None = typer.Option(None, "--browser/--no-browser", help="Open the dashboard in a browser"),
    headless: bool = typer.Option(False, "--headless", help="No dashboard: run in this terminal only"),
    quiet: bool = typer.Option(False, "--quiet", help="Do not mirror the office in the terminal"),
):
    """Open the dashboard and research a company. [dim](Same as: aladeen TICKER)[/]"""
    console.print(Panel(BANNER, border_style="#6366f1"))
    if on:
        _date(on)
    if headless:
        _headless(ticker, on, demo=False)
        return
    _launch(ticker, on, False, port, browser, follow=not quiet)


def _failed_id(run_id: str | None, runs: list[dict]) -> str:
    """The research to try again: the one named, else the latest failed one."""
    if run_id:
        return run_id
    failed = [r for r in runs if r.get("status") == "error"]
    if not failed:
        console.print("[yellow]There is no failed research to try again.[/]")
        raise typer.Exit(1)
    return failed[0]["id"]  # the archive is newest first


@app.command()
def retry(
    run_id: str | None = typer.Argument(None, help="Research id (default: the latest failed research)"),
    port: int | None = typer.Option(None, help="Dashboard port (default from Settings, 8765)"),
    browser: bool | None = typer.Option(None, "--browser/--no-browser", help="Open the dashboard in a browser"),
    headless: bool = typer.Option(False, "--headless", help="No dashboard: run in this terminal only"),
    quiet: bool = typer.Option(False, "--quiet", help="Do not mirror the office in the terminal"),
):
    """Try a failed research again. The same research continues: every finished AI answer is reused."""
    console.print(Panel(BANNER, border_style="#6366f1"))
    if headless:
        from aladeen.server.runs import RunManager

        mgr = RunManager()
        run_id = _failed_id(run_id, mgr.store.list())
        try:
            mgr.retry(run_id)
        except (KeyError, ValueError) as e:
            console.print(f"[red]{e.args[0] if isinstance(e, KeyError) else e}[/]")
            raise typer.Exit(2) from e
        _headless_follow(mgr, run_id)
        return
    cfg = _cfg()
    port = port or cfg["port"]
    browser = cfg["open_browser"] if browser is None else browser
    started = _ensure_dashboard(port, cfg["host"])
    http = _http()
    if not run_id:
        run_id = _failed_id(None, http.get(_base(port) + "/api/runs", timeout=30).json())
    r = http.post(f"{_base(port)}/api/runs/{run_id}/retry", timeout=30)
    if not r.ok:
        console.print(f"[red]{r.json().get('detail', r.text)}[/]")
        raise typer.Exit(2)
    url = f"{_base(port)}/#/run/{run_id}"
    _open(url, browser)
    if not quiet:
        _summary(_follow(port, run_id), url)
    _hold(started, port)


def _ask_rulings(hold: dict) -> tuple[dict, bool]:
    """Ask the owner, in the terminal, to rule on each open question."""
    questions = hold["questions"]
    console.print(f"[bold]{len(questions)} conflict(s) paused this research.[/] Rule on each one, or type "
                  "[bold]draft[/] at any prompt to publish the desk work as a draft with no call.\n")
    rulings: dict[str, dict] = {}
    for i, q in enumerate(questions, 1):
        console.print(f"[bold #b7791f]{i}. {q['text']}[/]")
        for t in q.get("also") or []:
            console.print(f"   [dim]Also raised as: {t}[/]")
        if q["kind"] == "data":
            feeds = ", ".join(f"{k} {v:g}" for k, v in (q.get("feeds") or {}).items())
            console.print(f"   Vendor readings ({q['unit']}): {feeds or 'none'}")
            for e in q.get("evidence") or []:
                console.print(f"   Filed: {e.get('title')} p.{e.get('page')}: {e.get('line')}")
            while True:
                raw = typer.prompt(f"   Figure to use ({q['unit']})").strip()
                if raw.lower() == "draft":
                    return rulings, True
                try:
                    value = float(raw.replace(",", ""))
                    break
                except ValueError:
                    console.print("   [red]Enter a number, e.g. 2150.5[/]")
            note = typer.prompt("   Where is it from (document and page)", default="", show_default=False)
            rulings[q["id"]] = {"value": value, "ruling": note}
        else:
            text = typer.prompt("   Your ruling (which claim is right, and the evidence)").strip()
            if text.lower() == "draft":
                return rulings, True
            rulings[q["id"]] = {"ruling": text}
    return rulings, False


def _paused_id(run_id: str | None, runs: list[dict]) -> str:
    if run_id:
        return run_id
    paused = [r for r in runs if r.get("status") == "awaiting"]
    if not paused:
        console.print("[yellow]No research is waiting for your ruling.[/]")
        raise typer.Exit(1)
    return paused[0]["id"]


@app.command()
def resolve(
    run_id: str | None = typer.Argument(None, help="Research id (default: the latest paused research)"),
    port: int | None = typer.Option(None, help="Dashboard port (default from Settings, 8765)"),
    browser: bool | None = typer.Option(None, "--browser/--no-browser", help="Open the dashboard in a browser"),
    headless: bool = typer.Option(False, "--headless", help="No dashboard: run in this terminal only"),
):
    """Rule on the conflicts that paused a research, then let the firm carry on from where it stopped."""
    console.print(Panel(BANNER, border_style="#6366f1"))
    if headless:
        from aladeen.firm.orchestrator import open_questions
        from aladeen.server.runs import RunManager

        mgr = RunManager()
        run_id = _paused_id(run_id, mgr.store.list())
        rec = mgr.store.get(run_id)
        if not rec or rec["status"] != "awaiting":
            console.print("[red]This research is not waiting for your ruling.[/]")
            raise typer.Exit(2)
        rulings, draft = _ask_rulings(open_questions(rec["out_dir"]))
        try:
            mgr.resolve(run_id, rulings, publish_draft=draft)
        except (KeyError, ValueError) as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(2) from e
        _headless_follow(mgr, run_id)
        return
    cfg = _cfg()
    port = port or cfg["port"]
    browser = cfg["open_browser"] if browser is None else browser
    started = _ensure_dashboard(port, cfg["host"])
    http = _http()
    run_id = _paused_id(run_id, http.get(_base(port) + "/api/runs", timeout=30).json())
    rec = http.get(f"{_base(port)}/api/runs/{run_id}", timeout=30).json()
    if rec.get("status") != "awaiting":
        console.print("[red]This research is not waiting for your ruling.[/]")
        raise typer.Exit(2)
    rulings, draft = _ask_rulings(rec["hold"])
    r = http.post(f"{_base(port)}/api/runs/{run_id}/resolve", json={"rulings": rulings, "publish_draft": draft},
                  timeout=30)
    if not r.ok:
        console.print(f"[red]{r.json().get('detail', r.text)}[/]")
        raise typer.Exit(2)
    url = f"{_base(port)}/#/run/{run_id}"
    _open(url, browser)
    _summary(_follow(port, run_id), url)
    _hold(started, port)


@app.command()
def dashboard(port: int | None = typer.Option(None, help="Port (default 8765)"),
              browser: bool | None = typer.Option(None, "--browser/--no-browser")):
    """Open the dashboard: research archive, live office, call log and settings."""
    console.print(Panel(BANNER, border_style="#6366f1"))
    cfg = _cfg()
    port = port or cfg["port"]
    started = _ensure_dashboard(port, cfg["host"])
    _open(_base(port) + "/", cfg["open_browser"] if browser is None else browser)
    if not started:
        console.print("[dim]The dashboard was already running.[/]")
    _hold(started, port)


@app.command()
def demo(port: int | None = typer.Option(None, help="Dashboard port"),
         browser: bool | None = typer.Option(None, "--browser/--no-browser"),
         headless: bool = typer.Option(False, "--headless", help="Run in this terminal only"),
         out: Path | None = typer.Option(None, help="Write the demo report to this folder (no dashboard)")):
    """Watch the firm research a synthetic company. No API key, no network, no AI calls."""
    console.print(Panel(BANNER, border_style="#6366f1"))
    if out:
        from aladeen.demo import DEMO_DATE, demo_runner, synthetic_factpack
        from aladeen.firm.orchestrator import ResearchRun

        cfg = load_config(use_env=False, use_settings=False)
        cfg["log_calls"] = False
        state = ResearchRun(cfg, "DEMO", DEMO_DATE, runner=demo_runner(),
                            factpack_loader=lambda t, d: synthetic_factpack(d), out_dir=out).run()
        console.print(f"Demo report written to {state['paths']['report']}")
        return
    if headless:
        _headless("DEMO", None, demo=True)
        return
    _launch("DEMO", None, True, port, browser, follow=True)


@app.command()
def data(ticker: str, on: str | None = typer.Option(None, "--date"),
         out: Path | None = typer.Option(None, help="Folder for factpack.json and factsheet.md"),
         documents: bool = typer.Option(False, "--documents/--no-documents")):
    """Collect and check the data only (no AI). Prints the fact sheet the team would read."""
    from aladeen.dataflows.factpack import build_factpack
    from aladeen.firm import context as cx
    from aladeen.quant.engine import compute_quant

    cfg = _cfg()
    cfg["fetch_documents"] = documents
    fp = build_factpack(ticker, _date(on), cfg, progress=lambda m: console.print(f"[dim]{m}[/]"))
    q = compute_quant(fp, cfg, with_charts=False)
    sheet = cx.full_fact_sheet(fp, q)
    console.print(sheet)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        fp.save(out / "factpack.json")
        (out / "factsheet.md").write_text(sheet, encoding="utf-8")
        console.print(f"Saved to {out}")


@app.command()
def value(ticker: str, on: str | None = typer.Option(None, "--date")):
    """Deterministic valuation with history-based assumptions (no AI)."""
    from aladeen.dataflows.factpack import build_factpack
    from aladeen.firm import context as cx
    from aladeen.quant.engine import compute_quant, value_company

    cfg = _cfg()
    fp = build_factpack(ticker, _date(on), cfg)
    q = compute_quant(fp, cfg, with_charts=False)
    if q["valuation_blockers"]:
        console.print(cx.company_md(fp))
        raise typer.Exit(1)
    res = value_company(q, cfg)
    console.print(cx.valuation_md(res.as_dict()))
    console.print("[dim]Default assumptions only. In a full research the Valuation Analyst sets them and the CIO "
                  "signs off.[/]")


@app.command()
def track(ticker: str, on: str | None = typer.Option(None, "--date")):
    """Quarterly tracker: last 5-10 trading days, the prior call and its kill fact (no AI)."""
    from aladeen.calllog import store as calllog
    from aladeen.dataflows.factpack import build_factpack
    from aladeen.firm import context as cx
    from aladeen.quant.engine import compute_quant
    from aladeen.server.store import Store

    cfg = _cfg()
    cfg["fetch_documents"] = False
    fp = build_factpack(ticker, _date(on), cfg)
    q = compute_quant(fp, cfg, with_charts=False)
    console.print(cx.short_term_md(q, fp))
    rows = calllog.prior_calls(calllog.store_from_config(cfg).read(), fp.yahoo_symbol)
    console.print(calllog.prior_calls_md(rows))
    db = Path(cfg["home_dir"]) / "aladeen.db"
    past = [r for r in Store(db).list() if r["status"] == "done" and r["ticker"] == fp.ticker] if db.exists() else []
    for rec in past:  # newest first
        p = Path(rec["out_dir"]) / "research.json"
        if p.exists():
            last = json.loads(p.read_text(encoding="utf-8"))
            console.print(f"\n[bold]Kill fact from the last report ({rec['as_of']}):[/] "
                          f"{last.get('final', {}).get('kill_fact')}\nCheck whether it has occurred.")
            break


@app.command()
def calls():
    """List the call log."""
    from aladeen.calllog import store as calllog

    cfg = _cfg()
    st = calllog.store_from_config(cfg)
    rows = st.read()
    cols = ("call_id", "call_date", "company", "ticker", "rating", "target_price", "close_on_call_date",
            "review_date", "stock_return", "alpha", "verdict")
    t = Table(title=f"Call log ({st.describe()})")
    for c in cols:
        t.add_column(c)
    for r in rows:
        t.add_row(*[str(r.get(c, "")) for c in cols])
    console.print(t if rows else "No calls logged yet.")


@app.command()
def score(on: str | None = typer.Option(None, "--date", help="Review date (default today)")):
    """Score every logged call against the Nifty 50 ("score my calls")."""
    from aladeen.calllog import scoring
    from aladeen.calllog import store as calllog

    cfg = _cfg()
    st = calllog.store_from_config(cfg)
    rows, summary = scoring.score(st.read(), _date(on), cfg["rating_bands"], log=console.print)
    st.write(rows)
    cols = ("call_id", "company", "rating", "call_date", "review_date", "stock_return", "benchmark_return", "alpha",
            "verdict")
    t = Table(title="Scored calls")
    for c in cols:
        t.add_column(c)
    for r in rows:
        t.add_row(*[str(r.get(c, "")) for c in cols])
    console.print(t)
    hr = summary["hit_rate"]
    console.print(f"Calls: {summary['calls']} · scored: {summary['scored']} · matured (12m+): "
                  f"{summary['matured_12m']} · hit rate: {'n/a' if hr is None else f'{hr:.0%}'}")
    if summary["avg_alpha_by_rating"]:
        console.print("Average alpha by rating: " + ", ".join(
            f"{k} {v * 100:+.1f}%" for k, v in summary["avg_alpha_by_rating"].items()))


@app.command(name="config")
def show_config():
    """Show the effective settings (defaults < environment < dashboard Settings). Keys are hidden."""
    cfg = _cfg()
    cfg["api_keys"] = {k: "set" for k, v in (cfg.get("api_keys") or {}).items() if v}
    console.print_json(json.dumps(cfg, default=str))


def main() -> None:  # pragma: no cover - thin wrapper
    """Entry point. ``aladeen TCS`` is shorthand for ``aladeen research TCS``."""
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
        argv = ["research", *argv]
    if not argv:
        argv = ["--help"]
    app(args=argv, prog_name="aladeen")


if __name__ == "__main__":  # pragma: no cover
    main()
