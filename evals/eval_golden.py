"""Compare a run's predictions with the human-labeled golden 50. Offline; no model calls.

    .venv\\Scripts\\python -m evals.eval_golden runs/probe_golden_shared [runs/probe_golden_inline ...]

Writes evals/results/golden_<run>.json and .md (per-field metrics, confusion tables, every disagreement).
Golden labels are only read here, after prediction; they never enter prompts or examples.
"""

import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from pipeline.contract import ROOT, TOPICS, INTENT_PRECEDENCE

GOLD = ROOT / "evals" / "golden_50_labeled.csv"
OUT = ROOT / "evals" / "results"
SENTIMENT_TOLERANCE = 0.5  # predeclared: within one step of the 5-level scale counts as agreement


def load_gold():
    with GOLD.open(encoding="utf-8", newline="") as f:
        return {r["review_id"]: r for r in csv.DictReader(f)}


def load_preds(run_dir):
    db = sqlite3.connect(Path(run_dir) / "state.sqlite")
    rows = db.execute("SELECT r.review_id, r.status, r.reason, s.record_json, s.label_config FROM records r "
                      "LEFT JOIN results s USING(review_id)").fetchall()
    return {rid: {"status": st, "reason": why, "label_config": lc, **(json.loads(rec) if rec else {})}
            for rid, st, why, rec, lc in rows}


def confusion(pairs, labels):
    m = {g: Counter() for g in labels}
    for g, p in pairs:
        m.setdefault(g, Counter())[p] += 1
    return {g: dict(c) for g, c in m.items() if c}


def evaluate(run_dir):
    gold, preds = load_gold(), load_preds(run_dir)
    n = len(gold)
    cases, topic_pairs, intent_pairs = [], [], []
    agree = Counter()
    sev_err, sent_err = [], []
    for rid, g in gold.items():
        p = preds.get(rid, {})
        ok = p.get("status") == "completed"  # missing/quarantined predictions count as wrong
        c = {"review_id": rid, "text": g["review_text"], "status": p.get("status", "missing"),
             "ambiguous": g.get("ambiguous") == "true", "gold_needs_review": g["needs_review"] == "true"}
        for f in ("topic", "intent", "severity", "sentiment", "needs_review"):
            c[f"gold_{f}"], c[f"pred_{f}"] = g[f], p.get(f)
        if ok:
            topic_pairs.append((g["topic"], p["topic"]))
            intent_pairs.append((g["intent"], p["intent"]))
            agree["topic"] += g["topic"] == p["topic"]
            agree["intent"] += g["intent"] == p["intent"]
            agree["severity_exact"] += int(g["severity"]) == p["severity"]
            agree["sentiment_within_tol"] += abs(float(g["sentiment"]) - p["sentiment"]) <= SENTIMENT_TOLERANCE
            agree["quote_exact_substring"] += p["evidence_quote"] in g["review_text"]
            sev_err.append(abs(int(g["severity"]) - p["severity"]))
            sent_err.append(abs(float(g["sentiment"]) - p["sentiment"]))
            c["errors"] = [f for f in ("topic", "intent") if g[f] != p[f]] + \
                (["severity"] if int(g["severity"]) != p["severity"] else []) + \
                (["sentiment"] if abs(float(g["sentiment"]) - p["sentiment"]) > SENTIMENT_TOLERANCE else [])
            c["rules_applied"] = p.get("detail", {}).get("rules_applied", [])
            c["low_confidence_fields"] = p.get("detail", {}).get("low_confidence_fields", [])
        else:
            c["errors"] = ["not_completed"]
        cases.append(c)

    completed = [c for c in cases if c["status"] == "completed"]
    # needs_review evaluated as a prediction of "this record has a topic/intent/severity error"
    flagged = [c for c in completed if c["pred_needs_review"]]
    wrong = [c for c in completed if set(c["errors"]) & {"topic", "intent", "severity"}]
    tp = len([c for c in flagged if c in wrong])
    labels_cfg = {p.get("label_config") for p in preds.values() if p.get("label_config")}
    res = {
        "run": Path(run_dir).name, "label_config": sorted(labels_cfg), "n_gold": n,
        "completed": len(completed), "ambiguous_cases": sum(c["ambiguous"] for c in cases),
        "agreement": {k: round(agree[k] / n, 3) for k in
                      ("topic", "intent", "severity_exact", "sentiment_within_tol", "quote_exact_substring")},
        "agreement_excluding_ambiguous": {
            f: round(sum(1 for c in cases if not c["ambiguous"] and c["status"] == "completed" and f not in c["errors"])
                     / max(1, sum(1 for c in cases if not c["ambiguous"])), 3)
            for f in ("topic", "intent", "severity", "sentiment")},
        "severity_mae": round(sum(sev_err) / len(sev_err), 3) if sev_err else None,
        "sentiment_mae": round(sum(sent_err) / len(sent_err), 3) if sent_err else None,
        "sentiment_tolerance": SENTIMENT_TOLERANCE,
        "needs_review_as_error_predictor": {"flagged": len(flagged), "records_with_label_errors": len(wrong),
                                            "precision": round(tp / len(flagged), 3) if flagged else None,
                                            "recall": round(tp / len(wrong), 3) if wrong else None},
        "per_topic_counts": {"gold": dict(Counter(g for g, _ in topic_pairs)),
                             "pred": dict(Counter(p for _, p in topic_pairs))},
        "confusion_topic": confusion(topic_pairs, TOPICS),
        "confusion_intent": confusion(intent_pairs, INTENT_PRECEDENCE),
        "cases": cases,
    }
    return res


def to_md(r):
    a = r["agreement"]
    lines = [f"# Golden-50 evaluation: `{r['run']}`", "", f"label_config: `{', '.join(r['label_config'])}`", "",
             f"Completed {r['completed']}/{r['n_gold']}; ambiguous (human-marked) {r['ambiguous_cases']}.", "",
             "| Metric | Value |", "|---|---|",
             f"| Topic agreement | {a['topic']:.0%} |", f"| Intent agreement | {a['intent']:.0%} |",
             f"| Severity exact | {a['severity_exact']:.0%} |", f"| Severity MAE | {r['severity_mae']} |",
             f"| Sentiment within ±{r['sentiment_tolerance']} | {a['sentiment_within_tol']:.0%} |",
             f"| Sentiment MAE | {r['sentiment_mae']} |",
             f"| Evidence quote exact substring | {a['quote_exact_substring']:.0%} |", "",
             "Excluding ambiguous cases: " + ", ".join(f"{k} {v:.0%}" for k, v in
                                                       r["agreement_excluding_ambiguous"].items()), "",
             f"needs_review as an error predictor: {r['needs_review_as_error_predictor']}", "",
             "## Disagreements", "", "| # | text | field | gold | pred | amb |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(r["cases"], 1):
        for f in c["errors"]:
            if f == "not_completed":
                lines.append(f"| {i} | {c['text'][:70]} | status | completed | {c['status']} | |")
                continue
            t = c["text"][:70].replace("|", "/").replace("\n", " ")
            lines.append(f"| {i} | {t} | {f} | {c['gold_' + f]} | {c['pred_' + f]} | {'y' if c['ambiguous'] else ''} |")
    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    for run in sys.argv[1:]:
        r = evaluate(run)
        (OUT / f"golden_{r['run']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        (OUT / f"golden_{r['run']}.md").write_text(to_md(r), encoding="utf-8")
        print(f"{r['run']}: topic {r['agreement']['topic']:.0%} | intent {r['agreement']['intent']:.0%} | "
              f"severity exact {r['agreement']['severity_exact']:.0%} (MAE {r['severity_mae']}) | "
              f"sentiment ±0.5 {r['agreement']['sentiment_within_tol']:.0%} (MAE {r['sentiment_mae']}) | "
              f"quotes {r['agreement']['quote_exact_substring']:.0%} | "
              f"excl. ambiguous {r['agreement_excluding_ambiguous']}")


if __name__ == "__main__":
    main()
