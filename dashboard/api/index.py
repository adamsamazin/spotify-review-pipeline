"""Dashboard backend: read-only JSON API over the processed results stored in Postgres.

Deployed as a Vercel Python function; every /api/* path is routed here (see vercel.json).
Local: uvicorn dashboard.api.index:app --reload   (needs DATABASE_URL)
No model calls happen here: the AI recommendation was generated and validated by the pipeline.
"""

import json
import os
from decimal import Decimal

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

app = FastAPI(title="Spotify review pipeline API", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def q(sql, params=(), one=False):
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(500, "DATABASE_URL is not configured")
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as con:
        con.execute("SET default_transaction_read_only = on")
        rows = con.execute(sql, params).fetchall()
    rows = [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows]
    return (rows[0] if rows else None) if one else rows


def info(key):
    r = q("SELECT value FROM run_info WHERE key = %s", (key,), one=True)
    return r["value"] if r else None


@app.get("/api/health")
def health():
    return {"ok": True, "reviews": q("SELECT COUNT(*) AS n FROM reviews", one=True)["n"]}


@app.get("/api/summary")
def summary():
    statuses = info("statuses") or {}
    return {
        "run": info("run"), "manifest": info("manifest"), "ingestion": info("ingestion"),
        "distinct_texts": info("distinct_texts"), "statuses": statuses,
        "total_records": sum(statuses.values()), "cache_reuse": info("cache_reuse"),
        "needs_review": info("needs_review"), "intents": info("intents"), "calls_by_role": info("calls_by_role"),
        "topics": q("SELECT topic, COUNT(*) AS reviews, ROUND(AVG(severity)::numeric, 3) AS mean_severity, "
                    "SUM(CASE WHEN intent IN ('complaint','cancellation') THEN 1 ELSE 0 END) AS negative "
                    "FROM reviews WHERE status = 'completed' GROUP BY topic ORDER BY reviews DESC"),
        "severity": q("SELECT severity, COUNT(*) AS n FROM reviews WHERE status='completed' GROUP BY severity "
                      "ORDER BY severity"),
        "quarantine": q("SELECT reason, COUNT(*) AS n FROM reviews WHERE status='quarantined' GROUP BY reason"),
    }


@app.get("/api/ranking")
def ranking(limit: int = 25):
    return q("SELECT r.*, i.topic, i.name, i.definition FROM ranking r JOIN issues i USING (issue_id) "
             "ORDER BY r.rank LIMIT %s", (max(1, min(limit, 200)),))


@app.get("/api/topics")
def topics():
    return q("SELECT * FROM topic_rollup ORDER BY severity_sum DESC, topic")


@app.get("/api/trend")
def trend():
    return q("SELECT month, topic, negative, completed FROM monthly ORDER BY month, topic")


@app.get("/api/issues/{issue_id}")
def issue(issue_id: str, limit: int = 15):
    row = q("SELECT i.*, r.rank, r.complaint_count, r.severity_sum, r.mean_severity, r.priority_score "
            "FROM issues i LEFT JOIN ranking r USING (issue_id) WHERE i.issue_id = %s", (issue_id,), one=True)
    if not row:
        raise HTTPException(404, "unknown issue_id")
    row["reviews"] = q(
        "SELECT v.review_id, v.severity, v.intent, v.sentiment, v.evidence_quote, v.review_rating, v.review_likes, "
        "v.review_timestamp FROM membership m JOIN reviews v USING (review_id) WHERE m.issue_id = %s "
        "AND v.cache_source_id IS NULL ORDER BY v.severity DESC, v.review_likes DESC NULLS LAST, v.review_id LIMIT %s",
        (issue_id, max(1, min(limit, 100))))
    row["severity_breakdown"] = q(
        "SELECT v.severity, COUNT(*) AS n FROM membership m JOIN reviews v USING (review_id) WHERE m.issue_id = %s "
        "GROUP BY v.severity ORDER BY v.severity", (issue_id,))
    return row


@app.get("/api/memo")
def memo():
    m = q("SELECT * FROM memo WHERE id = 1", one=True) or {}
    m["claims"] = q("SELECT c.*, r.rank FROM claims c LEFT JOIN ranking r USING (issue_id) ORDER BY "
                    "NULLIF(regexp_replace(c.claim_id, '\\D', '', 'g'), '')::int")
    ids = m.get("cited_review_ids") or []
    m["cited_reviews"] = q("SELECT review_id, topic, intent, severity, evidence_quote FROM reviews "
                           "WHERE review_id = ANY(%s)", (ids,)) if ids else []
    return m


@app.get("/api/reviews/{review_id}")
def review(review_id: str):
    row = q("SELECT * FROM reviews WHERE review_id = %s", (review_id,), one=True)
    if not row:
        raise HTTPException(404, "unknown review_id")
    row["entities"] = json.loads(row["entities"]) if row.get("entities") else []
    row["issues"] = q("SELECT m.issue_id, i.name FROM membership m JOIN issues i USING (issue_id) "
                      "WHERE m.review_id = %s", (review_id,))
    return row


@app.get("/api/evals")
def evals():
    return {r["key"]: r["value"] for r in q("SELECT key, value FROM evals")}
