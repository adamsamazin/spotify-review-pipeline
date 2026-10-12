"""Free, offline control tests using the fake model (synthetic data; excluded from business results).

    .venv\\Scripts\\python -m evals.test_controls

Each scenario ingests evals/synthetic/synthetic_8.csv into a fresh runs/_test_* dir and checks
record accounting after a rehearsed failure. Results are written to evals/results/test_controls.json.
"""

import json
import shutil
import sqlite3
import sys
from pathlib import Path

from pipeline.budget import Ledger
from pipeline.contract import ROOT
from pipeline.enrich import Enricher
from pipeline.ingest import ingest
from pipeline.jev import FakeJev

SYN = ROOT / "evals" / "synthetic" / "synthetic_8.csv"
quiet = lambda *a, **k: None  # noqa: E731


def fresh(name):
    d = ROOT / "runs" / f"_test_{name}"
    shutil.rmtree(d, ignore_errors=True)
    ingest(SYN, d)
    return d


def statuses(d):
    db = sqlite3.connect(d / "state.sqlite")
    out = dict(db.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    out["reasons"] = [r for (r,) in db.execute("SELECT reason FROM records WHERE status='quarantined'")]
    out["call_outcomes"] = [list(r) for r in db.execute("SELECT outcome, attempt, phase FROM calls ORDER BY seq")]
    return out


def enr(d, client, cap=10.0, batch=2, workers=1):
    return Enricher(d, client, "fake-jev", "inline_v1", Ledger(cap), batch, log=quiet, workers=workers)


def main():
    results = {}

    d = fresh("transient")  # call 1 overloaded (529) -> backoff -> succeeds
    s = enr(d, FakeJev(fail_plan={1: "transient"})).run()
    st = statuses(d)
    results["transient_retry"] = {"pass": st.get("completed") == 7 and s["failed_attempts"] == 1, **st}

    d = fresh("malformed")  # call 1 returns an invalid label for one review -> retried once -> completes
    enr(d, FakeJev(fail_plan={1: "malformed"})).run()
    st = statuses(d)
    results["malformed_retry_once"] = {"pass": st.get("completed") == 7, **st}

    d = fresh("quarantine")  # first attempt and the retry both malformed -> quarantined with reason
    enr(d, FakeJev(fail_plan={1: "malformed", 2: "malformed"})).run()
    st = statuses(d)
    results["invalid_twice_quarantined"] = {
        "pass": st.get("quarantined") == 2 and any("invalid_output_after_retry" in r for r in st["reasons"]), **st}

    d = fresh("missing")  # one answer ID missing from the response -> detected, retried
    enr(d, FakeJev(fail_plan={1: "drop_one"})).run()
    st = statuses(d)
    results["missing_answer_id_detected"] = {"pass": st.get("completed") == 7, **st}

    d = fresh("resume")  # interrupt after 1 request, then resume; completed IDs are never re-sent
    enr(d, FakeJev()).run(max_batches=1)
    db = sqlite3.connect(d / "state.sqlite")
    before = {r for (r,) in db.execute("SELECT review_id FROM records WHERE status='completed'")}
    enr(d, FakeJev()).run()
    after = {r for (r,) in db.execute("SELECT review_id FROM records WHERE status='completed'")}
    resent = [json.loads(ids) for (ids,) in db.execute("SELECT review_ids FROM calls WHERE phase='resume'")]
    overlap = before & {i for ids in resent for i in ids}
    results["interrupt_resume"] = {"pass": before < after and not overlap and len(after) == 7,
                                   "completed_before": len(before), "completed_after": len(after),
                                   "resume_calls_resending_completed_ids": sorted(overlap), **statuses(d)}

    d = fresh("budget")  # a cap below the next reservation stops the run before spending
    led = Ledger(0.0)
    led.rates[("fake-jev", "input_tokens")] = 1e-6  # give the fake model a price so reservations are > 0
    s = Enricher(d, FakeJev(), "fake-jev", "inline_v1", led, 2, log=quiet).run()
    results["budget_stop"] = {"pass": s["stop_reason"].startswith("budget stop") and s["attempts"] == 0,
                              "stop_reason": s["stop_reason"], **statuses(d)}

    # ---- parallel workers (queue + 2 threads; one writer) ----
    d = fresh("parallel")
    s = enr(d, FakeJev(), workers=2).run()
    st = statuses(d)
    dup = sqlite3.connect(d / "state.sqlite").execute(
        "SELECT COUNT(*) - COUNT(DISTINCT review_id) FROM results").fetchone()[0]
    results["parallel_2_workers_complete"] = {"pass": st.get("completed") == 7 and dup == 0 and s["attempts"] == 3,
                                              "duplicate_results": dup, **st}

    d = fresh("parallel_resume")
    enr(d, FakeJev(), workers=2).run(max_batches=1)
    db = sqlite3.connect(d / "state.sqlite")
    before = {r for (r,) in db.execute("SELECT review_id FROM records WHERE status='completed'")}
    enr(d, FakeJev(), workers=2).run()
    after = {r for (r,) in db.execute("SELECT review_id FROM records WHERE status='completed'")}
    resent = [json.loads(ids) for (ids,) in db.execute("SELECT review_ids FROM calls WHERE phase='resume'")]
    overlap = before & {i for ids in resent for i in ids}
    results["parallel_interrupt_resume"] = {"pass": before < after and not overlap and len(after) == 7,
                                            "completed_before": len(before), "completed_after": len(after), **statuses(d)}

    d = fresh("parallel_budget")  # small cap: stops on budget, never exceeds it, leaves work pending
    led = Ledger(0.0)
    led.rates[("fake-jev", "input_tokens")] = 1e-6  # price the fake so spend accumulates in this ledger
    led.rates[("fake-jev", "output_tokens")] = 0.0
    from pipeline.enrich import estimate_tokens
    from pipeline.questions import build_request
    one = estimate_tokens(*build_request(["Good", "Good"], "inline_v1")) * 1e-6
    led.cap = led.spent + one * 1.5
    s = Enricher(d, FakeJev(), "fake-jev", "inline_v1", led, 2, log=quiet, workers=2).run()
    st = statuses(d)
    results["parallel_budget_stop"] = {"pass": s["stop_reason"].startswith("budget stop") and s["attempts"] >= 1
                                       and led.spent + led.reserved <= led.cap + 1e-12 and st.get("pending", 0) > 0,
                                       "attempts": s["attempts"], "spent_usd": led.spent, "cap_usd": led.cap,
                                       "stop_reason": s["stop_reason"], **statuses(d)}

    # ---- memo: a wrong number is rejected by code, the retry passes ----
    from evals.fakes import fake_claude
    from pipeline.memo import MemoWriter
    from pipeline.run import run as run_pipeline
    run_pipeline(ROOT / "data" / "cost_100.csv", "_test_memo", fake=True, log=quiet)
    md = ROOT / "runs" / "_test_memo"
    (md / "memo" / "memo_validation.json").unlink(missing_ok=True)
    m = MemoWriter(md, fake_claude(bad_first_memo=True), Ledger(), log=quiet).run_memo()
    results["memo_wrong_number_rejected_then_fixed"] = {"pass": m["status"] == "valid" and m["calls"] == 2,
                                                        "status": m["status"], "calls": m["calls"]}

    out = ROOT / "evals" / "results" / "test_controls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for k, v in results.items():
        print(f"{'PASS' if v['pass'] else 'FAIL'}  {k}")
    sys.exit(0 if all(v["pass"] for v in results.values()) else 1)


if __name__ == "__main__":
    main()
