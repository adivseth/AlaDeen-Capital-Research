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

Every step is announced on an EventLog so the dashboard can show the office at work.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from aladeen.calllog import store as calllog
from aladeen.dataflows.factpack import FactPack, build_factpack
from aladeen.dataflows.symbols import normalize
from aladeen.firm import context as cx
from aladeen.firm import staff
from aladeen.firm.events import EventLog
from aladeen.firm.schemas import ValuationAssumptions
from aladeen.llm import LangChainRunner, Runner
from aladeen.quant import audit as audit_mod
from aladeen.quant import charts
from aladeen.quant.engine import compute_quant, value_company


def _short(text: str, n: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


class ResearchRun:
    def __init__(self, cfg: dict, ticker: str, as_of: date | str, *, runner: Runner | None = None,
                 events: EventLog | None = None, factpack_loader: Callable[[str, date], FactPack] | None = None,
                 out_dir: str | Path | None = None):
        self.cfg = cfg
        self.ticker = ticker
        self.as_of = as_of if isinstance(as_of, date) else date.fromisoformat(as_of)
        self.runner = runner or LangChainRunner(cfg)
        self.ev = events or EventLog()
        self.factpack_loader = factpack_loader
        self.out_dir = out_dir
        self.state: dict[str, Any] = {"ticker": ticker, "as_of": self.as_of.isoformat(), "errors": [],
                                      "audit": {}, "revisions": []}

    # ------------------------------------------------------------------ helpers
    def _work(self, agent: str, task: str) -> None:
        self.ev.agent(agent, "working", task)

    def _done(self, agent: str, task: str = "") -> None:
        self.ev.agent(agent, "done", task)

    def _known(self) -> list[float]:
        s = self.state
        fp, q = s["fp"], s["quant"]
        texts = [cx.full_fact_sheet(fp, q), s.get("debate_material", ""), *s.get("materials", {}).values(),
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
        self._work("data", "Collecting statements, prices, filings and news")
        fp = (self.factpack_loader(self.ticker, self.as_of) if self.factpack_loader
              else build_factpack(self.ticker, self.as_of, self.cfg, progress=lambda m: self._work("data", m)))
        if not fp.screener.get("tables", {}).get("profit_loss", {}).get("rows"):
            raise RuntimeError(f"No financial statements found for {self.ticker}. " + "; ".join(fp.warnings))
        if fp.prices is None or fp.prices.empty:
            raise RuntimeError(f"No price history for {self.ticker}. " + "; ".join(fp.warnings))
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
        try:
            rows = calllog.store_from_config(self.cfg).read()
            self.state["prior_calls"] = calllog.prior_calls(rows, normalize(self.ticker).yahoo)
        except Exception as e:  # noqa: BLE001
            self.state["prior_calls"] = []
            self.state["errors"].append(f"Call log unavailable: {e}")
        self.ev.phase("data", "done")

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
        self.ev.agent("cio", "waiting", "Waiting for the valuation")
        self.ev.phase("review", "done")

    def _revise(self, to_revise: list, round_label) -> None:
        """Desks rewrite their memos in parallel from the CIO's notes."""
        s = self.state

        def redo(r):
            self.ev.message("cio", r.desk, "Please revise: " + _short(r.notes, 200))
            self._work(r.desk, "Revising memo: " + _short(r.notes, 120))
            text, material = staff.write_memo(r.desk, self.runner, self.cfg, s["fp"], s["quant"],
                                              s["mandate"], revision_notes=r.notes, previous=s["memos"][r.desk],
                                              peer_memos=dict(s["memos"]))
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
                                        challenge=challenge, previous=s.get("assumptions"))
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
        v = self._run_valuation()
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
        s["debate_material_open"] = staff.debate_material(s["fp"], s["quant"], None, s["memos"],
                                                          s["desk_review"].synthesis, prior)
        s["debate_material"] = staff.debate_material(s["fp"], s["quant"], s["valuation"], s["memos"],
                                                     s["desk_review"].synthesis, prior)

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
        review = staff.cio_review(self.runner, self.cfg, s["mandate"], s["memos"], notes)
        to_revise = [r for r in review.reviews if r.verdict == "revise" and r.desk in s["memos"]]
        if not to_revise:
            self.ev.log("cio", "No desk memo needs to change for the council's gaps; they are disclosed in the report.")
        else:
            self._revise(to_revise, "council")
            for r in to_revise:
                self._done(r.desk, "Council gap closed")
            revised = staff.memos_md(s["memos"], tuple(r.desk for r in to_revise))
            self._work("cio", "Re-signing the decision with the revised memos")
            final = staff.cio_decide(self.runner, self.cfg, s["debate_material"] + "\n\n## Memos revised after "
                                     "the council\n" + revised, s["debate_verdict"], s["risk_review"],
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
        s["report_status"] = "draft" if incomplete and self.cfg.get("block_incomplete_reports", True) else "final"
        if s["report_status"] == "draft":
            s["draft_reason"] = ("The independent council found gaps that could change the call: "
                                 + "; ".join(cv.get("gaps_in_report") or ["see the council section"]))
            self.ev.log("cio", "Report held as a DRAFT: " + _short(s["draft_reason"], 300))

    def _publish(self) -> None:
        from aladeen.report.render import log_call, save_outputs

        self.ev.phase("publish")
        s = self.state
        self._work("editor", "Typesetting the report")
        s["_runner"] = self.runner
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
        if isinstance(self.runner, LangChainRunner):
            self.runner._model("deep")
            self.runner._model("quick")

    def run(self) -> dict:
        t0 = time.time()
        steps = [self._data, self._mandate, self._desks, self._review, self._valuation, self._debate, self._risk,
                 self._decision, self._compliance]
        if self.cfg.get("run_council", True):
            steps += [self._council, self._followup]
        steps += [self._status, self._publish]
        try:
            self._preflight()
            for step in steps:
                step()
        except Exception as e:
            self.state["error"] = f"{type(e).__name__}: {e}"
            self.ev.emit("error", text=self.state["error"], detail=traceback.format_exc()[-2000:])
            raise
        f, v = self.state["final"], self.state["valuation"]
        self.ev.emit("done", rating=f["rating"], qualifier=f.get("qualifier"), target_price=v["target_price"],
                     cmp=v["cmp"], upside=v["upside"], headline=f["headline"], seconds=round(time.time() - t0, 1),
                     llm_calls=len(getattr(self.runner, "calls", [])))
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
