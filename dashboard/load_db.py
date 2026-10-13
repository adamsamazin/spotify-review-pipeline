"""Load saved pipeline outputs into Postgres for the dashboard. Offline: no model calls.

    python -m dashboard.load_db runs/full            # uses DATABASE_URL from .env
    python -m dashboard.load_db runs/checkpoint_500 --database-url postgresql://...

Every table is rebuilt from saved artifacts (state.sqlite, rank/, group/, memo/, verify/, evals/, cost/),
so the dashboard always shows exactly what the pipeline saved. Also creates a read-only role
`dashboard_reader` if DASHBOARD_READER_PASSWORD is set, for the deployed backend.
"""

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
DROP TABLE IF EXISTS run_info, reviews, issues, membership, ranking, topic_rollup, memo, claims,
    monthly, evals CASCADE;
CREATE TABLE run_info (key TEXT PRIMARY KEY, value JSONB NOT NULL);
CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY, row_idx INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT,
    topic TEXT, intent TEXT, severity SMALLINT, sentiment REAL, needs_review BOOLEAN, evidence_quote TEXT,
    entities TEXT, review_rating SMALLINT, review_likes INTEGER, app_version TEXT, review_timestamp TEXT,
    cache_source_id TEXT, label_config TEXT);
CREATE TABLE issues (issue_id TEXT PRIMARY KEY, topic TEXT, name TEXT, definition TEXT, member_count INTEGER,
    source TEXT);
CREATE TABLE membership (issue_id TEXT NOT NULL, review_id TEXT NOT NULL, PRIMARY KEY (issue_id, review_id));
CREATE TABLE ranking (rank INTEGER PRIMARY KEY, issue_id TEXT NOT NULL, complaint_count INTEGER,
    severity_sum INTEGER, mean_severity NUMERIC(10,6), priority_score INTEGER);
CREATE TABLE topic_rollup (topic TEXT PRIMARY KEY, complaint_count INTEGER, severity_sum INTEGER,
    mean_severity NUMERIC(10,6));
CREATE TABLE memo (id INTEGER PRIMARY KEY, markdown TEXT, status TEXT, label_config TEXT, created_at TEXT,
    cited_review_ids JSONB);
CREATE TABLE claims (claim_id TEXT PRIMARY KEY, issue_id TEXT, metric TEXT, value TEXT);
CREATE TABLE monthly (month TEXT, topic TEXT, negative INTEGER, completed INTEGER, PRIMARY KEY (month, topic));
CREATE TABLE evals (key TEXT PRIMARY KEY, value JSONB NOT NULL);
"""

INDEXES = """
CREATE INDEX reviews_topic_intent ON reviews (topic, intent);
CREATE INDEX membership_review ON membership (review_id);
"""


def read_json(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def copy_rows(cur, table, cols, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    n = 0
    for r in rows:
        w.writerow(["\\N" if v is None else v for v in r])
        n += 1
    buf.seek(0)
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
        cp.write(buf.getvalue())
    return n


def load(run_dir, url):
    import psycopg
    run_dir = Path(run_dir)
    lite = sqlite3.connect(run_dir / "state.sqlite")
    with psycopg.connect(url, autocommit=False) as pg, pg.cursor() as cur:
        cur.execute(SCHEMA)

        # ---- reviews (processed records; review text itself is not copied, only the evidence quote)
        month_neg, month_all = Counter(), Counter()
        topic_month = defaultdict(Counter)

        def review_rows():
            for (rid, idx, status, reason, rating, likes, ver, ts, rec, lc, src) in lite.execute(
                    "SELECT r.review_id, r.row_idx, r.status, r.reason, r.review_rating, r.review_likes, r.app_version, "
                    "r.review_timestamp, s.record_json, s.label_config, s.cache_source_id FROM records r "
                    "LEFT JOIN results s USING(review_id) ORDER BY r.row_idx"):
                d = json.loads(rec) if rec else {}
                if status == "completed":
                    m = ts[:7]
                    month_all[m] += 1
                    if d["intent"] in ("complaint", "cancellation"):
                        topic_month[m][d["topic"]] += 1
                yield (rid, idx, status, reason, d.get("topic"), d.get("intent"), d.get("severity"), d.get("sentiment"),
                       d.get("needs_review"), d.get("evidence_quote"), json.dumps(d.get("entities", [])) if d else None,
                       int(rating) if str(rating).isdigit() else None, int(likes) if str(likes).isdigit() else None,
                       ver or None, ts, src, lc)
        n_reviews = copy_rows(cur, "reviews", ["review_id", "row_idx", "status", "reason", "topic", "intent", "severity",
                                               "sentiment", "needs_review", "evidence_quote", "entities", "review_rating",
                                               "review_likes", "app_version", "review_timestamp", "cache_source_id",
                                               "label_config"], review_rows())
        copy_rows(cur, "monthly", ["month", "topic", "negative", "completed"],
                  ((m, t, c, month_all[m]) for m, tc in topic_month.items() for t, c in tc.items()))

        # ---- issues, membership, ranking, topic rollup
        with (run_dir / "group" / "issues.csv").open(encoding="utf-8", newline="") as f:
            copy_rows(cur, "issues", ["issue_id", "topic", "name", "definition", "member_count", "source"],
                      ((r["issue_id"], r["topic"], r["name"], r["definition"], r["member_count"], r["source"])
                       for r in csv.DictReader(f)))
        copy_rows(cur, "membership", ["issue_id", "review_id"],
                  lite.execute("SELECT DISTINCT issue_id, review_id FROM membership"))
        with (run_dir / "rank" / "ranking.csv").open(encoding="utf-8", newline="") as f:
            copy_rows(cur, "ranking", ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity",
                                       "priority_score"],
                      ((r["rank"], r["issue_id"], r["complaint_count"], r["severity_sum"], r["mean_severity"],
                        r["priority_score"]) for r in csv.DictReader(f)))
        with (run_dir / "rank" / "topic_rollup.csv").open(encoding="utf-8", newline="") as f:
            copy_rows(cur, "topic_rollup", ["topic", "complaint_count", "severity_sum", "mean_severity"],
                      ((r["topic"], r["complaint_count"], r["severity_sum"], r["mean_severity"])
                       for r in csv.DictReader(f)))

        # ---- memo + claims (the AI recommendation, already validated by code)
        val = read_json(run_dir / "memo" / "memo_validation.json", {})
        md = (run_dir / "memo" / "memo.md").read_text(encoding="utf-8") if (run_dir / "memo" / "memo.md").exists() else ""
        cur.execute("INSERT INTO memo VALUES (1, %s, %s, %s, %s, %s)",
                    (md, val.get("status"), val.get("label_config"), val.get("created_at"),
                     json.dumps(val.get("cited_review_ids", []))))
        with (run_dir / "memo" / "claims.csv").open(encoding="utf-8", newline="") as f:
            copy_rows(cur, "claims", ["claim_id", "issue_id", "metric", "value"],
                      ((r["claim_id"], r["issue_id"], r["metric"], r["value"]) for r in csv.DictReader(f)))

        # ---- run info, evaluations, cost
        info = {
            "run": run_dir.name,
            "manifest": read_json(run_dir / "data_manifest.json", {}),
            "ingestion": read_json(run_dir / "ingestion_report.json", {}).get("course_profile", {}).get("counts", {}),
            "distinct_texts": read_json(run_dir / "ingestion_report.json", {}).get("extras", {}).get(
                "distinct_nonempty_texts"),
            "statuses": dict(lite.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall()),
            "cache_reuse": lite.execute("SELECT COUNT(*) FROM results WHERE cache_source_id IS NOT NULL").fetchone()[0],
            "needs_review": lite.execute(
                "SELECT COUNT(*) FROM results WHERE json_extract(record_json,'$.needs_review')=1").fetchone()[0],
            "calls_by_role": [dict(zip(("role", "model", "calls", "failed", "input_tokens", "output_tokens", "cost_usd",
                                        "seconds"), r)) for r in lite.execute(
                "SELECT role, model, COUNT(*), SUM(outcome='failed'), SUM(input_tokens), SUM(output_tokens), "
                "ROUND(SUM(cost_usd), 6), ROUND(SUM(seconds), 1) FROM calls GROUP BY role, model")],
            "intents": dict(Counter(json.loads(r)["intent"] for (r,) in lite.execute("SELECT record_json FROM results"))),
            "run_summaries": {p.stem: read_json(p) for p in sorted(run_dir.glob("run_summary_*.json"))},
        }
        # precomputed aggregates so the API does not scan 660k rows on every page load
        cur.execute("SELECT topic, COUNT(*) AS reviews, ROUND(AVG(severity)::numeric, 3)::float AS mean_severity, "
                    "SUM(CASE WHEN intent IN ('complaint','cancellation') THEN 1 ELSE 0 END) AS negative "
                    "FROM reviews WHERE status = 'completed' GROUP BY topic ORDER BY reviews DESC")
        info["topic_counts"] = [dict(zip(("topic", "reviews", "mean_severity", "negative"), r)) for r in cur.fetchall()]
        cur.execute("SELECT severity, COUNT(*) FROM reviews WHERE status='completed' GROUP BY severity ORDER BY severity")
        info["severity_counts"] = [{"severity": a, "n": b} for a, b in cur.fetchall()]
        cur.execute("SELECT reason, COUNT(*) FROM reviews WHERE status='quarantined' GROUP BY reason")
        info["quarantine_counts"] = [{"reason": a, "n": b} for a, b in cur.fetchall()]
        cur.executemany("INSERT INTO run_info VALUES (%s, %s)", [(k, json.dumps(v, default=str)) for k, v in info.items()])
        evals = {
            "verify": {k: v for k, v in read_json(run_dir / "verify" / "disagreements.json", {}).items() if k != "cases"},
            "golden": {k: v for k, v in read_json(ROOT / "evals" / "results" / "golden_full.json", {}).items()
                       if k != "cases"},
            "injection": read_json(ROOT / "evals" / "results" / "injection_test.json", {}),
            "controls": {k: {"pass": v.get("pass")} for k, v in read_json(ROOT / "evals" / "results" / "test_controls.json", {}).items()},
            "pilot_cold": {k: read_json(ROOT / "cost" / "pilot_summary_cold.json", {}).get(k)
                           for k in ("wall_seconds", "calls_this_invocation", "timings")},
            "pilot_warm": {k: read_json(ROOT / "cost" / "pilot_summary_warm.json", {}).get(k)
                           for k in ("wall_seconds", "calls_this_invocation", "timings")},
        }
        cur.executemany("INSERT INTO evals VALUES (%s, %s)", [(k, json.dumps(v, default=str)) for k, v in evals.items()])
        cur.execute(INDEXES)
        pw = os.environ.get("DASHBOARD_READER_PASSWORD")
        if pw:
            from psycopg import sql
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname='dashboard_reader'")
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE ROLE dashboard_reader LOGIN PASSWORD {}").format(sql.Literal(pw)))
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname='dashboard_reader'")
        if cur.fetchone():  # tables were just recreated: re-grant read-only access for the deployed backend
            cur.execute("GRANT USAGE ON SCHEMA public TO dashboard_reader")
            cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_reader")
        pg.commit()
    print(f"loaded {n_reviews:,} reviews and analysis outputs from {run_dir} into Postgres")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--database-url")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (add it to .env)")
    load(args.run_dir, url)


if __name__ == "__main__":
    main()
