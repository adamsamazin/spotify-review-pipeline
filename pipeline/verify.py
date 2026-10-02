"""Stage 3 - Verify (role: verify). A separate Jev task re-labels a declared random sample.

    python -m pipeline.verify runs/checkpoint_500 [--fraction 0.02 --min 20]

The verifier gets only the original review text and its own rubric wording (verify_v1); it
never sees the enricher's labels. Code compares the two and writes a disagreement report.
A planted-error test copies some enriched records, deliberately changes their topic, and
checks that comparing them with the verifier's labels flags every planted error. The planted
copy is synthetic test data and never touches business results.
"""

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

from pipeline.budget import BudgetExceeded, Ledger
from pipeline.contract import ROOT, TOPICS
from pipeline.enrich import DEFAULT_MODEL, Enricher, now
from pipeline.questions import FIELDS, VERIFY_VARIANT, review_key
from pipeline.schema import to_record

SAMPLE_SEED = "a5-verify-v1"
SENTIMENT_TOLERANCE = 0.5


class Verifier(Enricher):
    def __init__(self, run_dir, client, model, ledger, batch_size=50, log=print):
        super().__init__(run_dir, client, model, VERIFY_VARIANT, ledger, batch_size, role="verify", log=log)
        self.label_config = f"{model}+{VERIFY_VARIANT}+schema_v1"
        self.out = self.run_dir / "verify"
        self.out.mkdir(exist_ok=True)

    def sample(self, fraction, minimum):
        """Declared sample: completed records labelled directly (not cache copies), ordered by
        sha256(seed:review_id). Deterministic, so a rerun picks the same IDs."""
        rows = self.db.execute(
            "SELECT r.review_id, r.review_text FROM records r JOIN results s USING(review_id) "
            "WHERE r.status='completed' AND s.cache_source_id IS NULL").fetchall()
        rows.sort(key=lambda r: hashlib.sha256(f"{SAMPLE_SEED}:{r[0]}".encode()).hexdigest())
        n = min(len(rows), max(minimum, math.ceil(fraction * len(rows))))
        return rows[:n]

    def run_verify(self, fraction=0.02, minimum=20, planted=10):
        sample = self.sample(fraction, minimum)
        pred_path = self.out / "verifier_predictions.jsonl"
        done = {}
        if pred_path.exists():  # resume / warm run: never re-pay for verified IDs under this config
            for line in pred_path.open(encoding="utf-8"):
                p = json.loads(line)
                if p["label_config"] == self.label_config:
                    done[p["review_id"]] = p
        todo = [(rid, t) for rid, t in sample if rid not in done]
        self.phase = "initial"
        cur = self.db.execute("INSERT INTO sessions(role, phase, label_config, started_at) VALUES (?,?,?,?)",
                              ("verify", self.phase, self.label_config, now()))
        self.session_id = cur.lastrowid
        self.log(f"verify: sample {len(sample)} ({fraction:.1%}, min {minimum}); {len(todo)} need new calls")
        stop = "complete"
        with pred_path.open("a", encoding="utf-8") as f:
            try:
                for b, start in enumerate(range(0, len(todo), self.batch_size), 1):
                    items = todo[start:start + self.batch_size]
                    res = self._send(items, b)
                    if res is None or not res.ok:
                        stop = f"verifier call failed: {res.error if res else 'transient failures exhausted'}"
                        break
                    for i, (rid, text) in enumerate(items):
                        ans = {fl: res.answers.get(f"{review_key(i)}.{fl}") for fl in FIELDS}
                        if not all(ans.values()):
                            continue  # unverified IDs stay out; reported as missing below
                        rec = to_record(text, ans)
                        p = {"review_id": rid, "label_config": self.label_config, "request_id": res.request_id,
                             **{k: rec[k] for k in ("topic", "intent", "severity", "sentiment")},
                             "probabilities": rec["detail"]["probabilities"]}
                        done[rid] = p
                        f.write(json.dumps(p) + "\n")
                    f.flush()
            except BudgetExceeded as e:
                stop = f"budget stop: {e}"
        report = self.compare([rid for rid, _ in sample], done, planted)
        report.update({"stop_reason": stop, "label_config": self.label_config, "sample_seed": SAMPLE_SEED,
                       "fraction": fraction, "minimum": minimum, "calls": self.stats["attempts"],
                       "cost_usd": round(self.stats["cost_usd"], 6)})
        (self.out / "disagreements.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self.db.execute("UPDATE sessions SET ended_at=?, stop_reason=?, summary_json=? WHERE session_id=?",
                        (now(), stop, json.dumps({k: v for k, v in report.items() if k != "cases"}), self.session_id))
        self.calls_jsonl.close()
        self.log(f"verify: {json.dumps({k: v for k, v in report.items() if k not in ('cases', 'planted_test')})}")
        self.log(f"planted-error test: {report['planted_test']['summary']}")
        return report

    def _enriched(self, ids):
        q = ",".join("?" * len(ids))
        return {rid: json.loads(rec) for rid, rec in self.db.execute(
            f"SELECT review_id, record_json FROM results WHERE review_id IN ({q})", ids)}

    def compare(self, sample_ids, verified, planted):
        enriched = self._enriched(sample_ids)
        cases, dis = [], Counter()
        for rid in sample_ids:
            v, e = verified.get(rid), enriched.get(rid)
            if not v or not e:
                continue
            diff = [f for f in ("topic", "intent", "severity") if v[f] != e[f]]
            if abs(v["sentiment"] - e["sentiment"]) > SENTIMENT_TOLERANCE:
                diff.append("sentiment")
            dis.update(diff)
            if diff:
                cases.append({"review_id": rid, "fields": diff,
                              "enriched": {f: e[f] for f in ("topic", "intent", "severity", "sentiment")},
                              "verifier": {f: v[f] for f in ("topic", "intent", "severity", "sentiment")}})
        n = sum(1 for r in sample_ids if r in verified and r in enriched)
        # Planted-error test on a separate copy: change the topic of the first `planted` verified records.
        planted_rows = []
        for rid in [r for r in sample_ids if r in verified and r in enriched][:planted]:
            true_topic = enriched[rid]["topic"]
            # chosen without looking at the verifier's answer, so a miss is possible and would be reported
            wrong = TOPICS[(TOPICS.index(true_topic) + 1) % len(TOPICS)]
            planted_rows.append({"review_id": rid, "synthetic": True, "original_topic": true_topic,
                                 "planted_topic": wrong, "verifier_topic": verified[rid]["topic"],
                                 "flagged": verified[rid]["topic"] != wrong})
        (self.out / "planted_test_copy.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in planted_rows), encoding="utf-8")
        caught = sum(r["flagged"] for r in planted_rows)
        return {"sample_size": len(sample_ids), "verified": n, "missing": len(sample_ids) - n,
                "disagreement_rate": {f: round(dis[f] / n, 3) if n else None
                                      for f in ("topic", "intent", "severity", "sentiment")},
                "any_field_disagreement_rate": round(len(cases) / n, 3) if n else None,
                "planted_test": {"planted": len(planted_rows), "flagged": caught,
                                 "summary": f"{caught}/{len(planted_rows)} planted wrong topics flagged"},
                "cases": cases}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--fraction", type=float, default=0.02)
    ap.add_argument("--min", type=int, default=20)
    ap.add_argument("--planted", type=int, default=10)
    ap.add_argument("--budget", type=float)
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if args.fake:
        from pipeline.jev import FakeJev
        client, model = FakeJev(), "fake-jev"
    else:
        from pipeline.jev import JevClient
        client, model = JevClient(DEFAULT_MODEL), DEFAULT_MODEL
    Verifier(args.run_dir, client, model, Ledger(args.budget)).run_verify(args.fraction, args.min, args.planted)


if __name__ == "__main__":
    main()
