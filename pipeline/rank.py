"""Stage 5 - Rank. Code only; regenerates the baseline ranking from saved records + membership.

    python -m pipeline.rank runs/analysis_10000        # always offline, no model calls

priority(issue) = complaint_count x mean_severity = severity_sum, over completed complaint and
cancellation records; each review counted once per issue. Sorted by score descending, then
issue_id ascending. Means use six decimals with half-up rounding (contract mean_string).
"""

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from pipeline.contract import mean_string

NEGATIVE = ("complaint", "cancellation")


def compute(run_dir):
    run_dir = Path(run_dir)
    db = sqlite3.connect(run_dir / "state.sqlite")
    recs = {rid: json.loads(r) for rid, r in db.execute(
        "SELECT r.review_id, s.record_json FROM records r JOIN results s USING(review_id) WHERE r.status='completed'")}
    members = db.execute("SELECT DISTINCT issue_id, review_id FROM membership").fetchall()
    catalog = json.loads((run_dir / "group" / "catalog.json").read_text(encoding="utf-8"))
    names = {i["issue_id"]: (i["topic"], i["name"]) for i in catalog["issues"]}
    agg = defaultdict(lambda: [0, 0])
    problems = []
    for iid, rid in members:
        rec = recs.get(rid)
        if rec is None or rec["intent"] not in NEGATIVE:
            problems.append(f"{rid} in {iid} is not a completed complaint/cancellation")
            continue
        agg[iid][0] += 1
        agg[iid][1] += rec["severity"]
    negatives = {rid for rid, r in recs.items() if r["intent"] in NEGATIVE}
    uncovered = sorted(negatives - {rid for _, rid in members})
    rows = sorted(agg.items(), key=lambda kv: (-kv[1][1], kv[0]))
    ranking = [{"rank": str(k), "issue_id": iid, "complaint_count": str(n), "severity_sum": str(s),
                "mean_severity": mean_string(s, n), "priority_score": str(s)} for k, (iid, (n, s)) in enumerate(rows, 1)]
    # Topic rollup is an extra view for the memo (sums of the issue rows; not the baseline).
    topics = defaultdict(lambda: [0, 0])
    for iid, (n, s) in agg.items():
        topics[names.get(iid, (iid.split(".")[0], ""))[0]][0] += n
        topics[names.get(iid, (iid.split(".")[0], ""))[0]][1] += s
    topic_rows = [{"topic": t, "complaint_count": str(n), "severity_sum": str(s), "mean_severity": mean_string(s, n)}
                  for t, (n, s) in sorted(topics.items(), key=lambda kv: (-kv[1][1], kv[0]))]
    totals = dict(db.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    intents = defaultdict(int)
    for r in recs.values():
        intents[r["intent"]] += 1
    return {"ranking": ranking, "topics": topic_rows, "names": names, "uncovered": uncovered, "problems": problems,
            "totals": {"records": sum(totals.values()), **totals, "complaint_or_cancellation": len(negatives),
                       "intents": dict(intents)}}


def write(run_dir, result):
    out = Path(run_dir) / "rank"
    out.mkdir(exist_ok=True)
    cols = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]
    with (out / "ranking.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(result["ranking"])
    with (out / "aggregates.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["issue_id", "topic", "name", "complaint_count", "severity_sum", "mean_severity", "priority_score"])
        for r in result["ranking"]:
            t, name = result["names"].get(r["issue_id"], ("", ""))
            w.writerow([r["issue_id"], t, name, r["complaint_count"], r["severity_sum"], r["mean_severity"],
                        r["priority_score"]])
    with (out / "topic_rollup.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["topic", "complaint_count", "severity_sum", "mean_severity"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(result["topics"])
    summary = {"issues_ranked": len(result["ranking"]), "uncovered_negatives": len(result["uncovered"]),
               "membership_problems": len(result["problems"]), "totals": result["totals"],
               "ranking_sha256": hashlib.sha256((out / "ranking.csv").read_bytes()).hexdigest()}
    (out / "rank_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    s = write(args.run_dir, compute(args.run_dir))
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
