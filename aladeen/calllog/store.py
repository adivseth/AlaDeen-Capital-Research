"""Call log: every rated call is recorded so it can be scored against the benchmark later.

Default backend: a CSV file (``~/.aladeen/call_log.csv``). Optional backend: a Google Sheet
with the same column order (A-S). On Google Sheets, columns M-P (returns, alpha, verdict)
are left to sheet formulas and are never written by this code.
"""

from __future__ import annotations

import csv
from pathlib import Path

COLUMNS = [
    "call_id", "call_date", "company", "ticker", "rating", "target_price", "close_on_call_date",
    "benchmark", "benchmark_close_on_call_date", "review_date", "close_on_review_date",
    "benchmark_close_on_review_date", "stock_return", "benchmark_return", "alpha", "verdict",
    "lesson", "report_file", "notes",
]
FORMULA_COLUMNS = {"stock_return", "benchmark_return", "alpha", "verdict"}  # M-P on the sheet


class CSVStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as f:
            return [{c: r.get(c, "") for c in COLUMNS} for r in csv.DictReader(f)]

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
        rows = self.read()
        row = {c: row.get(c, "") for c in COLUMNS}
        row["call_id"] = row["call_id"] or next_call_id(rows)
        rows.append(row)
        self.write(rows)
        return row

    def describe(self) -> str:
        return str(self.path)


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
        values = self.ws.get_all_values()
        rows = []
        for v in values[1:]:
            if not any(x.strip() for x in v[:3]):
                continue
            v = v + [""] * (len(COLUMNS) - len(v))
            rows.append(dict(zip(COLUMNS, v[: len(COLUMNS)], strict=True)))
        return rows

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
        self._write_row(len(rows) + 2, row)
        return row

    def describe(self) -> str:
        return f"Google Sheet {self.sid}"


def next_call_id(rows: list[dict]) -> str:
    nums = []
    for r in rows:
        cid = str(r.get("call_id", ""))
        if cid.startswith("AC-") and cid[3:].isdigit():
            nums.append(int(cid[3:]))
    return f"AC-{(max(nums) + 1 if nums else 1):03d}"


def store_from_config(cfg: dict):
    if cfg.get("gsheets_spreadsheet_id"):
        return GSheetsStore(cfg["gsheets_spreadsheet_id"], cfg.get("gsheets_worksheet", "Calls"),
                            cfg.get("gsheets_credentials"))
    return CSVStore(cfg["call_log_path"])


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
