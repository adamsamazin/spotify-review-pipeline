# Output schema

Exported records follow `data/GRADING_CONTRACT.md` (`grading/records.jsonl.gz`). Validation lives in
[`pipeline/schema.py`](../pipeline/schema.py); a record that fails validation is retried once, then quarantined.

## Completed record (one per source `review_id`)

| Field | Type | Rule / source |
|---|---|---|
| `review_id` | string | original source ID, never changed |
| `source_sha256` | string | SHA-256 of compact UTF-8 JSON of the six source fields (course `row_sha` helper) |
| `status` | `"completed"` | |
| `topic` | one of `access, usability, playback, downloads, catalog, billing, support, other` | Jev Choice |
| `intent` | one of `cancellation, complaint, request, praise, unclear` (precedence order) | Jev Choice |
| `sentiment` | number in [-1, 1] | Jev Score on 5 levels; `score / 2 - 1` |
| `severity` | integer 1-5 | Jev Choice, then code rules: praise/request/unclear → 1; complaint → at least 2 |
| `entities` | list of strings | feature terms matched in code (lexicon in `pipeline/schema.py`); each appears in the text |
| `evidence_quote` | string | exact substring: full text if ≤ 280 chars, else the sentence with the most topic terms |
| `needs_review` | boolean | true when the top option for topic, intent or severity has probability < 0.60 |
| `label_config` | string | `jev-1.13.0+enrich_shared_v1+schema_v1` (model + prompt + schema) |
| `cache_source_id` | string, optional | present only on exact-duplicate texts; points to the directly labelled original |

Internal copies (`runs/<run>/state.sqlite`, `results/`) also keep `detail`: per-option probabilities, confidence,
raw sentiment score, low-confidence fields, rules applied, and `post_version`.

## Quarantined record

`review_id`, `source_sha256`, `status: "quarantined"`, `reason` (`empty_review_text`, or
`invalid_output_after_retry: …` / `request_rejected_…`), `attempts`. Full run: 13 records, all `empty_review_text`
([results/full/quarantine.jsonl](../results/full/quarantine.jsonl)).

## Call log entry (`grading/calls.jsonl.gz`)

`request_id`, `role` (`enrich | verify | group | memo`), `review_ids` (IDs actually sent; ≤ 50 for enrich), `model`,
`phase` (`initial | resume`), `outcome` (`succeeded | failed`), `label_config`, `input_tokens`, `output_tokens`,
plus `batch_no`, `attempt`, `http_status`, `error`, `started_at`, `seconds`, `cost_usd`, `cost_is_estimate`.

## Issue outputs

`grading/membership.csv`: `issue_id,review_id` (one issue per complaint/cancellation). `grading/ranking.csv`:
`rank,issue_id,complaint_count,severity_sum,mean_severity,priority_score`. `grading/claims.csv`:
`claim_id,issue_id,metric,value`.
