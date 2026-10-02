"""Build the standardized grading/ folder from a run (offline; no model calls).

    python -m pipeline.export runs/full --out grading
    python data/check_submission.py check --reference local-reference.json --submission grading --out self-check.json

Files follow data/GRADING_CONTRACT.md: run.json, ingestion.json, records.jsonl(.gz), membership.csv,
ranking.csv, claims.csv, calls.jsonl, checkpoint_before.json, checkpoint_after.json.
"""

import argparse
import csv
import gzip
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from pipeline.contract import FULL_SHA256, ROOT, read_json

RECORD_KEYS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review")
CALL_KEYS = ("request_id", "role", "review_ids", "model", "phase", "outcome", "label_config",
             "input_tokens", "output_tokens")


def records(run_dir):
    """One contract record per source ID, in source order."""
    db = sqlite3.connect(Path(run_dir) / "state.sqlite")
    for rid, sha, status, reason, attempts, rec, lc, src in db.execute(
            "SELECT r.review_id, r.source_sha256, r.status, r.reason, r.attempts, s.record_json, s.label_config, "
            "s.cache_source_id FROM records r LEFT JOIN results s USING(review_id) ORDER BY r.row_idx"):
        if status == "completed":
            body = json.loads(rec)
            out = {"review_id": rid, "source_sha256": sha, "status": "completed",
                   **{k: body[k] for k in RECORD_KEYS}, "label_config": lc}
            if src:
                out["cache_source_id"] = src
        elif status == "quarantined":
            out = {"review_id": rid, "source_sha256": sha, "status": "quarantined", "reason": reason,
                   "attempts": attempts}
        else:
            out = {"review_id": rid, "source_sha256": sha, "status": "pending"}
        yield out


def calls(run_dir):
    for line in (Path(run_dir) / "calls.jsonl").open(encoding="utf-8"):
        c = json.loads(line)
        yield {**{k: c.get(k) for k in CALL_KEYS},
               **{k: c[k] for k in ("run", "batch_no", "attempt", "http_status", "error", "started_at", "seconds",
                                    "cost_usd", "cost_is_estimate") if k in c}}


def export(run_dir, out, gz=True, checkpoints=None):
    run_dir, out = Path(run_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = read_json(run_dir / "data_manifest.json")
    count = sqlite3.connect(run_dir / "state.sqlite").execute("SELECT COUNT(*) FROM records").fetchone()[0]
    (out / "run.json").write_text(json.dumps({
        "version": "a5-audit-v1", "analysis_count": count, "analysis_sha256": manifest["input_sha256"],
        "classification_input_fields": ["review_text"], "allow_multi_issue": False}) + "\n", encoding="utf-8")
    if manifest["input_sha256"] != FULL_SHA256:
        print(f"note: {run_dir.name} is not the full corpus; this export is a development check only")
    opener = (lambda p: gzip.open(p, "wt", encoding="utf-8")) if gz else (lambda p: open(p, "w", encoding="utf-8"))
    with opener(out / ("records.jsonl.gz" if gz else "records.jsonl")) as f:
        for r in records(run_dir):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with opener(out / ("calls.jsonl.gz" if gz else "calls.jsonl")) as f:
        for c in calls(run_dir):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (out / "membership.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["issue_id", "review_id"])
        w.writerows(sqlite3.connect(run_dir / "state.sqlite").execute(
            "SELECT DISTINCT issue_id, review_id FROM membership ORDER BY issue_id, review_id"))
    shutil.copy(run_dir / "rank" / "ranking.csv", out / "ranking.csv")
    shutil.copy(run_dir / "memo" / "claims.csv", out / "claims.csv")
    for name in ("checkpoint_before.json", "checkpoint_after.json"):
        src = Path(checkpoints) / name if checkpoints else run_dir / name
        if src.exists():
            shutil.copy(src, out / name)
        else:
            print(f"warning: {name} not found (record the interruption/resume demo first)")
    ing = run_dir.parent.parent / "grading" / "ingestion.json"
    if manifest["input_sha256"] == FULL_SHA256 and ing.exists() and out.resolve() != ing.parent.resolve():
        shutil.copy(ing, out / "ingestion.json")
    print(f"exported {count} records from {run_dir.name} to {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "grading")
    ap.add_argument("--no-gzip", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    export(args.run_dir, args.out, gz=not args.no_gzip)


if __name__ == "__main__":
    main()
