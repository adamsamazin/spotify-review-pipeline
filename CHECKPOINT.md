> **Historical document (Class 7 checkpoint, 2026-10-02).** Numbers below are development results from the 100/500-review runs and are superseded by the final full-corpus run. For final results, evidence and costs see [README.md](README.md).

# Class 7 checkpoint (prepared 2026-10-02)

Status of the three checkpoint tasks, using real runs only. Development results, not the final
full-corpus run. Total real API spend so far across all runs: **$0.138** (Jev $0.022, Anthropic $0.115)
against a code-enforced cap of $10.

## 1. Topics, severity rubric, golden labels

- **Topics:** the 8 contract topics (`access`, `usability`, `playback`, `downloads`, `catalog`, `billing`,
  `support`, `other`). Severity: the shared 1-5 scale. Intents: cancellation > complaint > request > praise > unclear.
  Definitions, boundaries and 13 worked examples from development data: [prompts/labels.md](prompts/labels.md).
  What Jev actually receives: [pipeline/questions.py](pipeline/questions.py).
- **Golden 50:** hand-labeled by me in [evals/golden_50_labeled.csv](evals/golden_50_labeled.csv) with an
  ambiguity flag and notes (13 marked ambiguous). An assistant checked the labels against the contract rules
  only. I revised 6 labels where my severity contradicted the contract's definition. Golden labels never
  enter prompts or examples.

## 2. Enrichment (500 reviews) with IDs preserved, validation, retry-once, quarantine

Run: `python -m pipeline.run data/checkpoint_500.csv --run checkpoint_500 --label official`

| | Result |
|---|---|
| Records | 500/500 completed, 0 quarantined, 0 pending; every source `review_id` and row hash preserved |
| Requests | 10 enrichment requests of <= 50 reviews; 0 failed attempts, 0 retries needed |
| Exact-text reuse | 479 distinct texts sent; 21 duplicates reuse a validated result via `cache_source_id` |
| Validation | Every returned question ID checked against what was sent; labels, ranges, quote substring checked in code |
| Consistency rules | 6 records adjusted by code (praise/request/unclear → severity 1; complaint → at least 2), recorded per record |
| `needs_review` | 17.8% flagged (top option below 0.60; cutoff chosen on this development data, not on the golden set) |

Failure paths were rehearsed for free with a fake model ([evals/test_controls.py](evals/test_controls.py),
results in [evals/results/test_controls.json](evals/results/test_controls.json)): overload → backoff → success;
malformed answer → retried once → success; invalid twice → quarantined with reason and attempt count; missing
answer ID detected; interrupt then resume with no completed ID re-sent; spend cap stops the run before paying.

## 3. Label agreement, failures and cost

### Agreement with the golden 50 (enrichment config `jev-1.13.0+enrich_shared_v1+schema_v1`)

| Field | Agreement | Excluding 13 ambiguous |
|---|---|---|
| Topic | 78% | 86% |
| Intent | 88% | 94% |
| Severity exact (MAE) | 78% (0.28) | 83% |
| Sentiment within ±0.5 (MAE) | 94% (0.133) | 100% |
| Evidence quote is an exact substring | 100% | |

Full per-case table: [evals/results/golden_probe_golden_shared.md](evals/results/golden_probe_golden_shared.md).
Disclosure: the golden set was used once to choose between two question designs (`inline_v1` vs `shared_v1`).
They tied on topic and intent, and inline was 4 points better on severity at 2.4x the cost (projected $14.60 vs
$6.20 full run). No prompt wording was tuned on individual golden disagreements. Fifty cases are a small
diagnostic sample, not a population accuracy estimate.

### Independent verification and inspected failures

The verifier ([pipeline/verify.py](pipeline/verify.py)) is a separate Jev task with its own wording; it sees
only the review text. On a seeded 20-review sample it disagreed on 5 (25%): topic 10%, severity 15%, intent 0%.

| Review (excerpt) | Enricher | Verifier | My read |
|---|---|---|---|
| "...moving storage failed and deleted everything" | downloads, sev 3 | sev 5 | **Verifier right**: explicit data loss is severity 5 |
| "...removing Collab streams from only BTS..." | catalog, sev 2 | sev 3 | Borderline: content removed, rest of app works |
| "...in some songs there is no lyrics..." | catalog, sev 3 | sev 2 | Borderline: lyrics missing for some songs |
| "Absolutely convenient and easy to use with great features" | other | usability | Verifier arguably right: "easy to use" is a specific praised feature |
| "I can enjoy the music I choose." | other | usability | Enricher arguably right: general praise |

Planted-error test: on a separate copy, 10 enriched records had their topic deliberately changed; the verifier
flagged **10/10**. The copy is synthetic and excluded from business results.

Other failures found and handled:
- **Memo numbers (Haiku):** the first memos rounded means (2.94 for 2.941176) and stated numbers without claim
  tags; code validation rejected them, so no invalid memo was published. Fix: the model now writes only claim
  tags and code inserts exact values (`memo_v3`). The memo role moved to Sonnet 5.5 after a Haiku memo
  contradicted itself; Sonnet's memo passed every check on the first attempt.
- **Issue catalog boundaries:** discovery proposed two overlapping billing issues and filed connection errors
  under `access`. The catalog from the 10,000-review run will be reviewed and accepted by a person, then reused.
- **Projection bug:** the calculator first scaled group-assignment cost by all complaints rather than the 72%
  actually sent to Jev; fixed and replayed offline.

### Cost

| | Measured |
|---|---|
| 100-review pilot, cold (all 6 stages, empty cache, 1 worker) | **$0.0174, 29.9 s wall-clock**, 7 calls, 0 failed |
| 100-review pilot, warm (same settings, saved results) | **$0.0000, 0.14 s, 0 calls** in every stage |
| 500-review run, all stages | enrich $0.006, verify $0.001, group $0.024, memo $0.035 (Sonnet) |

Full-run projection (offline replay, per-unit rates refreshed from the 500 run): **base $7.56, conservative
$9.41** with exact-text reuse; $10.31 / $12.83 without reuse (over budget, so reuse is required). About 0.7-1.1
hours at one worker. Report and formulas: [cost/report.md](cost/report.md); replay with
`python -m cost.calculator` (no API key needed).

## Who chooses the next step, and when the run stops

**Code chooses; models only judge language inside bounded tasks.** The orchestrator
([pipeline/run.py](pipeline/run.py)) runs a fixed sequence: ingest → enrich → verify → group → rank → memo.
It decides which records are pending, batches them (<= 50), validates every answer, retries, quarantines, and
moves to the next stage. Models never pick the next step, see the budget, or change the taxonomy:

- Jev answers fixed multiple-choice questions (topic, intent, severity, sentiment; verifier labels; issue assignment).
- Claude Haiku proposes issue names once from a bounded set of examples; code validates and saves the catalog.
- Claude Sonnet 5.5 writes the memo from saved aggregates; code checks every claim and number.
- A person accepts the issue catalog and checks the memo's argument.

**The run stops when any of these happens** (progress is committed after every request, so a rerun resumes):
1. All records are completed or quarantined (normal end).
2. The next request's reserved worst-case cost would push total spend across all runs past the cap ($10).
3. A request still fails after bounded backoff (4 attempts for overload/timeouts) - the run stops rather than loop.
4. An authentication error (401/403).
5. A deliberate limit: `--max-batches` (used for the interruption demo) or `--max-minutes`.
6. Downstream stages do not start while any record is still pending.

Per-record stops: invalid output is retried once, then the record is quarantined with the reason and attempt count.

## Plan for Class 7 and after

- **In class:** run `analysis_10000.csv` through all stages; review and accept its issue catalog; refresh the
  projection; review the memo draft.
- **After class:** top up Jev (~$5-6), freeze the configuration, re-run the 100-review pilot on the final
  configuration, run the full corpus with a recorded interruption/resume, export `grading/`, pass
  `check_submission.py`, finish the README and memo, publish by 10/11 (due 10/13).
