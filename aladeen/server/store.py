"""Research archive: one row per research run, stored in SQLite under the user's home folder."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

COLUMNS = ["id", "ticker", "company", "as_of", "created_at", "finished_at", "status", "rating", "qualifier",
           "target_price", "cmp", "upside", "headline", "council_verdict", "out_dir", "error", "demo",
           "llm_provider", "deep_model", "quick_model", "seconds", "call_id"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, ticker TEXT, company TEXT, as_of TEXT, created_at REAL, finished_at REAL,
    status TEXT, rating TEXT, qualifier TEXT, target_price REAL, cmp REAL, upside REAL, headline TEXT,
    council_verdict TEXT, out_dir TEXT, error TEXT, demo INTEGER, llm_provider TEXT, deep_model TEXT,
    quick_model TEXT, seconds REAL, call_id TEXT
)"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute(_SCHEMA)
            # runs that were in flight when the app last stopped can never finish
            c.execute("UPDATE runs SET status='error', error='Interrupted: the dashboard was closed' "
                      "WHERE status IN ('queued','running')")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def insert(self, **row) -> None:
        row.setdefault("created_at", time.time())
        keys = [k for k in row if k in COLUMNS]
        with self._lock, self._conn() as c:
            c.execute(f"INSERT INTO runs ({','.join(keys)}) VALUES ({','.join('?' * len(keys))})",
                      [row[k] for k in keys])

    def update(self, run_id: str, **fields) -> None:
        keys = [k for k in fields if k in COLUMNS and k != "id"]
        if not keys:
            return
        with self._lock, self._conn() as c:
            c.execute(f"UPDATE runs SET {','.join(k + '=?' for k in keys)} WHERE id=?",
                      [fields[k] for k in keys] + [run_id])

    def get(self, run_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def list(self, limit: int = 500) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def delete(self, run_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM runs WHERE id=?", (run_id,))
