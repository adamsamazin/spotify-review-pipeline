"""Stage 2 - Classify (role: enrich). Jev labels topic/intent/severity/sentiment; code does the rest.

    python -m pipeline.enrich runs/cost_100                 # paid: calls Jev
    python -m pipeline.enrich runs/cost_100 --dry-run       # free: request sizes + cost estimate only
    python -m pipeline.enrich runs/_test --fake             # free: offline fake model for testing
    python -m pipeline.enrich runs/full --workers 4         # paid, 4 parallel request workers

Control flow is owned by code:
  * one representative per exact text is sent; duplicates reuse its validated result (cache_source_id)
  * requests hold <= 50 reviews; every returned question ID is checked against what was sent
  * invalid output -> retried once, then quarantined with the reason and attempt count
  * 429/529/5xx/timeouts -> bounded exponential backoff with jitter, then the run stops (progress kept)
  * spend is reserved before each request and the run stops before the cap would be crossed
  * results are committed after every request, so an interrupted run resumes without re-paying
  * --workers N: a queue feeds N threads that only make network calls; this thread keeps the queue,
    the spend reservations and every database write (one writer, atomic commits)
"""

import argparse
import json
import random
import sqlite3
import sys
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from pipeline.budget import BudgetExceeded, Ledger
from pipeline.contract import ROOT
from pipeline.questions import FIELDS, SCHEMA_VERSION, VARIANTS, build_request, review_key
from pipeline.schema import to_record, validate

DEFAULT_MODEL = "jev-1.13.0"  # pinned version, not the moving `jev-latest` alias
MAX_BATCH = 50
MAX_TRANSIENT_ATTEMPTS = 4
CHARS_PER_TOKEN_EST = 3.0      # conservative pre-call estimate; real usage replaces it

TABLES = """
CREATE TABLE IF NOT EXISTS results (
    review_id TEXT PRIMARY KEY, label_config TEXT NOT NULL, record_json TEXT NOT NULL,
    cache_source_id TEXT, request_id TEXT, completed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calls (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, request_id TEXT, role TEXT, phase TEXT,
    review_ids TEXT, model TEXT, label_config TEXT, outcome TEXT, http_status INTEGER, error TEXT,
    input_tokens INTEGER, output_tokens INTEGER, est_cost_usd REAL, cost_usd REAL, cost_is_estimate INTEGER,
    attempt INTEGER, batch_no INTEGER, started_at TEXT, seconds REAL);
CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, phase TEXT, label_config TEXT,
    started_at TEXT, ended_at TEXT, stop_reason TEXT, wall_seconds REAL, summary_json TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def label_config_for(model, variant):
    return f"{model}+enrich_{variant}+{SCHEMA_VERSION}"


def q_dump(questions):
    return {k: q.model_dump(exclude_none=True) if hasattr(q, "model_dump") else q for k, q in questions.items()}


def estimate_tokens(state, questions):
    return int(len(json.dumps(state, ensure_ascii=False) + json.dumps(q_dump(questions), ensure_ascii=False))
               / CHARS_PER_TOKEN_EST)


class Enricher:
    def __init__(self, run_dir, client, model, variant, ledger, batch_size=MAX_BATCH, role="enrich", log=print,
                 workers=1):
        if not 1 <= batch_size <= MAX_BATCH:
            raise ValueError(f"batch size must be 1..{MAX_BATCH}")
        self.run_dir, self.client, self.model, self.variant = Path(run_dir), client, model, variant
        self.ledger, self.batch_size, self.role, self.log = ledger, batch_size, role, log
        self.workers = max(1, int(workers))
        self._local = threading.local()
        self._tsha = {}
        self.label_config = label_config_for(model, variant)
        self.db = sqlite3.connect(self.run_dir / "state.sqlite", isolation_level=None)
        self.db.executescript(TABLES)
        self.calls_jsonl = (self.run_dir / "calls.jsonl").open("a", encoding="utf-8")
        self.stats = {"requests": 0, "attempts": 0, "failed_attempts": 0, "retried_reviews": 0,
                      "completed": 0, "cache_hits": 0, "quarantined": 0, "input_tokens": 0, "cost_usd": 0.0}

    # ---------- bookkeeping ----------
    def _check_config(self):
        other = self.db.execute("SELECT DISTINCT label_config FROM results WHERE label_config != ?",
                                (self.label_config,)).fetchall()
        if other:
            sys.exit(f"{self.run_dir} already has results under {other[0][0]}; use a new run dir for a new config")

    def _start_session(self):
        prior = self.db.execute("SELECT COUNT(*) FROM sessions WHERE role=? AND label_config=?",
                                (self.role, self.label_config)).fetchone()[0]
        self.phase = "resume" if prior else "initial"
        cur = self.db.execute("INSERT INTO sessions(role, phase, label_config, started_at) VALUES (?,?,?,?)",
                              (self.role, self.phase, self.label_config, now()))
        self.session_id = cur.lastrowid

    def _log_call(self, res, review_ids, attempt, batch_no, est_cost, started_at):
        cost = self.ledger.settle(est_cost, res.model or self.model, res.input_tokens, res.output_tokens)
        row = {"request_id": res.request_id, "role": self.role, "review_ids": review_ids,
               "model": res.model or self.model, "phase": self.phase,
               "outcome": "succeeded" if res.ok else "failed", "label_config": self.label_config,
               "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
               # extra evidence fields beyond the contract minimum
               "run": self.run_dir.name, "session_id": self.session_id, "batch_no": batch_no, "attempt": attempt,
               "http_status": res.status, "error": res.error or None, "started_at": started_at,
               "seconds": round(res.seconds, 3), "est_cost_usd": est_cost, "cost_usd": cost,
               "cost_is_estimate": res.input_tokens is None}
        self.db.execute(
            "INSERT INTO calls(session_id, request_id, role, phase, review_ids, model, label_config, outcome, "
            "http_status, error, input_tokens, output_tokens, est_cost_usd, cost_usd, cost_is_estimate, attempt, "
            "batch_no, started_at, seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.session_id, row["request_id"], self.role, self.phase, json.dumps(review_ids), row["model"],
             self.label_config, row["outcome"], res.status, res.error or None, res.input_tokens,
             res.output_tokens, est_cost, cost, int(row["cost_is_estimate"]), attempt, batch_no, started_at,
             row["seconds"]))
        self.calls_jsonl.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.calls_jsonl.flush()
        self.stats["attempts"] += 1
        self.stats["failed_attempts"] += not res.ok
        self.stats["input_tokens"] += res.input_tokens or 0
        self.stats["cost_usd"] += cost

    # ---------- one request with bounded transient retries ----------
    def _thread_client(self):
        """Each worker thread gets its own HTTP client when the client supports clone()."""
        if self.workers == 1 or not hasattr(self.client, "clone"):
            return self.client
        if not hasattr(self._local, "client"):
            self._local.client = self.client.clone()
        return self._local.client

    def _attempts(self, items, batch_no):
        """Runs in a worker thread, no database access.
        Returns ([(result, attempt, est_cost, started_at)], BudgetExceeded or None)."""
        state, questions = build_request([t for _, t in items], self.variant)
        est_cost = estimate_tokens(state, questions) * self.ledger.rates.get((self.model, "input_tokens"), 0)
        client, out = self._thread_client(), []
        for attempt in range(1, MAX_TRANSIENT_ATTEMPTS + 1):
            try:
                self.ledger.reserve(est_cost)  # raises before any money is spent
            except BudgetExceeded as e:
                return out, e
            started = now()
            res = client.ask(state, questions)
            if res.ok and res.model and res.model != self.model:
                res.ok, res.error = False, f"model mismatch: asked {self.model}, got {res.model}"
            out.append((res, attempt, est_cost, started))
            if res.ok or not res.transient:
                break
            delay = min(30.0, 1.0 * 2 ** (attempt - 1)) * (1 - random.uniform(0, 0.25))
            self.log(f"  batch {batch_no}: transient failure ({res.status or res.error[:40]}); "
                     f"retry {attempt}/{MAX_TRANSIENT_ATTEMPTS - 1} in {delay:.1f}s")
            time.sleep(delay)
        return out, None

    def _record(self, items, batch_no, out):
        """Main thread: log every attempt; return the final result, or None if transient failures ran out."""
        ids = [rid for rid, _ in items]
        for res, attempt, est, started in out:
            self._log_call(res, ids, attempt, batch_no, est, started)
        if out and (out[-1][0].ok or not out[-1][0].transient):
            return out[-1][0]
        return None

    def _send(self, items, batch_no):
        """Sequential helper used by the verify role."""
        self.stats["requests"] += 1
        out, err = self._attempts(items, batch_no)
        res = self._record(items, batch_no, out)
        if err:
            raise err
        return res

    def _parse(self, items, res):
        """Validate every returned question ID and build records. Returns (valid{id: rec}, invalid{id: reason})."""
        valid, invalid = {}, {}
        for i, (rid, text) in enumerate(items):
            key = review_key(i)
            ans = {f: res.answers.get(f"{key}.{f}") for f in FIELDS}
            missing = [f for f, a in ans.items() if not a]
            if missing:
                invalid[rid] = f"missing answers: {','.join(missing)}"
                continue
            try:
                rec = to_record(text, ans)
            except (KeyError, TypeError, ValueError) as e:
                invalid[rid] = f"malformed answer: {type(e).__name__} {e}"[:200]
                continue
            problems = validate(rec, text)
            if problems:
                invalid[rid] = "; ".join(problems)
            else:
                valid[rid] = rec
        sent = {f"{review_key(i)}.{f}" for i in range(len(items)) for f in FIELDS}
        extra = set(res.answers) - sent
        if extra:  # unexpected IDs are never attached to any review
            self.log(f"  ignoring {len(extra)} unexpected answer IDs")
        return valid, invalid

    def _commit(self, items, valid, invalid, request_id, final_attempt):
        """Atomically save one request's outcome. Returns review IDs that should be retried."""
        retry = []
        ts = now()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for rid, _ in items:
                self.db.execute("UPDATE records SET attempts = attempts + 1 WHERE review_id=?", (rid,))
            for rid, rec in valid.items():
                self.db.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?)",
                                (rid, self.label_config, json.dumps(rec, ensure_ascii=False), None, request_id, ts))
                self.db.execute("UPDATE records SET status='completed', reason=NULL WHERE review_id=?", (rid,))
            for rid, why in invalid.items():
                if final_attempt:
                    self.db.execute("UPDATE records SET status='quarantined', reason=? WHERE review_id=?",
                                    (f"invalid_output_after_retry: {why}", rid))
                else:
                    self.db.execute("UPDATE records SET reason=? WHERE review_id=?", (f"retrying: {why}", rid))
                    retry.append(rid)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        self.stats["completed"] += len(valid)
        self.stats["quarantined"] += len(invalid) if final_attempt else 0
        return retry

    def _propagate_cache(self, tshas=None):
        """Pending rows whose exact text already has a directly-labelled completed original.
        With `tshas`, only those texts are checked (cheap per-batch pass); without, a full pass."""
        where, params = "", [self.label_config]
        if tshas is not None:
            tshas = list(set(tshas))
            if not tshas:
                return 0
            where = f" AND p.text_sha256 IN ({','.join('?' * len(tshas))})"
            params += tshas
        rows = self.db.execute(f"""
            SELECT p.review_id, r.review_id, r.record_json, MIN(o.row_idx) FROM records p
            JOIN records o ON o.text_sha256 = p.text_sha256 AND o.status = 'completed'
            JOIN results r ON r.review_id = o.review_id AND r.label_config = ? AND r.cache_source_id IS NULL
            WHERE p.status = 'pending'{where}
            GROUP BY p.review_id""", params).fetchall()
        if not rows:
            return 0
        ts = now()
        self.db.execute("BEGIN IMMEDIATE")
        for rid, src, rec, _ in rows:
            self.db.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?)",
                            (rid, self.label_config, rec, src, None, ts))
            self.db.execute("UPDATE records SET status='completed', reason=NULL WHERE review_id=?", (rid,))
        self.db.execute("COMMIT")
        self.stats["cache_hits"] += len(rows)
        return len(rows)

    def _work_queue(self):
        seen, queue = set(), []
        for rid, text, tsha in self.db.execute(
                "SELECT review_id, review_text, text_sha256 FROM records WHERE status='pending' ORDER BY row_idx"):
            if tsha not in seen:
                seen.add(tsha)
                queue.append((rid, text))
                self._tsha[rid] = tsha
        return queue

    # ---------- main loop ----------
    def run(self, max_batches=None, max_minutes=None, dry_run=False):
        self._check_config()
        t0 = time.perf_counter()
        if dry_run:
            return self._dry_run()
        self._start_session()
        self._propagate_cache()
        queue = self._work_queue()
        self.log(f"{self.run_dir.name}: {len(queue)} distinct pending texts | phase={self.phase} | "
                 f"{self.label_config} | spent so far ${self.ledger.spent:.4f} of ${self.ledger.cap:.2f} cap")
        stop, batch_no = "all_pending_processed", 0
        retry_jobs = deque()  # (items, batch_no): second attempts after invalid output
        batches = (queue[i:i + self.batch_size] for i in range(0, len(queue), self.batch_size))
        admitting, futures = True, {}
        pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix=self.role)
        try:
            while True:
                # admit work up to the worker limit: retries first, then new batches
                while admitting and len(futures) < self.workers:
                    if retry_jobs:
                        items, b = retry_jobs.popleft()
                        final = True
                    else:
                        if max_batches is not None and batch_no >= max_batches:
                            stop, admitting = f"max_batches={max_batches} reached (deliberate interruption)", False
                            break
                        if max_minutes is not None and time.perf_counter() - t0 > max_minutes * 60:
                            stop, admitting = f"max_minutes={max_minutes} reached", False
                            break
                        items = next(batches, None)
                        if items is None:
                            break
                        batch_no += 1
                        b, final = batch_no, False
                    self.stats["requests"] += 1
                    futures[pool.submit(self._attempts, items, b)] = (items, b, final)
                if not futures:
                    break
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for fut in done:
                    items, b, final = futures.pop(fut)
                    out, err = fut.result()
                    res = self._record(items, b, out)
                    if err is not None:
                        stop, admitting = f"budget stop: {err}", False
                    if res is None:
                        if err is None:
                            stop, admitting = "transient failures exhausted; progress saved, rerun to resume", False
                        continue  # these reviews stay pending for a resume
                    if res.status in (401, 403):
                        stop, admitting = f"authentication error {res.status}", False
                        continue
                    if res.ok:
                        valid, invalid = self._parse(items, res)
                    else:  # request rejected (e.g. 422): retry each review alone to isolate the bad one
                        valid, invalid = {}, {rid: f"request_rejected_{res.status}" for rid, _ in items}
                    retry = self._commit(items, valid, invalid, res.request_id, final_attempt=final)
                    if retry and admitting:
                        self.stats["retried_reviews"] += len(retry)
                        texts = dict(items)
                        if res.ok:
                            retry_jobs.append(([(r, texts[r]) for r in retry], b))
                        else:
                            retry_jobs.extend(([(r, texts[r])], b) for r in retry)
                    self._propagate_cache([self._tsha[rid] for rid, _ in items if rid in self._tsha])
                    if b % 20 == 0 or self.workers == 1 or len(queue) <= 2000:
                        done_n = self.db.execute("SELECT COUNT(*) FROM records WHERE status='completed'").fetchone()[0]
                        self.log(f"  batch {b}{' (retry)' if final else ''}: +{len(valid)} valid, {len(invalid)} "
                                 f"invalid | completed {done_n} | tokens {self.stats['input_tokens']:,} | "
                                 f"${self.stats['cost_usd']:.5f}")
        except KeyboardInterrupt:
            stop, admitting = "interrupted by user (progress saved after last committed batch)", False
            for fut in list(futures):  # save what is already in flight
                items, b, final = futures.pop(fut)
                try:
                    out, _ = fut.result()
                    self._record(items, b, out)
                except Exception:  # noqa: BLE001 - an interrupted request may not return
                    pass
        finally:
            pool.shutdown(wait=True)
        self._propagate_cache()  # full pass: duplicates of texts finished in this session
        return self._finish(stop, time.perf_counter() - t0)

    def _finish(self, stop, wall):
        statuses = dict(self.db.execute("SELECT status, COUNT(*) FROM records GROUP BY status").fetchall())
        summary = {**self.stats, "cost_usd": round(self.stats["cost_usd"], 6), "statuses": statuses,
                   "stop_reason": stop, "wall_seconds": round(wall, 2), "phase": self.phase,
                   "label_config": self.label_config, "batch_size": self.batch_size,
                   "ledger_spent_usd": round(self.ledger.spent, 6), "ledger_cap_usd": self.ledger.cap}
        self.db.execute("UPDATE sessions SET ended_at=?, stop_reason=?, wall_seconds=?, summary_json=? "
                        "WHERE session_id=?", (now(), stop, wall, json.dumps(summary), self.session_id))
        self.calls_jsonl.close()
        self.log(f"stop: {stop}\n{json.dumps(summary, indent=2)}")
        return summary

    def _dry_run(self):
        queue = self._work_queue()
        price = self.ledger.rates.get((self.model, "input_tokens"), 0)
        total = 0
        for s in range(0, len(queue), self.batch_size):
            state, qs = build_request([t for _, t in queue[s:s + self.batch_size]], self.variant)
            total += estimate_tokens(state, qs)
        n = max(len(queue), 1)
        out = {"distinct_pending_texts": len(queue), "requests": -(-len(queue) // self.batch_size),
               "est_input_tokens": total, "est_tokens_per_review": round(total / n, 1),
               "est_cost_usd": round(total * price, 6), "note": f"estimate at {CHARS_PER_TOKEN_EST} chars/token"}
        self.log(json.dumps(out, indent=2))
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--variant", choices=VARIANTS, default="inline_v1")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch-size", type=int, default=MAX_BATCH)
    ap.add_argument("--budget", type=float, help="USD cap across all runs (default: SPEND_CAP_USD or 10)")
    ap.add_argument("--max-batches", type=int, help="stop after N requests (interruption demo)")
    ap.add_argument("--max-minutes", type=float)
    ap.add_argument("--workers", type=int, default=1, help="parallel request workers (start at 1, then 2, 4)")
    ap.add_argument("--dry-run", action="store_true", help="estimate only, no API calls")
    ap.add_argument("--fake", action="store_true", help="offline fake model (free, for tests)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not (args.run_dir / "state.sqlite").exists():
        sys.exit(f"{args.run_dir}/state.sqlite missing: run `python -m pipeline.ingest <csv>` first")
    if args.fake:
        from pipeline.jev import FakeJev
        client, model = FakeJev(), "fake-jev"
    elif args.dry_run:
        client, model = None, args.model
    else:
        from pipeline.jev import JevClient
        client, model = JevClient(args.model), args.model
    Enricher(args.run_dir, client, model, args.variant, Ledger(args.budget), args.batch_size,
             workers=args.workers).run(
        args.max_batches, args.max_minutes, args.dry_run)


if __name__ == "__main__":
    main()
