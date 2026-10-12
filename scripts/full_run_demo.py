"""Full-corpus run with a recorded interruption and resume (paid).

    .venv\\Scripts\\python scripts\\full_run_demo.py

1. Start the full run and deliberately stop enrichment after 40 requests (--max-batches).
2. Snapshot completed IDs  -> runs/full/checkpoint_before.json
3. Resume: 40 more requests in the `resume` phase; completed IDs are never re-sent.
4. Snapshot completed IDs  -> runs/full/checkpoint_after.json
5. Continue to the end: all remaining enrichment, then verify, group, rank and memo.
Every step prints a banner with the time and record counts so the recording is easy to follow.
"""

import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
RUN = ["-m", "pipeline.run", "data/spotify_reviews_18months.csv", "--run", "full",
       "--catalog", "prompts/catalog_accepted.json", "--verify-fraction", "0.01", "--workers", "4"]


def counts():
    db = ROOT / "runs" / "full" / "state.sqlite"
    if not db.exists():
        return "no state yet"
    con = sqlite3.connect(db)
    st = dict(con.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    ph = dict(con.execute("SELECT phase, COUNT(*) FROM calls WHERE role='enrich' GROUP BY phase").fetchall())
    return f"records {st} | enrich calls by phase {ph}"


def banner(text):
    print(f"\n{'=' * 78}\n[{datetime.now():%H:%M:%S}] {text}\n    {counts()}\n{'=' * 78}", flush=True)


def step(args):
    r = subprocess.run([PY, "-u", *args], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"step failed: {' '.join(args)}")


def main():
    t0 = time.time()
    banner("STEP 1  start full run; enrichment will be deliberately interrupted after 40 requests")
    step(RUN + ["--max-batches", "40", "--label", "interrupted"])
    banner("STEP 2  interruption done; saving checkpoint_before (completed IDs so far)")
    step(["-m", "pipeline.checkpoint", "runs/full", "before"])
    banner("STEP 3  RESUME: same settings, 40 more requests; already-completed IDs are not re-sent")
    step(RUN + ["--max-batches", "40", "--label", "resume"])
    banner("STEP 4  saving checkpoint_after (more completed IDs than before)")
    step(["-m", "pipeline.checkpoint", "runs/full", "after"])
    banner("STEP 5  continue to the end: remaining enrichment, then verify, group, rank, memo "
           "(recording can stop here)")
    step(RUN + ["--label", "complete"])
    banner(f"DONE in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
