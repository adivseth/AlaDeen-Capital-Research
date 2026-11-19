"""Call log: every rated call is recorded so it can be scored against the benchmark later.

Default backend: a CSV file (``~/.aladeen/call_log.csv``). Optional backend: a Google Sheet
with the same column order (A-S). On Google Sheets, columns M-P (returns, alpha, verdict)
are left to sheet formulas and are never written by this code.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

COLUMNS = [
    "call_id", "call_date", "company", "ticker", "rating", "target_price", "close_on_call_date",
    "benchmark", "benchmark_close_on_call_date", "review_date", "close_on_review_date",
    "benchmark_close_on_review_date", "stock_return", "benchmark_return", "alpha", "verdict",
    "lesson", "report_file", "notes",
]
FORMULA_COLUMNS = {"stock_return", "benchmark_return", "alpha", "verdict"}  # M-P on the sheet


class CSVStore:
    def __init__(self, path: str | Path, id_floor: int = 0, mirror: SheetReader | None = None):
        self.path = Path(path).expanduser()
        self.id_floor = id_floor
        self.mirror = mirror  # read-only copy of a shared sheet: earlier calls and the next call ID
        self.mirror_error: str | None = None

    def _local(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as f:
            return [{c: r.get(c, "") for c in COLUMNS} for r in csv.DictReader(f)]

    def read(self) -> list[dict]:
        rows = self._local()
        if self.mirror:
            try:
                shared = self.mirror.read()
                self.mirror_error = None
            except Exception as e:  # noqa: BLE001 - the local log still works without the shared sheet
                shared, self.mirror_error = [], str(e)
            seen = {r["call_id"] for r in rows}
            rows = [r for r in shared if r["call_id"] not in seen] + rows
        return rows

    def write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLUMNS})
        tmp.replace(self.path)

    def append(self, row: dict) -> dict:
        local = self._local()
        row = {c: row.get(c, "") for c in COLUMNS}
        row["call_id"] = row["call_id"] or next_call_id(self.read(), self.id_floor)
        if self.mirror:
            note = ("Not yet in the shared sheet: add this row there (columns A-L, Q-S)."
                    + (f" The sheet could not be read ({self.mirror_error}); check the call ID." if self.mirror_error else ""))
            row["notes"] = (row["notes"] + " " if row["notes"] else "") + note
        local.append(row)
        self.write(local)
        return row

    def describe(self) -> str:
        return str(self.path) + (f" (IDs continue from {self.mirror.describe()})" if self.mirror else "")


class SheetReader:
    """Read-only view of a Google Sheet shared as "anyone with the link can view" (CSV export, no key)."""

    def __init__(self, spreadsheet_id: str, gid: str | None = None, session=requests, timeout: int = 20):
        self.sid, self.gid, self.session, self.timeout = spreadsheet_id, gid, session, timeout

    def read(self) -> list[dict]:
        url = f"https://docs.google.com/spreadsheets/d/{self.sid}/export?format=csv"
        if self.gid:
            url += f"&gid={self.gid}"
        r = self.session.get(url, timeout=self.timeout)
        if not r.ok or "text/csv" not in r.headers.get("content-type", ""):
            raise RuntimeError(f"Google Sheet {self.sid} is not readable without a key (HTTP {r.status_code})")
        values = list(csv.reader(io.StringIO(r.text)))
        return _rows_from_values(values)

    def describe(self) -> str:
        return f"Google Sheet {self.sid} (read-only)"


def _rows_from_values(values: list[list[str]]) -> list[dict]:
    rows = []
    for v in values[1:]:
        if not any(x.strip() for x in v[:3]):
            continue
        v = v + [""] * (len(COLUMNS) - len(v))
        rows.append(dict(zip(COLUMNS, v[: len(COLUMNS)], strict=True)))
    return rows


class GSheetsStore:
    """Google Sheets backend (needs ``pip install gspread`` and a service-account JSON key)."""

    def __init__(self, spreadsheet_id: str, worksheet: str, credentials: str | None):
        try:
            import gspread
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Install gspread to use the Google Sheets call log") from e
        gc = gspread.service_account(filename=credentials) if credentials else gspread.service_account()
        self.ws = gc.open_by_key(spreadsheet_id).worksheet(worksheet)
        self.sid = spreadsheet_id

    def read(self) -> list[dict]:
        return _rows_from_values(self.ws.get_all_values())

    def _write_row(self, row_num: int, row: dict) -> None:
        a_l = [row.get(c, "") for c in COLUMNS[:12]]
        q_s = [row.get(c, "") for c in COLUMNS[16:]]
        self.ws.update(range_name=f"A{row_num}:L{row_num}", values=[a_l], value_input_option="USER_ENTERED")
        self.ws.update(range_name=f"Q{row_num}:S{row_num}", values=[q_s], value_input_option="USER_ENTERED")

    def write(self, rows: list[dict]) -> None:
        for i, r in enumerate(rows, start=2):
            self._write_row(i, r)

    def append(self, row: dict) -> dict:
        rows = self.read()
        row = {c: row.get(c, "") for c in COLUMNS}
        row["call_id"] = row["call_id"] or next_call_id(rows)
        self._write_row(len(rows) + 2, row)  # rows skips blank lines; the formula columns M-P are untouched
        return row

    def describe(self) -> str:
        return f"Google Sheet {self.sid}"


def next_call_id(rows: list[dict], floor: int = 0) -> str:
    nums = [int(floor or 0)]
    for r in rows:
        cid = str(r.get("call_id", ""))
        if cid.startswith("AC-") and cid[3:].isdigit():
            nums.append(int(cid[3:]))
    return f"AC-{max(nums) + 1:03d}"


def _has_service_account(cfg: dict) -> bool:
    if cfg.get("gsheets_credentials"):
        return Path(cfg["gsheets_credentials"]).expanduser().exists()
    return (Path.home() / ".config" / "gspread" / "service_account.json").exists()


def store_from_config(cfg: dict):
    """Google Sheets when a service-account key is set up; otherwise the local CSV, reading a shared sheet
    (if one is configured and link-viewable) so earlier calls and the call ID sequence stay in step."""
    sid = cfg.get("gsheets_spreadsheet_id")
    if sid and _has_service_account(cfg):
        return GSheetsStore(sid, cfg.get("gsheets_worksheet", "Calls"), cfg.get("gsheets_credentials"))
    mirror = SheetReader(sid, cfg.get("gsheets_gid")) if sid else None
    return CSVStore(cfg["call_log_path"], id_floor=int(cfg.get("call_id_floor") or 0), mirror=mirror)


def prior_calls(rows: list[dict], yahoo_symbol: str) -> list[dict]:
    return [r for r in rows if r.get("ticker", "").upper() == yahoo_symbol.upper()]


def prior_calls_md(rows: list[dict]) -> str:
    if not rows:
        return "## Prior calls on this company\nNone in the call log."
    lines = ["## Prior calls on this company (from the call log)"]
    for r in rows:
        lines.append(
            f"- {r['call_id']} {r['call_date']}: {r['rating']} target ₹{r['target_price']} at "
            f"₹{r['close_on_call_date']}; latest review {r.get('review_date') or 'not scored'}: stock "
            f"{r.get('stock_return') or 'n/a'}, alpha {r.get('alpha') or 'n/a'}, verdict "
            f"{r.get('verdict') or 'n/a'}. Lesson: {r.get('lesson') or 'none yet'}")
    return "\n".join(lines)
