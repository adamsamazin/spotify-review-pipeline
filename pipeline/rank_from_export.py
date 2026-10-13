"""Regenerate the baseline ranking from the committed grading/ export alone (no run folder, no model calls).

    python -m pipeline.rank_from_export grading          # writes grading/ranking_regenerated.csv and compares

Reads records.jsonl(.gz) and membership.csv, recomputes complaint_count, severity_sum, mean_severity
(six decimals, half-up) and priority_score = severity_sum, sorts by score desc then issue_id asc,
and reports whether the result is byte-for-byte identical to grading/ranking.csv.
"""

import csv
import gzip
import json
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    g = Path(sys.argv[1] if len(sys.argv) > 1 else "grading")
    src = g / "records.jsonl.gz" if (g / "records.jsonl.gz").exists() else g / "records.jsonl"
    opener = gzip.open if src.suffix == ".gz" else open
    sev = {}
    with opener(src, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("status") == "completed" and r["intent"] in ("complaint", "cancellation"):
                sev[r["review_id"]] = r["severity"]
    agg = defaultdict(lambda: [0, 0])
    with (g / "membership.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["review_id"] in sev:
                agg[row["issue_id"]][0] += 1
                agg[row["issue_id"]][1] += sev[row["review_id"]]
    rows = sorted(agg.items(), key=lambda kv: (-kv[1][1], kv[0]))
    out = g / "ranking_regenerated.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"])
        for k, (iid, (n, s)) in enumerate(rows, 1):
            mean = (Decimal(s) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            w.writerow([k, iid, n, s, mean, s])
    same = out.read_bytes() == (g / "ranking.csv").read_bytes()
    print(f"{len(rows)} issues from {len(sev):,} complaint/cancellation records -> {out}; "
          f"identical to ranking.csv: {same}")
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
