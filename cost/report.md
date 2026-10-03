# 100-review cost & runtime report

Generated 2026-10-02 21:32 UTC by offline replay (`python -m cost.calculator`). No API key or model call is used to produce this report.

## Measured pilot (real calls on `data/cost_100.csv`)

- Input checksum `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` - matches course manifest: **True**
- Pilot IDs saved: 100; identical to cost_100.csv IDs in order: **True**
- Records: 100 completed, 0 not completed; unique texts 100; result-cache hits 0
- Cold run: empty result cache (fresh run directory), 1 worker. Warm run: same settings, saved results.
- **Wall-clock (measured with a clock): cold 29.93 s, warm 0.14 s**
- **API cost: cold $0.0174, warm (incremental) $0.0000**; warm enrichment calls: **0**
- Cost per 1,000 input rows (cold): $0.1738; per completed record: $0.0002; throughput 3.3 rows/s end-to-end

### By stage (cold run)

| Stage | Provider | Exact model | Effort / settings | Prompt / schema version | Batch | Workers | Requests (attempts / failed) | Reviews sent | Input tok | Output tok | Cost | Stage time (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich | typesafe | jev-1.13.0 | no effort control (Jev); 4 questions/review | jev-1.13.0+enrich_shared_v1+schema_v1 | <=50 | 1 | 2 / 0 | 100 | 30,487 | 20,760 | $0.0013 | 0.57 |
| verify | typesafe | jev-1.13.0 | no effort control (Jev) | jev-1.13.0+verify_v1+schema_v1 | <=50 | 1 | 1 / 0 | 20 | 14,805 | 4,151 | $0.0006 | 0.20 |
| group | anthropic, typesafe | claude-haiku-4-5-20251001, jev-1.13.0 | Jev assign / Haiku discovery: no extended thinking, JSON schema | claude-haiku-4-5+group_discover_v1, jev-1.13.0+group_assign_v1+catalog_df2d778dad | <=50 | 1 | 3 / 0 | 23 | 5,982 | 2,675 | $0.0070 | 13.86 |
| memo | anthropic | claude-haiku-4-5-20251001 | Haiku: no extended thinking, JSON schema, max_tokens 4000 | claude-haiku-4-5+memo_v1 | 1 | 1 | 1 / 0 | 0 | 3,504 | 1,000 | $0.0085 | 15.19 |
| ingest + rank (code) | local | - | - | - | - | 1 | 0 | - | - | - | $0 API (local compute unknown) | 0.11 |

Summed call durations are not wall-clock time; the wall-clock figures above are from a clock around the whole run.

### Rates used (editable: `cost/rates.csv`)

| Model | Item | Price per unit | Currency | Source | Checked |
|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | input_tokens | 0.000001000000 per token | USD | https://platform.claude.com/docs/en/models/overview | 2026-10-02 |
| claude-haiku-4-5-20251001 | output_tokens | 0.000005000000 per token | USD | https://platform.claude.com/docs/en/models/overview | 2026-10-02 |
| jev-1.13.0 | input_tokens | 0.000000042000 per token | USD | https://docs.typesafe.ai/models | 2026-10-02 |
| jev-1.13.0 | output_tokens | 0.000000000000 per token | USD | https://docs.typesafe.ai/models | 2026-10-02 |

Item cost = billed units x price per unit (per-million prices divided by 1,000,000). Input and output are mutually exclusive items; Jev bills input only (output price 0); no cached-input or batch tier was used. Per-call lines: `cost/cost_lines.csv`; raw usage: `cost/usage.csv`.

Local compute: Pipeline code runs on a Windows laptop. Electricity and hardware time are not metered: reported as unknown, not zero.

## Full-run projection (estimates, not measurements)

Per-unit usage source: **checkpoint_500** (refreshed from a larger run). Projected rows: 660,622 (all source rows); 660,609 nonempty classifications and 13 empty-text quarantines at the course volume; exact-text reuse leaves 484,189 distinct texts for first-pass enrichment. Fixed overhead (memo, issue discovery) is counted once, never per review.

Controls: budget **$10.00**, max workers **1**, Claude output cap **4000** tokens, max fallback fraction **0.0** (No stronger-model fallback is used; invalid outputs are retried once then quarantined.)

| Scenario | Reuse | Enrich | Verify | Group assign | Fixed (memo, discovery) | **Total** | Est. time | Budget check |
|---|---|---|---|---|---|---|---|---|
| base | with exact text reuse | $6.27 | $0.3075 | $0.9719 | $0.0105 | **$7.56** | 0.70 h | within budget |
| base | no reuse | $8.55 | $0.4196 | $1.33 | $0.0105 | **$10.31** | 0.95 h | **OVER BUDGET** |
| conservative | with exact text reuse | $7.49 | $0.7353 | $1.16 | $0.0211 | **$9.41** | 1.06 h | within budget |
| conservative | no reuse | $10.22 | $1.00 | $1.59 | $0.0211 | **$12.83** | 1.45 h | **OVER BUDGET** |

Assumptions: base = retry 1%, verify 2%; conservative = retry 5%, +15% tokens, verify 4%, memo x2, +50% time. Time = requests x measured seconds per request / workers.

Per-unit measurements used:

```json
{
  "run": "pilot_cost_100",
  "records_completed": 100,
  "direct_labelled": 100,
  "negative_share": 0.474,
  "jev_assign_share": 0.7172995780590717,
  "enrich": {
    "tokens_per_review": 305.19415448851777,
    "sec_per_request": 0.2129,
    "attempts": 10,
    "model": "jev-1.13.0"
  },
  "verify": {
    "tokens_per_review": 748.55,
    "sec_per_request": 0.16,
    "model": "jev-1.13.0"
  },
  "group_assign": {
    "tokens_per_review": 139.1764705882353,
    "sec_per_request": 0.12266666666666666,
    "model": "jev-1.13.0"
  },
  "group_discovery": {
    "input_tokens": 8268,
    "output_tokens": 2977,
    "seconds": 44.888,
    "model": "claude-haiku-4-5-20251001"
  },
  "memo": {
    "input_tokens": 14645,
    "output_tokens": 5498,
    "seconds": 59.215,
    "attempts": 4,
    "model": "claude-haiku-4-5-20251001"
  },
  "source": "checkpoint_500"
}
```
