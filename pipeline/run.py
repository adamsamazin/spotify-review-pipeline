"""Orchestrator: runs every stage on an input CSV, in a fixed order, under code control.

    python -m pipeline.run data/checkpoint_500.csv --run checkpoint_500            # paid
    python -m pipeline.run data/spotify_reviews_18months.csv --run full --catalog runs/analysis_10000/group/catalog.json
    python -m pipeline.run evals/synthetic/synthetic_8.csv --run _demo --fake       # free

ingest (code) -> enrich (Jev) -> verify (Jev, separate prompt) -> group (Claude names issues once,
Jev assigns) -> rank (code) -> memo (Claude) -> memo checks (code).
Code decides the next stage, retries and stops; models only judge language inside bounded tasks.
Each stage reuses its saved outputs when inputs and settings are unchanged, so a rerun ("warm")
makes no new enrichment calls. Stage timings and outcomes go to runs/<run>/run_log.jsonl and
run_summary.json.
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline.budget import Ledger
from pipeline.contract import ROOT
from pipeline.enrich import DEFAULT_MODEL, Enricher
from pipeline.group import Grouper
from pipeline.ingest import ingest
from pipeline.memo import MemoWriter
from pipeline.rank import compute, write
from pipeline.verify import Verifier


def run(csv_path, run_name, *, fake=False, budget=None, verify_fraction=0.02, verify_min=20, catalog=None,
        max_batches=None, variant="shared_v1", label="run", log=print):
    run_dir = ROOT / "runs" / run_name
    if fake:
        from evals.fakes import fake_claude
        from pipeline.jev import FakeJev
        jev, jev_model, claude = FakeJev(), "fake-jev", fake_claude()
    else:
        from pipeline.claude import ClaudeClient
        from pipeline.jev import JevClient
        jev, jev_model, claude = JevClient(DEFAULT_MODEL), DEFAULT_MODEL, ClaudeClient()
    ledger = Ledger(budget)
    log_path = run_dir / "run_log.jsonl"
    timings, results = {}, {}
    t_start = time.perf_counter()
    start_iso = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def stage(name, fn):
        log(f"== {name}")
        t0 = time.perf_counter()
        out = fn()
        timings[name] = round(time.perf_counter() - t0, 3)
        results[name] = out
        run_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label": label,
                                "stage": name, "seconds": timings[name],
                                "result": out if isinstance(out, dict) else str(out)}, default=str) + "\n")
        return out

    rep = stage("ingest", lambda: {k: v for k, v in ingest(csv_path, run_dir).items() if k != "course_profile"})
    enr = stage("enrich", lambda: Enricher(run_dir, jev, jev_model, variant, ledger, log=log).run(max_batches))
    pending = sqlite3.connect(run_dir / "state.sqlite").execute(
        "SELECT COUNT(*) FROM records WHERE status='pending'").fetchone()[0]
    if pending:
        log(f"stop: {pending} records still pending ({enr['stop_reason']}); downstream stages wait for a resume")
        summary = {"label": label, "stopped_after": "enrich", "pending": pending, "timings": timings,
                   "wall_seconds": round(time.perf_counter() - t_start, 3)}
        (run_dir / f"run_summary_{label}.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    stage("verify", lambda: {k: v for k, v in Verifier(run_dir, jev, jev_model, ledger, log=log)
                             .run_verify(verify_fraction, verify_min).items() if k != "cases"})
    stage("group", lambda: Grouper(run_dir, jev, jev_model, claude, ledger, log=log).run_group(catalog))
    stage("rank", lambda: write(run_dir, compute(run_dir)))
    ver = results["verify"]
    notes = {"verifier_sample_size": ver["verified"], "verifier_any_field_disagreement_rate": ver["any_field_disagreement_rate"],
             "quarantined_records": rep["state"]["statuses"].get("quarantined", 0)}
    stage("memo", lambda: MemoWriter(run_dir, claude, ledger, log=log).run_memo(notes))
    db = sqlite3.connect(run_dir / "state.sqlite")
    by_role = {role: {"attempts": n, "failed": f, "input_tokens": i or 0, "output_tokens": o or 0}
               for role, n, f, i, o in db.execute(
                   "SELECT role, COUNT(*), SUM(outcome='failed'), SUM(input_tokens), SUM(output_tokens) FROM calls "
                   "WHERE started_at >= ? GROUP BY role", (start_iso,))}
    summary = {"label": label, "input": str(csv_path), "run": run_name, "timings": timings,
               "wall_seconds": round(time.perf_counter() - t_start, 3), "calls_this_invocation": by_role,
               "statuses": dict(db.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall()),
               "enrich": {k: enr.get(k) for k in ("requests", "attempts", "completed", "cache_hits", "quarantined",
                                                  "input_tokens", "cost_usd", "stop_reason", "phase", "label_config")},
               "verify": {k: v for k, v in ver.items() if k != "planted_test"}, "planted_test": ver["planted_test"],
               "group": results["group"], "rank": results["rank"], "memo": results["memo"],
               "ledger_spent_usd": round(ledger.spent, 6), "ledger_cap_usd": ledger.cap}
    (run_dir / f"run_summary_{label}.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log(f"done in {summary['wall_seconds']}s: {json.dumps(timings)} | spent across runs ${ledger.spent:.4f}")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--run", help="run name under runs/ (default: CSV stem)")
    ap.add_argument("--label", default="run", help="tag for this invocation, e.g. cold / warm / resume")
    ap.add_argument("--catalog", type=Path, help="accepted issue catalog to reuse")
    ap.add_argument("--verify-fraction", type=float, default=0.02)
    ap.add_argument("--verify-min", type=int, default=20)
    ap.add_argument("--max-batches", type=int, help="stop enrichment after N requests (interruption demo)")
    ap.add_argument("--budget", type=float)
    ap.add_argument("--fake", action="store_true", help="offline fake models (free)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    run(args.csv, args.run or args.csv.stem, fake=args.fake, budget=args.budget, verify_fraction=args.verify_fraction,
        verify_min=args.verify_min, catalog=args.catalog, max_batches=args.max_batches, label=args.label)


if __name__ == "__main__":
    main()
