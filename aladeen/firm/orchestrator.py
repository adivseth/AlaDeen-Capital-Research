"""The CIO-led research process.

    Data & Quant Desk collects and checks the data
    → CIO sets the mandate and briefs each desk
    → research desks write memos in parallel
    → Compliance audits the memos; CIO reviews and sends weak memos back for revision
    → Valuation Analyst sets assumptions; the engine values the company; a target far from both the
      price and the consensus goes back to the analyst once (reality check)
    → Bull and Bear Advocates open on the business (valuation hidden), then rebut with it; CIO rules
    → Chief Risk Officer stress-tests the view
    → CIO signs the decision, or challenges the valuation once and signs again
    → Compliance audits every number and enforces the rating bands
    → Independent Council reviews the signed report (optional); its gaps go back to the desks, and
      the council checks again; a report it still finds incomplete is published as a draft, unlogged
    → Publishing Editor typesets and files the report

A decision-changing conflict (a vendor figure the filings cannot settle, or contradictory claims the CIO or the
council flags) holds the research for the firm owner instead of carrying it forward. The open questions are saved to
``owner_questions.json``; the owner's rulings go to ``owner_rulings.json`` and the research resumes from its journal:
finished work is reused, the rulings are applied, and every later agent reads them as settled facts.

Every step is announced on an EventLog so the dashboard can show the office at work.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from aladeen.calllog import store as calllog
from aladeen.dataflows.authority import owner_key
from aladeen.dataflows.factpack import FactPack, build_factpack
from aladeen.dataflows.symbols import normalize, safe_component
from aladeen.firm import context as cx
from aladeen.firm import staff
from aladeen.firm.events import EventLog
from aladeen.firm.journal import JOURNAL_FILE, JournalRunner
from aladeen.firm.schemas import ValuationAssumptions
from aladeen.llm import LangChainRunner, Runner
from aladeen.quant import audit as audit_mod
from aladeen.quant import charts
from aladeen.quant.engine import compute_quant, value_company

QUESTIONS_FILE = "owner_questions.json"
RULINGS_FILE = "owner_rulings.json"


class OwnerHold(Exception):  # noqa: N818 - a pause, not a failure
    """The research waits for the firm owner to settle conflicting evidence."""

    def __init__(self, stage: str, questions: list[dict]):
        super().__init__(f"{len(questions)} conflict(s) need the firm owner's ruling")
        self.stage, self.questions = stage, questions


def question_id(kind: str, text: str) -> str:
    """Stable across a resume: the replayed answers raise the same conflicts in the same words."""
    return "q-" + hashlib.sha256(f"{kind}:{text}".encode()).hexdigest()[:12]


def data_question(record: dict) -> dict:
    text = f'{record["period"]} {record["scope"]} {record["metric"]}'
    return {"id": question_id("data", text), "kind": "data", "text": text, "key": owner_key(record),
            "metric": record["metric"], "period": record["period"], "scope": record["scope"],
            "unit": record["unit"], "feeds": record.get("feeds", {}),
            "evidence": [{k: e.get(k) for k in ("title", "url", "page", "value", "line")}
                         for e in record.get("evidence", [])][:6]}


def conflict_question(text: str, raised_by: str) -> dict:
    return {"id": question_id("conflict", text), "kind": "conflict", "text": text, "raised_by": raised_by}


def open_questions(out_dir: str | Path) -> dict | None:
    """The questions a held research is waiting on, with the desk work behind them, or None."""
    p = Path(out_dir) / QUESTIONS_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def record_rulings(out_dir: str | Path, answers: dict[str, dict], publish_draft: bool = False) -> dict:
    """Check the owner's answers against the open questions and add them to the research's rulings.

    ``answers`` maps a question id to ``{"ruling": text, "value": number}``. A conflict needs a ruling in words; a
    data question needs the figure to use (the ruling is the note on where it comes from). With ``publish_draft``
    the owner declines to rule: the research publishes the desk work as a draft, as before, and logs no call."""
    held = open_questions(out_dir)
    if not held:
        raise ValueError("This research is not waiting for a ruling")
    by_id = {q["id"]: q for q in held["questions"]}
    unknown = set(answers) - set(by_id)
    if unknown:
        raise ValueError("Unknown question: " + ", ".join(sorted(unknown)))
    p = Path(out_dir) / RULINGS_FILE
    saved = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    rulings = saved.setdefault("rulings", {})
    missing = []
    for qid, q in by_id.items():
        a = answers.get(qid) or {}
        text = str(a.get("ruling") or "").strip()[:2000]
        value = a.get("value")
        if value is not None and value != "":
            try:
                value = float(value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"{q['text']}: the figure must be a number") from e
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"{q['text']}: the figure must be a number")
        else:
            value = None
        if (q["kind"] == "data" and value is None) or (q["kind"] == "conflict" and not text):
            missing.append(q["text"])
            continue
        rulings[qid] = {"kind": q["kind"], "question": q["text"], "ruling": text, "value": value,
                        "unit": q.get("unit"), "at": time.time()}
    if missing and not publish_draft:
        raise ValueError("Rule on every open question first: " + "; ".join(_short(m, 120) for m in missing))
    saved["publish_draft"] = bool(publish_draft)
    p.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return saved


def _register_path(cfg: dict, ticker: str) -> Path:
    try:
        key = normalize(ticker).yahoo
    except ValueError:
        key = ticker.upper()
    return Path(cfg["home_dir"]) / "rulings" / f"{safe_component(key)}.json"


def remember_rulings(cfg: dict, ticker: str, rulings: dict, run_id: str, as_of: date | str) -> None:
    """Keep the owner's rulings for the company, so the next research on it does not ask the same thing again."""
    as_of = as_of.isoformat() if isinstance(as_of, date) else as_of
    p = _register_path(cfg, ticker)
    reg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"rulings": {}}
    for qid, r in rulings.items():
        reg["rulings"][qid] = {**r, "run": run_id, "as_of": as_of}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def carried_rulings(cfg: dict, ticker: str, as_of: date | str) -> dict:
    """Rulings from earlier research on the company within ``carry_rulings_days`` of this one. A ruling made for a
    later analysis date is not used: a research as of a past date sees only what the owner had settled by then."""
    days = int(cfg.get("carry_rulings_days", 90) or 0)
    if days <= 0:
        return {}
    reg = _earlier_run_rulings(cfg, ticker)
    p = _register_path(cfg, ticker)
    with contextlib.suppress(ValueError):  # an unreadable register: the run folders still count
        reg.update(json.loads(p.read_text(encoding="utf-8")).get("rulings", {}) if p.exists() else {})
    now = as_of if isinstance(as_of, date) else date.fromisoformat(as_of)
    return {k: {**r, "carried": True} for k, r in reg.items()
            if r.get("as_of") and 0 <= (now - date.fromisoformat(r["as_of"])).days <= days}


def _earlier_run_rulings(cfg: dict, ticker: str) -> dict:
    """Rulings saved in the company's earlier research folders (including those from before the register)."""
    out: dict = {}
    root = Path(cfg.get("results_dir") or Path(cfg["home_dir"]) / "research")
    for f in sorted(root.glob(f"*-{safe_component(ticker.upper())}-*/{RULINGS_FILE}")):
        try:
            saved = json.loads(f.read_text(encoding="utf-8"))
            q = open_questions(f.parent) or {}
        except ValueError:
            continue
        run_id = f.parent.name
        as_of = q.get("as_of") or f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"  # older folders: the run's date
        for qid, r in (saved.get("rulings") or {}).items():
            out[qid] = {**r, "run": run_id, "as_of": as_of}
    return out


def _short(text: str, n: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def evidence_revision(before: dict, after: dict, reason: str) -> dict:
    def inputs(value):
        used = dict(value.get("inputs") or {})
        model = {**(used.pop("dcf", None) or {}), **(used.pop("bank", None) or {})}
        return {**used, **model, **(value.get("capital") or {})}

    old, new = inputs(before), inputs(after)
    return {"by": "evidence", "note": reason, "before": before["target_price"], "after": after["target_price"],
            "fair_before": before.get("value_today"), "fair_after": after.get("value_today"),
            "changes": {k: [old.get(k), new.get(k)] for k in sorted(old.keys() | new.keys()) if old.get(k) != new.get(k)}}


class ResearchRun:
    def __init__(self, cfg: dict, ticker: str, as_of: date | str, *, runner: Runner | None = None,
                 events: EventLog | None = None, factpack_loader: Callable[[str, date], FactPack] | None = None,
                 out_dir: str | Path | None = None, resume: bool = False):
        """With ``out_dir``, every finished AI answer and the collected data are saved there as the research goes.
        ``resume=True`` continues an earlier attempt in the same ``out_dir`` from those saved answers; without it,
        any leftovers in ``out_dir`` are cleared and the research starts from scratch."""
        self.cfg = cfg
        self.ticker = ticker
        self.as_of = as_of if isinstance(as_of, date) else date.fromisoformat(as_of)
        self.resume = resume
        self.out_dir = out_dir
        if out_dir and not resume:
            for name in (JOURNAL_FILE, "prior_calls.json", QUESTIONS_FILE, RULINGS_FILE):
                (Path(out_dir) / name).unlink(missing_ok=True)
        self._inner = runner or LangChainRunner(cfg)
        self.runner = JournalRunner(self._inner, Path(out_dir) / JOURNAL_FILE) if out_dir else self._inner
        self.ev = events or EventLog()
        self.factpack_loader = factpack_loader
        self.state: dict[str, Any] = {"ticker": ticker, "as_of": self.as_of.isoformat(), "errors": [],
                                      "audit": {}, "revisions": [], "owner_rulings": [], "rulings_md": ""}

    # ------------------------------------------------------------------ helpers
    def _work(self, agent: str, task: str) -> None:
        self.ev.agent(agent, "working", task)

    def _done(self, agent: str, task: str = "") -> None:
        self.ev.agent(agent, "done", task)

    def _known(self) -> list[float]:
        s = self.state
        fp, q = s["fp"], s["quant"]
        texts = [cx.full_fact_sheet(fp, q), s.get("debate_material", ""), s.get("rulings_md", ""),
                 *s.get("materials", {}).values(),
                 *(d.get("text", "") for d in fp.documents)]
        extra: list[float] = []
        v = s.get("valuation")
        if v:
            texts.append(cx.valuation_md(v))
            extra = [v["target_price"], v["cmp"], v["entry_price_for_mos"], v["intrinsic_base"],
                     v.get("value_today") or 0.0, *(x["value"] for x in v["scenarios"].values()),
                     *(x.get("value_today") or 0.0 for x in v["scenarios"].values())]
            if v.get("implied_roe_at_cmp") is not None:
                extra.append(v["implied_roe_at_cmp"] * 100)
        return audit_mod.known_set(*texts, extra=extra)

    @staticmethod
    def audit_md(audit: dict) -> str:
        flagged = {k: v for k, v in audit.items() if v}
        if not flagged:
            return "## Compliance number audit\nEvery figure audited so far traced to the fact pack."
        lines = ["## Compliance number audit: figures that could NOT be traced to the fact pack"]
        lines += [f"- {k}: {', '.join(v[:12])}" for k, v in flagged.items()]
        return "\n".join(lines)

    # ------------------------------------------------------------------ phases
    def _data(self) -> None:
        self.ev.phase("data")
        self.ev.message("cio", "data", f"Pull everything we have on {self.ticker} as of {self.as_of}.")
        fp = self._saved_factpack()
        if fp is not None:
            self._work("data", "Reusing the fact pack collected on the earlier attempt")
        else:
            self._work("data", "Collecting statements, prices, filings and news")
            fp = (self.factpack_loader(self.ticker, self.as_of) if self.factpack_loader
                  else build_factpack(self.ticker, self.as_of, self.cfg, progress=lambda m: self._work("data", m)))
        if not fp.screener.get("tables", {}).get("profit_loss", {}).get("rows"):
            raise RuntimeError(f"No financial statements found for {self.ticker}. " + "; ".join(fp.warnings))
        if fp.prices is None or fp.prices.empty:
            raise RuntimeError(f"No price history for {self.ticker}. " + "; ".join(fp.warnings))
        self._save_factpack(fp)  # a failure from here on can be continued without collecting the data again
        self._work("data", "Reconciling statements, computing ratios, technicals and charts")
        q = compute_quant(fp, self.cfg)
        self.state.update(fp=fp, quant=q, company=fp.name)
        rec = q["reconciliation"]
        failed = [r for r in rec if r["status"] != "OK"]
        caveats = data_caveats(fp, q)
        self.state["data_caveats"] = caveats
        self.ev.log("data", f"Fact pack ready: {fp.name}. {len(rec) - len(failed)}/{len(rec)} reconciliation "
                            f"checks passed; {len(caveats)} data caveats.", "\n".join(caveats))
        self.ev.emit("company", name=fp.name, ticker=fp.ticker, exchange=fp.exchange, logo=fp.company.get("logo"))
        self._done("data", "Fact pack delivered to the CIO")
        saved = self._saved_prior_calls()
        if saved is not None:
            self.state["prior_calls"] = saved
        else:
            try:
                rows = calllog.store_from_config(self.cfg).read()
                self.state["prior_calls"] = (calllog.prior_calls(rows, normalize(self.ticker).yahoo)
                                             if self.as_of >= date.today() else [])
            except Exception as e:  # noqa: BLE001
                self.state["prior_calls"] = []
                self.state["errors"].append(f"Call log unavailable: {e}")
            self._save_json("prior_calls.json", self.state["prior_calls"])
        self.ev.phase("data", "done")

    # ------------------------------------------------------------------ what a retry reuses
    # The prompts quote the fact pack and the prior calls, so both are frozen on the first attempt: the retry then
    # asks the models exactly the same questions and the saved answers are found again.
    def _saved_path(self, name: str) -> Path | None:
        return Path(self.out_dir) / name if self.out_dir else None

    def _saved_factpack(self) -> FactPack | None:
        p = self._saved_path("factpack.json")
        if not (self.resume and p and p.exists()):
            return None
        try:
            fp = FactPack.load(p)
        except (ValueError, TypeError, KeyError):
            return None  # unreadable: collect the data again
        if fp.owner_facts:  # a published copy: replay with the data as first collected, rulings come later
            fp.owner_facts = {}
            fp.resolve_facts()
        return fp

    def _save_factpack(self, fp: FactPack) -> None:
        p = self._saved_path("factpack.json")
        if p:
            p.parent.mkdir(parents=True, exist_ok=True)
            fp.save(p)

    def _saved_prior_calls(self) -> list[dict] | None:
        p = self._saved_path("prior_calls.json")
        if not (self.resume and p and p.exists()):
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def _save_json(self, name: str, data: Any) -> None:
        p = self._saved_path(name)
        if p:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, default=str), encoding="utf-8")

    def _mandate(self) -> None:
        self.ev.phase("mandate")
        s = self.state
        self._work("cio", "Reading the fact sheet and setting the research mandate")
        m = staff.cio_mandate(self.runner, self.cfg, s["fp"], s["quant"], calllog.prior_calls_md(s["prior_calls"]))
        s["mandate"] = m
        self.ev.log("cio", "Mandate set: " + " | ".join(m.key_questions), "\n".join(m.watch_items))
        for b in m.briefs:
            self.ev.message("cio", b.desk, b.focus)
        self.ev.agent("cio", "waiting", "Waiting for desk memos")
        self.ev.phase("mandate", "done")

    def _desks(self) -> None:
        self.ev.phase("desks")
        s = self.state
        s["memos"], s["materials"] = {}, {}

        def work(desk):
            brief = next(b.focus for b in s["mandate"].briefs if b.desk == desk)
            self._work(desk, _short(brief, 140))
            text, material = staff.write_memo(desk, self.runner, self.cfg, s["fp"], s["quant"], s["mandate"])
            self.ev.log(desk, f"Memo submitted to the CIO ({len(text.split())} words)", _short(text, 900))
            self.ev.agent(desk, "waiting", "Memo with the CIO")
            return desk, text, material

        with ThreadPoolExecutor(max_workers=len(self.cfg["desks"])) as ex:
            for desk, text, material in ex.map(work, self.cfg["desks"]):
                s["memos"][desk] = text
                s["materials"][desk] = material
        self.ev.phase("desks", "done")

    def _review(self) -> None:
        self.ev.phase("review")
        s = self.state
        rounds = max(0, int(self.cfg["cio_revision_rounds"]))
        for round_no in range(rounds + 1):
            self._work("compliance", "Auditing every number in the desk memos")
            known = self._known()
            for k, text in s["memos"].items():
                s["audit"][f"memo:{k}"] = audit_mod.audit_text(text, known)
            flagged = sum(1 for k, v in s["audit"].items() if k.startswith("memo:") and v)
            self.ev.log("compliance", f"Memo audit: {flagged} memo(s) contain figures not found in the fact pack.")
            self.ev.agent("compliance", "waiting", "Standing by")
            self._work("cio", "Reviewing desk memos" + (" (second look)" if round_no else ""))
            review = staff.cio_review(self.runner, self.cfg, s["mandate"], s["memos"], self.audit_md(s["audit"]))
            s["desk_review"] = review
            to_revise = [r for r in review.reviews if r.verdict == "revise" and r.desk in s["memos"]]
            for r in review.reviews:
                if r.desk in s["memos"] and r.verdict == "accept":
                    self.ev.message("cio", r.desk, "Accepted. " + _short(r.notes, 160))
                    self._done(r.desk, "Memo accepted by the CIO")
            self.ev.log("cio", "Synthesis: " + _short(review.synthesis, 400))
            if not to_revise or round_no >= rounds:
                for r in to_revise:
                    self._done(r.desk, "Memo filed with CIO notes")
                break
            self._revise(to_revise, round_no + 1)
        s["evidence_gaps"] = [f'{r["period"]} {r["scope"]} {r["metric"]}' for r in s["quant"]["valuation_blockers"]]
        s["evidence_gaps"].extend(review.unresolved_material_conflicts)
        self.ev.agent("cio", "waiting", "Waiting for the valuation")
        self.ev.phase("review", "done")

    def _revise(self, to_revise: list, round_label) -> None:
        """Desks rewrite their memos in parallel from the CIO's notes."""
        s = self.state
        peers = dict(s["memos"])  # taken once: a replayed revision must see exactly what the first attempt saw

        def redo(r):
            self.ev.message("cio", r.desk, "Please revise: " + _short(r.notes, 200))
            self._work(r.desk, "Revising memo: " + _short(r.notes, 120))
            text, material = staff.write_memo(r.desk, self.runner, self.cfg, s["fp"], s["quant"],
                                              s["mandate"], revision_notes=r.notes, previous=s["memos"][r.desk],
                                              peer_memos=peers)
            self.ev.log(r.desk, "Revised memo submitted", _short(text, 900))
            self.ev.agent(r.desk, "waiting", "Revised memo with the CIO")
            return r, text, material

        with ThreadPoolExecutor(max_workers=len(to_revise)) as ex:
            for r, text, material in ex.map(redo, to_revise):
                s["revisions"].append({"desk": r.desk, "notes": r.notes, "round": round_label})
                s["memos"][r.desk] = text
                s["materials"][r.desk] = material

    def _run_valuation(self, challenge: str | None = None) -> dict:
        """Analyst assumptions -> engine. With ``challenge``, the analyst revises its previous assumptions."""
        s = self.state
        try:
            a = staff.valuation_analyst(self.runner, self.cfg, s["fp"], s["quant"], s["memos"], s["mandate"],
                                        challenge=challenge, previous=s.get("assumptions"),
                                        rulings=s.get("rulings_md", ""))
        except Exception as e:  # noqa: BLE001 - fall back to defaults, but say so
            msg = f"Valuation analyst failed ({type(e).__name__}: {e}); history-based default assumptions used."
            a = ValuationAssumptions(rationale=msg)
            s["errors"].append(msg)
            self.ev.log("valuation", msg)
        self.ev.message("valuation", "data", "Run the model with these assumptions.")
        self._work("data", "Running the valuation model, sensitivity grid, multiples and scenarios")
        try:
            res = value_company(s["quant"], self.cfg, a.to_engine())
        except ValueError as e:
            msg = f"Analyst assumptions rejected by the engine ({e}); history-based defaults used."
            s["errors"].append(msg)
            self.ev.log("data", msg)
            res = value_company(s["quant"], self.cfg, None)
            res.warnings.append(f"Analyst assumptions rejected by the engine ({e}); defaults used.")
        v = res.as_dict()
        v["scenario_chart"] = charts.scenario_chart(v["cmp"], {k: x["value"] for k, x in v["scenarios"].items()},
                                                    v["target_price"])
        s.update(assumptions=a.model_dump(), valuation=v)
        self._done("data", "Valuation computed")
        self.ev.log("valuation", f"12-month target ₹{v['target_price']:,.2f} vs CMP ₹{v['cmp']:,.2f} "
                                 f"({v['upside'] * 100:+.1f}%); bands imply {v['band_rating']}.",
                    _short(a.rationale, 900))
        return v

    def _valuation(self) -> None:
        self.ev.phase("valuation")
        s = self.state
        s["valuation_revisions"] = []
        self.ev.message("cio", "valuation", "Value the company. Answer the key questions in your assumptions.")
        self._work("valuation", "Setting growth, margin, reinvestment and scenario assumptions")
        reason = self.cfg.get("review_reason")
        if reason:
            s["assumptions"] = (self.cfg["review_baseline"].get("inputs") or {})
        v = self._run_valuation(challenge=reason) if reason else self._run_valuation()
        rc = v.get("reality_check") or {}
        if rc.get("flag") and self.cfg.get("reality_check_revision", True):
            note = rc["message"]
            self.ev.message("cio", "valuation", "Reality check: " + _short(note, 220))
            self._work("valuation", "Re-examining the assumptions against the market price")
            s["valuation_revisions"].append({"by": "reality_check", "note": note,
                                             "before": v["target_price"]})
            v = self._run_valuation(challenge=note + " Either show, with evidence, what the market is missing, "
                                                     "or revise the assumptions.")
            s["valuation_revisions"][-1]["after"] = v["target_price"]
        self._done("valuation", "Valuation delivered to the CIO")
        self._set_debate_material()
        self.ev.phase("valuation", "done")

    def _set_debate_material(self) -> None:
        s = self.state
        prior = calllog.prior_calls_md(s["prior_calls"])
        rulings = s.get("rulings_md", "")
        s["debate_material_open"] = staff.debate_material(s["fp"], s["quant"], None, s["memos"],
                                                          s["desk_review"].synthesis, prior, rulings)
        s["debate_material"] = staff.debate_material(s["fp"], s["quant"], s["valuation"], s["memos"],
                                                     s["desk_review"].synthesis, prior, rulings)

    def _debate(self) -> None:
        self.ev.phase("debate")
        s = self.state
        s["debate"] = []
        self.ev.message("cio", "bull", "Make the case for owning it.")
        self.ev.message("cio", "bear", "Make the case against it. Lead with what most threatens value here.")
        for r in range(self.cfg["max_debate_rounds"] + 1):
            material = s["debate_material_open"] if r == 0 else s["debate_material"]
            for side in ("bull", "bear"):
                self._work(side, "Opening case" if r == 0 else "Rebuttal")
                text = staff.debate_turn(side, self.runner, self.cfg, material, s["debate"], r)
                s["debate"].append({"side": side, "round": r, "text": text})
                self.ev.log(side, ("Opening case" if r == 0 else "Rebuttal") + " delivered", _short(text, 900))
                self.ev.agent(side, "waiting", "Listening to the other side")
        for side in ("bull", "bear"):
            self._done(side, "Debate closed")
        self._work("compliance", "Auditing numbers used in the debate")
        known = self._known()
        for d in s["debate"]:
            s["audit"][f"{d['side']}_r{d['round']}"] = audit_mod.audit_text(d["text"], known)
        self.ev.agent("compliance", "waiting", "Standing by")
        self._work("cio", "Ruling on the debate and naming the kill fact")
        verdict = staff.cio_rule_on_debate(self.runner, self.cfg, s["debate_material"], s["debate"],
                                           self.audit_md(s["audit"]))
        s["debate_verdict"] = verdict
        self.ev.log("cio", f"Debate ruling: lean {verdict.lean}. Kill fact: {verdict.kill_fact}",
                    verdict.why_losing_side_lost)
        self.ev.agent("cio", "waiting", "Waiting for the risk office")
        self.ev.phase("debate", "done")

    def _risk(self) -> None:
        self.ev.phase("risk")
        s = self.state
        self.ev.message("cio", "risk", f"Stress-test my draft view ({s['debate_verdict'].lean}).")
        self._work("risk", "Aggressive, neutral and conservative stress tests")
        rr = staff.risk_office(self.runner, self.cfg, cx.valuation_md(s["valuation"]), s["debate_verdict"])
        s["risk_review"] = rr
        self.ev.log("risk", f"Risk rating: {rr.risk_rating}", _short(rr.recommendation, 900))
        self._done("risk", "Risk review delivered to the CIO")
        self.ev.phase("risk", "done")

    def _refresh_risk_after_revision(self) -> None:
        s = self.state
        s["debate_verdict"] = staff.cio_rule_on_debate(self.runner, self.cfg, s["debate_material"],
                                                      s["debate"], self.audit_md(s["audit"]))
        self._risk()

    def _decision(self) -> None:
        self.ev.phase("decision")
        s = self.state
        self._work("cio", "Writing and signing the investment decision")
        final = staff.cio_decide(self.runner, self.cfg, s["debate_material"], s["debate_verdict"], s["risk_review"],
                                 self.audit_md(s["audit"]))
        if final.valuation_challenge and self.cfg.get("cio_valuation_challenge", True):
            # The CIO disputes the valuation: the analyst re-runs it once, then the CIO signs again.
            before = s["valuation"]["target_price"]
            self.ev.message("cio", "valuation", "I dispute the valuation: " + _short(final.valuation_challenge, 220))
            self._work("valuation", "Re-running the valuation on the CIO's challenge")
            s.setdefault("valuation_revisions", []).append({"by": "cio", "note": final.valuation_challenge,
                                                            "before": before})
            v = self._run_valuation(challenge="The CIO challenges the valuation: " + final.valuation_challenge)
            s["valuation_revisions"][-1]["after"] = v["target_price"]
            self._done("valuation", "Revised valuation delivered to the CIO")
            self._set_debate_material()
            self._refresh_risk_after_revision()
            self._work("cio", "Re-signing the decision on the revised valuation")
            final = staff.cio_decide(self.runner, self.cfg, s["debate_material"], s["debate_verdict"],
                                     s["risk_review"], self.audit_md(s["audit"]))
        s["final"] = final.model_dump()
        qual = f" ({final.qualifier})" if final.qualifier else ""
        self.ev.log("cio", f"Decision signed: {final.rating}{qual}, {final.position_size} position. {final.headline}")
        self.ev.agent("cio", "waiting", "Decision with Compliance")
        self.ev.phase("decision", "done")

    def _compliance(self) -> None:
        self.ev.phase("compliance")
        s = self.state
        f, v = s["final"], s["valuation"]
        self._work("compliance", "Checking the rating against the expected-return bands")
        band = v["band_rating"]
        check = {"band_rating": band, "cio_rating": f["rating"], "consistent": f["rating"] == band}
        if not check["consistent"]:
            f["rating"] = band
            check["note"] = (f"The CIO signed {check['cio_rating']}; the expected 12-month total return implies "
                             f"{band}, so the published rating is {band}.")
            self.ev.message("compliance", "cio", check["note"])
        s["rating_check"] = check
        self._work("compliance", "Auditing every figure in the decision and the risk review")
        known = self._known()
        text = " ".join([f["headline"], f["executive_summary"], *f["thesis_pillars"], f["rating_rationale"],
                         *(c["impact"] for c in f["catalysts"])])
        s["audit"]["cio_decision"] = audit_mod.audit_text(text, known)
        rr = s["risk_review"]
        s["audit"]["risk_office"] = audit_mod.audit_text(
            " ".join([rr.aggressive, rr.neutral, rr.conservative, rr.recommendation]), known)
        flagged = {k: x for k, x in s["audit"].items() if x}
        self.ev.log("compliance", f"Compliance sign-off. Rating {'consistent' if check['consistent'] else 'aligned'} "
                                  f"with the bands; {len(flagged)} output(s) carry untraced figures (disclosed in "
                                  "the report).")
        self._done("compliance", "Signed off")
        self._done("cio", "Decision signed")
        self.ev.phase("compliance", "done")

    def _council(self) -> None:
        self.ev.phase("council")
        self._work("council", "Five advisors reviewing the signed report")
        try:
            c = staff.council_review(self.runner, self.cfg, report_summary_md(self.state),
                                     on_step=lambda m: self._work("council", m))
            self.state["council"] = c
            cv = c["verdict"]
            self.ev.log("council", f"Council verdict: {cv['verdict']}. {cv['recommendation']}",
                        "\n".join(cv.get("gaps_in_report", [])))
            self._done("council", f"Verdict: {cv['verdict']}")
        except Exception as e:  # noqa: BLE001
            self.state["council"] = {"error": str(e)}
            self.state["errors"].append(f"Council failed: {e}")
            self.ev.agent("council", "error", f"Council could not complete: {_short(str(e), 160)}")
        self.ev.phase("council", "done")

    def _followup(self) -> None:
        """If the council says the research is incomplete, the CIO sends its gaps to the desks once and re-signs."""
        s = self.state
        cv = (s.get("council") or {}).get("verdict") or {}
        if not self.cfg.get("council_followup", True) or not cv or cv.get("report_complete", True):
            return
        self.ev.phase("followup")
        gaps = cv.get("gaps_in_report") or []
        self.ev.message("council", "cio", "The research is not complete: " + _short("; ".join(gaps), 300))
        self._work("cio", "Deciding which desks must close the council's gaps")
        notes = ("## The independent council found these gaps. Send a desk back only if its memo must change "
                 "to close a gap; accept the rest.\n" + "\n".join(f"- {g}" for g in gaps))
        if s.get("rulings_md"):
            notes += "\n\n" + s["rulings_md"]
        review = staff.cio_review(self.runner, self.cfg, s["mandate"], s["memos"], notes)
        if review.unresolved_material_conflicts:
            self._settle("followup", review.unresolved_material_conflicts, "cio")  # holds for the owner
            if s["evidence_gaps"]:
                self.ev.log("cio", "Decision held for primary evidence: " + "; ".join(s["evidence_gaps"]))
                self.ev.phase("followup", "done")
                return
        to_revise = [r for r in review.reviews if r.verdict == "revise" and r.desk in s["memos"]]
        if not to_revise:
            self.ev.log("cio", "No desk memo needs to change for the council's gaps; they are disclosed in the report.")
        else:
            self._revise(to_revise, "council")
            for r in to_revise:
                self._done(r.desk, "Council gap closed")
            s["desk_review"] = review
            for r in to_revise:
                s["audit"][f"memo:{r.desk}"] = audit_mod.audit_text(s["memos"][r.desk], self._known())
            if any(r.revisit_value for r in to_revise):
                before = s["valuation"]
                v = self._run_valuation(challenge="Reassess affected inputs using these corrected memos: "
                                        + staff.memos_md(s["memos"], tuple(r.desk for r in to_revise)))
                s.setdefault("valuation_revisions", []).append(
                    evidence_revision(before, v, "; ".join(r.notes for r in to_revise)))
            self._set_debate_material()
            if any(r.revisit_value or r.revisit_risk for r in to_revise):
                self._refresh_risk_after_revision()
            self._work("cio", "Re-signing the decision with the revised memos")
            final = staff.cio_decide(self.runner, self.cfg, s["debate_material"], s["debate_verdict"], s["risk_review"],
                                     self.audit_md(s["audit"]))
            s["final"] = final.model_dump()
            self.ev.log("cio", f"Decision re-signed after the council follow-up: {final.rating}. {final.headline}")
            self._compliance()  # bands and number audit again on the new decision
            if self.cfg.get("council_recheck", True):
                first = cv
                self._council()
                s["council"]["first_verdict"] = first
        self._done("cio", "Decision signed")
        self.ev.phase("followup", "done")

    def _status(self) -> None:
        """A report the council still finds incomplete is published as a draft and not logged as a call."""
        s = self.state
        cv = (s.get("council") or {}).get("verdict") or {}
        incomplete = bool(cv) and not cv.get("report_complete", True)
        council_conflicts = cv.get("unresolved_material_conflicts") or []
        if council_conflicts and not s["evidence_gaps"]:
            self._settle("council", council_conflicts, "council")  # holds for the owner; else what is left
            council_conflicts = []
        gaps = s["evidence_gaps"] + council_conflicts
        s["report_status"] = "final"
        if gaps:
            s.update(report_status="draft", draft_reason="Verify against the primary documentation: " + "; ".join(gaps))
        elif incomplete and self.cfg.get("block_incomplete_reports", True):
            s.update(report_status="draft", draft_reason="The independent council found gaps that could change the call: "
                     + "; ".join(cv.get("gaps_in_report") or ["see the council section"]))
        if s["report_status"] == "draft":
            if gaps or not s["fp"].synthetic:
                s.update(decision_pending=True, final={"rating": None, "headline": "Awaiting evidence review"},
                         valuation={"target_price": None, "upside": None, "cmp": s["quant"]["market"]["cmp"]})
            self.ev.log("cio", "Report held as a DRAFT: " + _short(s["draft_reason"], 300))

    # ------------------------------------------------------------------ the firm owner's rulings
    def _load_rulings(self) -> dict:
        p = self._saved_path(RULINGS_FILE)
        if not (p and p.exists()):
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}

    def _settle(self, stage: str, conflicts: list[str], raised_by: str) -> None:
        """Apply the owner's rulings, then hold the research if a decision-changing conflict is still open.

        Data rulings put the owner's figure into the fact pack, so the engine can value the company. Every ruling,
        from this hold or an earlier one, is given to the agents from the valuation onward as a settled fact. With
        nothing ruled the agents' questions are unchanged, so a resumed research replays its saved answers."""
        s, saved = self.state, self._load_rulings()
        rulings = {**carried_rulings(self.cfg, self.ticker, s["as_of"]), **(saved.get("rulings") or {})}
        fp = s["fp"]
        figures = {}
        for record in s["quant"]["valuation_blockers"]:
            q, ruling = data_question(record), rulings.get(data_question(record)["id"])
            if ruling and ruling.get("value") is not None and q["key"] not in fp.owner_facts:
                figures[q["key"]] = {"value": ruling["value"], "note": ruling.get("ruling") or ""}
        if figures:
            fp.owner_facts.update(figures)
            s["quant"] = compute_quant(fp, self.cfg)
            s["data_caveats"] = data_caveats(fp, s["quant"])
            self.ev.log("data", "The firm owner's figures are in the fact pack: " + "; ".join(
                f"{k.replace('|', ' ')} = {v['value']:g}" for k, v in figures.items()))
        s["owner_rulings"] = [{"id": k, **r} for k, r in rulings.items()]
        s["rulings_md"] = staff.rulings_md(s["owner_rulings"])
        conflicts = list(dict.fromkeys(c.strip() for c in conflicts if c and c.strip()))
        questions = [data_question(r) for r in s["quant"]["valuation_blockers"]]
        questions += [conflict_question(c, raised_by) for c in conflicts]
        open_ = self._drop_repeats([q for q in questions if q["id"] not in rulings], rulings)
        settled = len(questions) - len(open_)
        if settled:
            self.ev.log("cio", f"{settled} conflict(s) settled by the firm owner; the research continues on those rulings.")
        s["evidence_gaps"] = [q["text"] for q in open_]
        if open_ and self.out_dir and self.cfg.get("hold_for_owner", True) and not saved.get("publish_draft"):
            raise OwnerHold(stage, open_)

    def _drop_repeats(self, open_: list[dict], rulings: dict) -> list[dict]:
        """Agents at different stages flag the same point in their own words. A conflict that repeats one the owner
        has already ruled on is settled by that ruling; one that repeats an earlier conflict in the same list is
        merged into it. Nothing is asked when there is nothing to compare."""
        new = [q for q in open_ if q["kind"] == "conflict"]
        if not new or (not rulings and len(new) < 2):
            return open_
        ruled = [{"id": k, **r} for k, r in rulings.items()]
        try:
            matches = staff.match_conflicts(self.runner, self.cfg, [q["text"] for q in new], ruled)
        except Exception as e:  # noqa: BLE001 - when the check fails, ask the owner rather than guess
            self.state["errors"].append(f"Repeat check on conflicts failed: {e}")
            return open_
        drop = set()
        for q, m in zip(new, matches, strict=True):
            if m["same_as"]:
                drop.add(q["id"])
                self.ev.log("cio", "Already ruled by the firm owner (same point, new wording): " + _short(q["text"], 200),
                            "Ruling applied: " + (rulings[m["same_as"]].get("ruling") or rulings[m["same_as"]]["question"]))
            elif m["duplicate_of"] is not None:
                drop.add(q["id"])
                new[m["duplicate_of"]].setdefault("also", []).append(q["text"])
        if drop:
            self.state.setdefault("repeats_dropped", 0)
            self.state["repeats_dropped"] += len(drop)
        return [q for q in open_ if q["id"] not in drop]

    def _hold(self, h: OwnerHold) -> None:
        """Save the open questions and stop. The research resumes when the owner has ruled on every one."""
        s = self.state
        review = s.get("desk_review")
        s["held"] = {"stage": h.stage, "questions": h.questions}
        self._save_json(QUESTIONS_FILE, {
            "stage": h.stage, "asked_at": time.time(), "as_of": s["as_of"], "questions": h.questions,
            "synthesis": getattr(review, "synthesis", ""), "memos": s.get("memos", {})})
        try:  # the working papers so far, so the owner can read the desk work behind each conflict
            from aladeen.report.render import transcript_md
            Path(self.out_dir, "transcript.md").write_text(transcript_md(s), encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - the questions matter more than the transcript
            s["errors"].append(f"Working papers not written at the hold: {e}")
        for q in h.questions:
            self.ev.message("cio", "owner", "Please rule: " + _short(q["text"], 300))
        self._work("cio", "Waiting for the firm owner to settle the conflicting evidence")
        self.ev.emit("hold", stage=h.stage, questions=h.questions,
                     text=f"Research paused: {len(h.questions)} conflict(s) need your ruling before the "
                          f"{'valuation' if h.stage == 'review' else 'decision'} goes ahead.")

    def _publish(self) -> None:
        from aladeen.report.render import log_call, save_outputs

        self.ev.phase("publish")
        s = self.state
        self._work("editor", "Typesetting the report")
        s["_runner"] = self.runner
        if self.cfg.get("review_baseline") and s.get("report_status") != "draft":
            s.setdefault("valuation_revisions", []).append(evidence_revision(
                self.cfg["review_baseline"], s["valuation"], self.cfg["review_reason"]))
        paths = save_outputs(s, self.cfg, self.out_dir)
        s["paths"] = {k: str(p) for k, p in paths.items()}
        if self.cfg.get("log_calls", True) and s.get("report_status", "final") == "draft":
            self.ev.log("editor", "Draft report: the call is not filed in the call log until the gaps are closed.")
        elif self.cfg.get("log_calls", True):
            try:
                row = log_call(s, self.cfg, paths["report"])
                if row:
                    s["call_id"] = row["call_id"]
                    self.ev.log("editor", f"Call {row['call_id']} filed in the call log.")
            except Exception as e:  # noqa: BLE001
                s["errors"].append(f"Call log write failed: {e}")
        self._done("editor", "Report published")
        self.ev.phase("publish", "done")

    # ------------------------------------------------------------------ run
    def _preflight(self) -> None:
        """Fail in seconds, not minutes: build both model clients (no call is made) before any data work."""
        if isinstance(self._inner, LangChainRunner):
            self._inner._model("deep")
            self._inner._model("quick")

    def run(self) -> dict:
        t0 = time.time()
        steps = [self._data, self._mandate, self._desks, self._review, self._valuation, self._debate, self._risk,
                 self._decision, self._compliance]
        try:
            self._preflight()
            if self.resume and isinstance(self.runner, JournalRunner) and self.runner.restored:
                self.ev.log("cio", f"Continuing the earlier research: {self.runner.restored} finished AI answers "
                                   "are reused, so the firm picks up where it stopped.")
            for step in steps:
                if step == self._valuation:
                    self._settle("review", self.state["desk_review"].unresolved_material_conflicts, "cio")
                    if self.state["evidence_gaps"]:
                        break  # holding is off: the desk work is published as a draft
                step()
            if not self.state["evidence_gaps"]:
                prior_band = (self.cfg.get("review_baseline") or {}).get("band_rating")
                changed = prior_band and prior_band != self.state["valuation"]["band_rating"]
                if self.cfg.get("run_council", True) or (changed and self.cfg.get("council_on_band_change")):
                    self._council()
                    self._followup()
            self._status()
            self._publish()
        except OwnerHold as h:
            self._hold(h)
            return self.state
        except Exception as e:
            self.state["error"] = f"{type(e).__name__}: {e}"
            self.ev.emit("error", text=self.state["error"], detail=traceback.format_exc()[-2000:])
            raise
        f, v = self.state["final"], self.state["valuation"]
        self.ev.emit("done", rating=f["rating"], qualifier=f.get("qualifier"), target_price=v["target_price"],
                     cmp=v["cmp"], upside=v["upside"], headline=f["headline"], seconds=round(time.time() - t0, 1),
                     llm_calls=len(getattr(self.runner, "calls", [])),
                     reused_calls=getattr(self.runner, "replayed", 0))
        return self.state


def report_summary_md(s: dict) -> str:
    """Condensed view of the signed research for the independent council."""
    f, v, d = s["final"], s["valuation"], s["debate_verdict"]
    fp = s["fp"]
    lines = [
        f"# {fp.name} ({fp.exchange}: {fp.ticker}) — {f['rating']}"
        f"{' (' + f['qualifier'] + ')' if f.get('qualifier') else ''}",
        f"Headline: {f['headline']}",
        f"CMP ₹{v['cmp']:,.2f}; target ₹{v['target_price']:,.2f}; upside {v['upside'] * 100:.1f}%; "
        f"expected total return {v['total_return'] * 100:.1f}%; position {f['position_size']}",
        f"## Executive summary\n{f['executive_summary']}",
        "## Thesis pillars\n" + "\n".join(f"- {p}" for p in f["thesis_pillars"]),
        cx.valuation_md(v),
        "## Debate outcome\n" + f"Surviving bull points: {d.surviving_bull_points}\n"
        f"Surviving bear points: {d.surviving_bear_points}\nKill fact: {f['kill_fact']}",
        "## Risk office\n" + s["risk_review"].model_dump_json(indent=1),
        "## Risks\n" + "\n".join(f"- {r['risk']} ({r['probability']}/{r['impact']})" for r in f["risks"]),
        f"## Governance score: {f['governance_score']}",
        "## Desk memos\n" + staff.memos_md(s.get("memos", {})),
        cx.reconciliation_md(s["quant"]),
        cx.warnings_md(fp, [*s.get("data_caveats", []), *v.get("warnings", [])]),
    ]
    if s.get("rulings_md"):
        lines.append(s["rulings_md"])
    flagged = {k: x for k, x in s.get("audit", {}).items() if x}
    if flagged:
        lines.append("## Number audit flags\n" + "\n".join(f"- {k}: {', '.join(x[:10])}" for k, x in flagged.items()))
    return "\n\n".join(lines)


def run_research(cfg: dict, ticker: str, as_of: date | str, **kw) -> dict:
    return ResearchRun(cfg, ticker, as_of, **kw).run()


def data_caveats(fp: FactPack, q: dict) -> list[str]:
    """Every known limit of the data: fact-pack warnings, failed reconciliations and engine notes."""
    out = list(fp.warnings)
    out += [f"Reconciliation mismatch: {r['check']} ({r['period']}): expected {r['expected']:,}, "
            f"reported {r['actual']:,}" for r in q.get("reconciliation", []) if r["status"] != "OK"]
    out += [n for n in q.get("market", {}).get("notes", []) if n not in out]
    return out
