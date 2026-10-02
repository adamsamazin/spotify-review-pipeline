"""Stage 1 - Prepare. Code only, no model calls.

Reads every row of an input CSV, profiles it with the course helper, finds exact
duplicate texts, and seeds the run's state database: nonempty rows start `pending`,
empty texts are `quarantined` with reason `empty_review_text`.

    python -m pipeline.ingest data/cost_100.csv
    python -m pipeline.ingest data/spotify_reviews_18months.csv --run full
"""

import argparse
import json
import sqlite3
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pipeline.contract import (FIELDS, FULL_EXPECTED, FULL_SHA256, ROOT, csv_rows, file_sha,
                               profile, read_json, row_sha, text_sha, write_json)

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    row_idx          INTEGER NOT NULL,
    review_id        TEXT PRIMARY KEY,
    source_sha256    TEXT NOT NULL,
    text_sha256      TEXT NOT NULL,
    review_text      TEXT NOT NULL,
    review_rating    TEXT NOT NULL,
    review_likes     TEXT NOT NULL,
    app_version      TEXT NOT NULL,
    review_timestamp TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'quarantined')),
    reason           TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS records_status ON records(status);
CREATE INDEX IF NOT EXISTS records_text ON records(text_sha256);
"""


def git_version():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return out + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "uncommitted"


def course_manifest_entry(csv_path):
    manifest = ROOT / "data" / "manifest.json"
    if manifest.exists():
        return read_json(manifest)["files"].get(Path(csv_path).name)
    return None


def ingest(csv_path, run_dir):
    started = time.perf_counter()
    run_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(run_dir / "state.sqlite")
    db.executescript(SCHEMA)

    text_counts, lengths = Counter(), []
    inserted = 0
    with db:  # one transaction; INSERT OR IGNORE keeps statuses from earlier runs intact
        for idx, row in enumerate(csv_rows(csv_path)):
            text = row["review_text"]
            empty = not text.strip()
            if not empty:
                text_counts[text] += 1
                lengths.append(len(text))
            cur = db.execute(
                "INSERT OR IGNORE INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,0)",
                (idx, row["review_id"], row_sha(row), text_sha(text), *(row[k] for k in FIELDS[1:]),
                 "quarantined" if empty else "pending", "empty_review_text" if empty else None))
            inserted += cur.rowcount

    # The course helper re-reads the file so the profile is exactly what the checker computes.
    prof = profile(csv_path)
    counts = prof["counts"]
    lengths.sort()
    dup_groups = {t: n for t, n in text_counts.items() if n > 1}
    statuses = dict(db.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
    db.close()

    extras = {
        "nonempty_texts": counts["records"] - counts["empty_review_text"],
        "distinct_nonempty_texts": len(text_counts),
        "duplicate_text_groups": len(dup_groups),
        "rows_in_duplicate_text_groups": sum(dup_groups.values()),
        "rows_reusable_from_cache": sum(dup_groups.values()) - len(dup_groups),
        "top_duplicate_texts": [{"text": t, "rows": n} for t, n in Counter(dup_groups).most_common(10)],
        "text_length_chars": ({"min": lengths[0], "median": lengths[len(lengths) // 2],
                               "p99": lengths[int(len(lengths) * 0.99)], "max": lengths[-1]}
                              if lengths else {}),
    }

    checks = {}
    expected = course_manifest_entry(csv_path)
    if expected:
        checks["sha256_matches_course_manifest"] = prof["file_sha256"] == expected["sha256"]
    if prof["file_sha256"] == FULL_SHA256:
        observed = {**counts, "distinct_nonempty_texts": extras["distinct_nonempty_texts"]}
        checks["full_corpus_expectations"] = {
            k: {"expected": v, "observed": observed[k], "ok": observed[k] == v} for k, v in FULL_EXPECTED.items()}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": str(Path(csv_path).resolve()),
        "course_profile": prof,
        "extras": extras,
        "checks": checks,
        "state": {"rows_inserted_this_run": inserted, "statuses": statuses},
        "seconds": round(time.perf_counter() - started, 2),
    }
    write_json(run_dir / "ingestion_report.json", report)
    write_json(run_dir / "data_manifest.json", {
        "run_dir": str(run_dir.relative_to(ROOT)) if run_dir.is_relative_to(ROOT) else str(run_dir),
        "input_name": Path(csv_path).name,
        "input_bytes": Path(csv_path).stat().st_size,
        "input_sha256": prof["file_sha256"],
        "parsed_rows_sha256": prof["parsed_rows_sha256"],
        "code_version": git_version(),
        "created_at": report["generated_at"],
    })
    (run_dir / "pending_ids.txt").write_text(
        "\n".join(r for (r,) in sqlite3.connect(run_dir / "state.sqlite").execute(
            "SELECT review_id FROM records WHERE status='pending' ORDER BY row_idx")) + "\n",
        encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="input CSV with the six source columns")
    ap.add_argument("--run", help="run name under runs/ (default: CSV file stem)")
    args = ap.parse_args()
    run_dir = ROOT / "runs" / (args.run or args.csv.stem)
    r = ingest(args.csv, run_dir)
    c, e = r["course_profile"]["counts"], r["extras"]
    print(f"{args.csv.name}: {c['records']:,} rows | empty {c['empty_review_text']} | "
          f"missing app_version {c['missing_app_version']:,} | dup IDs {c['duplicate_review_ids']} | "
          f"distinct nonempty texts {e['distinct_nonempty_texts']:,} | {r['seconds']}s")
    print("statuses:", r["state"]["statuses"])
    print("checks:", json.dumps(r["checks"]))
    print("wrote", run_dir / "ingestion_report.json")


if __name__ == "__main__":
    main()
