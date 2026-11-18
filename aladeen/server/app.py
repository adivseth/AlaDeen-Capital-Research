"""The AlaDeen Capital Research dashboard: a local web app served on 127.0.0.1."""

from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from aladeen import __version__
from aladeen.config import DESKS, EDITABLE, PROVIDER_KEY_ENV, load_config, read_settings, settings_path
from aladeen.dataflows import backups
from aladeen.firm.roster import roster_payload
from aladeen.server.runs import RunManager

WEB = Path(__file__).resolve().parent.parent / "web"

PROVIDERS = [
    {"id": "anthropic", "label": "Anthropic Claude", "key": True,
     "deep": "claude-opus-5-5", "quick": "claude-sonnet-5-5"},
    {"id": "openai", "label": "OpenAI", "key": True},
    {"id": "google", "label": "Google Gemini", "key": True},
    {"id": "xai", "label": "xAI Grok", "key": True},
    {"id": "deepseek", "label": "DeepSeek", "key": True},
    {"id": "moonshot", "label": "Moonshot AI (Kimi)", "key": True},
    {"id": "qwen", "label": "Alibaba Qwen (Model Studio)", "key": True},
    {"id": "mistral", "label": "Mistral AI", "key": True},
    {"id": "zai", "label": "Z.ai (GLM)", "key": True},
    {"id": "meta", "label": "Meta Llama API", "key": True},
    {"id": "xiaomi", "label": "Xiaomi MiMo", "key": True},
    {"id": "openrouter", "label": "OpenRouter", "key": True},
    {"id": "ollama", "label": "Ollama (local)", "key": False},
    {"id": "openai_compatible", "label": "OpenAI-compatible server", "key": False},
]


DATA_SOURCES = [
    {"id": "alphavantage", "label": "Alpha Vantage", "use": "Backup price history when Yahoo Finance fails"},
    {"id": "firecrawl", "label": "Firecrawl", "use": "Reads annual reports and concalls when BSE blocks the download"},
    {"id": "exa", "label": "Exa", "use": "Web research (analyst coverage, sector outlook, company history) and a second "
     "backup for reading annual reports and concalls"},
]
KEY_ENVS = {**PROVIDER_KEY_ENV, **backups.KEY_ENV}


def _write_private(path: Path, text: str) -> None:
    """Write a file only the current user can read (it holds API keys). Created 0600, never world-readable."""
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o600)  # in case the file already existed with wider permissions
    os.replace(tmp, path)


def _mask(key: str) -> str:
    return (key[:3] + "…" + key[-4:]) if len(key) > 10 else "••••"


def create_app(home_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="AlaDeen Capital Research", version=__version__, docs_url=None, redoc_url=None)
    mgr = RunManager(home_dir)
    app.state.mgr = mgr

    # ------------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse((WEB / "index.html").read_text(encoding="utf-8"))

    app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

    @app.get("/api/health")
    def health():
        return {"ok": True, "app": "AlaDeen Capital Research", "version": __version__}

    @app.get("/api/roster")
    def roster():
        return roster_payload()

    # ------------------------------------------------------------------ settings
    @app.get("/api/settings")
    def get_settings():
        cfg = mgr.config()
        keys = {}
        for pid, env in KEY_ENVS.items():
            saved = cfg["api_keys"].get(pid)
            keys[pid] = {"set": bool(saved or os.environ.get(env)),
                         "source": "dashboard" if saved else ("environment" if os.environ.get(env) else None),
                         "masked": _mask(saved) if saved else (_mask(os.environ[env]) if os.environ.get(env) else "")}
        return {"values": {k: cfg.get(k) for k in EDITABLE}, "keys": keys, "providers": PROVIDERS,
                "data_sources": DATA_SOURCES, "desks": DESKS, "paths": {"home": cfg["home_dir"], "research": cfg["results_dir"],
                                          "call_log": cfg["call_log_path"], "settings": str(settings_path(cfg["home_dir"]))}}

    @app.put("/api/settings")
    def put_settings(payload: dict = Body(...)):
        cfg = mgr.config()
        saved = read_settings(cfg["home_dir"])
        for k, v in (payload.get("values") or {}).items():
            if k in EDITABLE:
                saved[k] = v
        keys = dict(saved.get("api_keys") or {})
        for pid, v in (payload.get("api_keys") or {}).items():
            if pid not in KEY_ENVS:
                raise HTTPException(400, f"Unknown key {pid!r}")
            if v:
                keys[pid] = v.strip()
        for pid in payload.get("clear_keys") or []:
            keys.pop(pid, None)
        saved["api_keys"] = keys
        try:  # validate before writing
            load_config({"home_dir": cfg["home_dir"], **{k: v for k, v in saved.items() if k in EDITABLE}},
                        use_settings=False)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e)) from e
        p = settings_path(cfg["home_dir"])
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_private(p, json.dumps(saved, indent=2))
        return get_settings()

    @app.post("/api/settings/test")
    def test_model(payload: dict = Body(default={})):
        from aladeen.llm import LangChainRunner

        tier = payload.get("tier", "quick")
        try:
            out = LangChainRunner(mgr.config()).text("You are a connectivity check.", "Reply with the single word OK.",
                                                     tier=tier, name="settings_test")
            return {"ok": True, "reply": out[:200]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:600]}

    # ------------------------------------------------------------------ research runs
    @app.post("/api/research")
    def start(payload: dict = Body(...)):
        ticker = (payload.get("ticker") or "").strip()
        demo = bool(payload.get("demo"))
        if not ticker and not demo:
            raise HTTPException(400, "Enter a ticker, e.g. TCS or 532540")
        as_of = payload.get("as_of") or None
        if as_of:
            try:
                date.fromisoformat(as_of)
            except ValueError as e:
                raise HTTPException(400, "Date must be YYYY-MM-DD") from e
        try:
            run_id = mgr.start(ticker, as_of, demo=demo)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"id": run_id}

    @app.get("/api/runs")
    def runs():
        return mgr.store.list()

    def _rec(run_id: str) -> dict:
        rec = mgr.store.get(run_id)
        if not rec:
            raise HTTPException(404, "Research not found")
        return rec

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        rec = _rec(run_id)
        p = Path(rec["out_dir"]) / "research.json"
        rec["research"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        return rec

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, since: int = 0, wait: float = 10.0):
        _rec(run_id)
        return mgr.events(run_id, since, min(max(wait, 0.0), 25.0))

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str, download: bool = False, print: bool = False):  # noqa: A002
        rec = _rec(run_id)
        p = Path(rec["out_dir"]) / "report.html"
        if not p.exists():
            raise HTTPException(404, "The report is not ready yet")
        html = p.read_text(encoding="utf-8")
        if print:
            html = html.replace("</body>", "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),"
                                          "600));</script></body>")
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{rec["ticker"]}_{rec["as_of"]}_AlaDeen.html"'
        return HTMLResponse(html, headers=headers)

    @app.get("/api/runs/{run_id}/transcript")
    def transcript(run_id: str):
        p = Path(_rec(run_id)["out_dir"]) / "transcript.md"
        if not p.exists():
            raise HTTPException(404, "Not ready")
        return PlainTextResponse(p.read_text(encoding="utf-8"))

    @app.get("/api/runs/{run_id}/file/{name}")
    def file(run_id: str, name: str):
        if name not in ("factpack.json", "research.json", "transcript.md", "events.json"):
            raise HTTPException(404, "Unknown file")
        p = Path(_rec(run_id)["out_dir"]) / name
        if not p.exists():
            raise HTTPException(404, "Not ready")
        return FileResponse(p, filename=f"{run_id}_{name}")

    @app.delete("/api/runs/{run_id}")
    def delete(run_id: str):
        rec = _rec(run_id)
        if rec["status"] == "running":
            raise HTTPException(409, "This research is still running")
        mgr.store.delete(run_id)
        out = Path(rec["out_dir"])
        if out.exists() and out.parent == Path(mgr.config()["results_dir"]):
            shutil.rmtree(out, ignore_errors=True)
        return {"ok": True}

    # ------------------------------------------------------------------ call log
    @app.get("/api/calls")
    def calls():
        from aladeen.calllog import store as calllog
        from aladeen.calllog.scoring import summarize

        rows = calllog.store_from_config(mgr.config()).read()
        return {"rows": rows, "summary": summarize(rows)}

    @app.post("/api/calls/score")
    def score():
        from aladeen.calllog import scoring
        from aladeen.calllog import store as calllog

        cfg = mgr.config()
        st = calllog.store_from_config(cfg)
        rows, summary = scoring.score(st.read(), date.today(), cfg["rating_bands"])
        st.write(rows)
        return {"rows": rows, "summary": summary}

    @app.exception_handler(Exception)
    def on_error(_req, exc):  # pragma: no cover - last-resort JSON error
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    return app
