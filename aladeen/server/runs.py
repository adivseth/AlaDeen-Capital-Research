"""Starts research runs in background threads and keeps their live event logs."""

from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import date, datetime
from pathlib import Path

from aladeen.config import load_config
from aladeen.dataflows.symbols import normalize, safe_component
from aladeen.firm.events import EventLog
from aladeen.firm.orchestrator import ResearchRun
from aladeen.server.store import Store


class RunManager:
    def __init__(self, home_dir: str | None = None):
        self.home_dir = home_dir
        cfg = self.config()
        self.store = Store(Path(cfg["home_dir"]) / "aladeen.db")
        self.live: dict[str, EventLog] = {}
        self._lock = threading.Lock()

    def config(self) -> dict:
        return load_config({"home_dir": self.home_dir} if self.home_dir else None)

    def start(self, ticker: str, as_of: str | None = None, demo: bool = False) -> str:
        cfg = self.config()
        ticker = ticker.strip()
        if demo:
            ticker = "DEMO"
        else:
            normalize(ticker)  # raises ValueError for a malformed ticker
        day = date.fromisoformat(as_of) if as_of else date.today()
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{safe_component(ticker.upper())}-{secrets.token_hex(2)}"
        out_dir = Path(cfg["results_dir"]) / run_id
        self.store.insert(id=run_id, ticker=ticker.upper(), company=ticker.upper(), as_of=day.isoformat(),
                          status="running", out_dir=str(out_dir), demo=int(demo), llm_provider=cfg["llm_provider"],
                          deep_model=cfg["deep_think_llm"], quick_model=cfg["quick_think_llm"])
        ev = EventLog()
        with self._lock:
            self.live[run_id] = ev
        threading.Thread(target=self._run, args=(run_id, cfg, ticker, day, demo, out_dir, ev), daemon=True,
                         name=f"research-{run_id}").start()
        return run_id

    def _run(self, run_id, cfg, ticker, day, demo, out_dir: Path, ev: EventLog) -> None:
        t0 = time.time()
        kw = {}
        if demo:
            from aladeen.demo import demo_runner, synthetic_factpack

            cfg["log_calls"] = False
            kw = {"runner": demo_runner(delay=1.6), "factpack_loader": lambda t, d: synthetic_factpack(d)}
            ev.log("cio", "Demo mode: synthetic company and scripted agents. No AI model is called.")
        try:
            state = ResearchRun(cfg, ticker, day, events=ev, out_dir=out_dir, **kw).run()
            f, v = state["final"], state["valuation"]
            cv = (state.get("council") or {}).get("verdict") or {}
            self.store.update(run_id, status="done", finished_at=time.time(), company=state["fp"].name,
                              rating=f["rating"], qualifier=f.get("qualifier"), target_price=v["target_price"],
                              cmp=v["cmp"], upside=v["upside"], headline=f["headline"],
                              council_verdict=cv.get("verdict"), seconds=round(time.time() - t0, 1),
                              call_id=state.get("call_id"))
        except Exception as e:  # noqa: BLE001 - surfaced to the dashboard
            if not ev.closed:
                ev.emit("error", text=f"{type(e).__name__}: {e}")
            self.store.update(run_id, status="error", finished_at=time.time(), error=f"{type(e).__name__}: {e}",
                              seconds=round(time.time() - t0, 1))
        finally:
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "events.json").write_text(json.dumps(ev.all(), default=str), encoding="utf-8")
            except OSError:
                pass

    def events(self, run_id: str, since: int = 0, wait: float = 10.0) -> dict:
        ev = self.live.get(run_id)
        if ev is not None:
            items = ev.since(since, timeout=wait)
            return {"events": items, "closed": ev.closed and since + len(items) >= len(ev.all())}
        rec = self.store.get(run_id)
        if not rec:
            return {"events": [], "closed": True}
        p = Path(rec["out_dir"]) / "events.json"
        items = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        return {"events": items[since:], "closed": True}
