"""Check that the live dashboard API serves exactly the saved results (offline files vs deployed backend).

    .venv/Scripts/python scripts/check_dashboard.py [base_url]

Compares /api/ranking with grading/ranking.csv, /api/memo claims with grading/claims.csv, and /api/summary
counts with grading/records.jsonl.gz. Writes evals/results/dashboard_check.json.
"""
import csv, gzip, json, sys, urllib.request
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://spotify-review-dashboard-adam-samazins-projects.vercel.app"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    checks = {}
    api_rank = get("/api/ranking?limit=200")
    with (ROOT / "grading" / "ranking.csv").open(encoding="utf-8", newline="") as f:
        saved = list(csv.DictReader(f))
    diffs = []
    for a, s in zip(api_rank, saved):
        for k in ("rank", "issue_id", "complaint_count", "severity_sum", "priority_score"):
            if str(a[k]) != s[k]:
                diffs.append(f"rank {s['rank']} {k}: api {a[k]} vs saved {s[k]}")
        if Decimal(str(a["mean_severity"])).quantize(Decimal("0.000001")) != Decimal(s["mean_severity"]):
            diffs.append(f"rank {s['rank']} mean_severity: api {a['mean_severity']} vs saved {s['mean_severity']}")
    checks["ranking"] = {"api_rows": len(api_rank), "saved_rows": len(saved), "differences": diffs,
                         "pass": len(api_rank) == len(saved) and not diffs}
    memo = get("/api/memo")
    with (ROOT / "grading" / "claims.csv").open(encoding="utf-8", newline="") as f:
        saved_claims = {r["claim_id"]: r for r in csv.DictReader(f)}
    cd = [c["claim_id"] for c in memo["claims"] if saved_claims.get(c["claim_id"], {}).get("value") != c["value"]
          or saved_claims[c["claim_id"]]["issue_id"] != c["issue_id"]]
    checks["claims"] = {"api_claims": len(memo["claims"]), "saved_claims": len(saved_claims), "mismatched": cd,
                        "memo_status": memo.get("status"),
                        "memo_text_matches_results_memo": memo["markdown"].strip() == (ROOT / "results" / "memo.md").read_text(encoding="utf-8").strip(),
                        "pass": len(memo["claims"]) == len(saved_claims) and not cd and memo.get("status") == "valid"}
    s = get("/api/summary")
    st, intents = Counter(), Counter()
    with gzip.open(ROOT / "grading" / "records.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            st[r["status"]] += 1
            if r["status"] == "completed":
                intents[r["intent"]] += 1
    checks["summary"] = {"api_statuses": s["statuses"], "saved_statuses": dict(st), "api_intents": s["intents"],
                         "saved_intents": dict(intents),
                         "pass": s["statuses"] == dict(st) and s["intents"] == dict(intents)}
    out = {"base_url": BASE, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "all_pass": all(c["pass"] for c in checks.values()), **checks}
    (ROOT / "evals" / "results" / "dashboard_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for k, c in checks.items():
        print(f"{'PASS' if c['pass'] else 'FAIL'}  {k}")
    sys.exit(0 if out["all_pass"] else 1)


if __name__ == "__main__":
    main()
