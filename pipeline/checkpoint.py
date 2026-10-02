"""Snapshot completed IDs for the interruption/resume evidence (offline).

    python -m pipeline.checkpoint runs/full before    # after the deliberate interruption
    python -m pipeline.checkpoint runs/full after     # after resuming and completing more work

Writes runs/<run>/checkpoint_<when>.json = {"completed_ids": [...], plus counts and time}.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def snapshot(run_dir, when):
    run_dir = Path(run_dir)
    db = sqlite3.connect(run_dir / "state.sqlite")
    ids = [r for (r,) in db.execute("SELECT review_id FROM records WHERE status='completed' ORDER BY row_idx")]
    counts = dict(db.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    calls = db.execute("SELECT phase, COUNT(*) FROM calls WHERE role='enrich' GROUP BY phase").fetchall()
    out = {"completed_ids": ids, "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "statuses": counts, "enrich_calls_by_phase": dict(calls)}
    path = run_dir / f"checkpoint_{when}.json"
    path.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print(f"{path}: {len(ids)} completed | statuses {counts} | enrich calls {dict(calls)}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("when", choices=["before", "after"])
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    snapshot(args.run_dir, args.when)


if __name__ == "__main__":
    main()
