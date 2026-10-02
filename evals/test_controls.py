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


def enr(d, client, cap=10.0, batch=2):
    return Enricher(d, client, "fake-jev", "inline_v1", Ledger(cap), batch, log=quiet)


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

    out = ROOT / "evals" / "results" / "test_controls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for k, v in results.items():
        print(f"{'PASS' if v['pass'] else 'FAIL'}  {k}")
    sys.exit(0 if all(v["pass"] for v in results.values()) else 1)


if __name__ == "__main__":
    main()
