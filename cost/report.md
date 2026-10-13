# 100-review cost & runtime report

Generated 2026-10-13 00:16 UTC by offline replay (`python -m cost.calculator`). No API key or model call is used to produce this report.

## Measured pilot (real calls on `data/cost_100.csv`)

- Input checksum `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` - matches course manifest: **True**
- Pilot IDs saved: 100; identical to cost_100.csv IDs in order: **True**
- Records: 100 completed, 0 not completed; unique texts 100; result-cache hits 0
- Cold run: empty result cache (fresh run directory), 1 worker. Warm run: same settings, saved results.
- **Wall-clock (measured with a clock): cold 24.25 s, warm 0.12 s**
- **API cost: cold $0.0429, warm (incremental) $0.0000**; warm enrichment calls: **0**
- Cost per 1,000 input rows (cold): $0.4293; per completed record: $0.0004; throughput 4.1 rows/s end-to-end

### By stage (cold run)

| Stage | Provider | Exact model | Effort / settings | Prompt / schema version | Batch | Workers | Requests (attempts / failed) | Reviews sent | Input tok | Output tok | Cost | Stage time (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich | typesafe | jev-1.13.0 | no effort control (Jev); 4 questions/review | jev-1.13.0+enrich_shared_v1+schema_v1 | <=50 | 1 | 2 / 0 | 100 | 30,487 | 20,762 | $0.0013 | 0.56 |
| verify | typesafe | jev-1.13.0 | no effort control (Jev) | jev-1.13.0+verify_v1+schema_v1 | <=50 | 1 | 1 / 0 | 20 | 14,805 | 4,151 | $0.0006 | 0.18 |
| group | typesafe | jev-1.13.0 | Jev assign / Haiku discovery: no extended thinking, JSON schema | jev-1.13.0+group_assign_v1+catalog_b4a33aea9b | <=50 | 1 | 7 / 0 | 39 | 7,432 | 3,015 | $0.0003 | 0.74 |
| memo | anthropic | claude-sonnet-5-5 | per model in this column (Sonnet 5.5: adaptive thinking, effort high, max_tokens 16000; earlier Haiku runs: no thinking, max_tokens 4000); JSON schema | claude-sonnet-5-5+memo_v3 | 1 | 1 | 1 / 0 | 0 | 4,291 | 3,213 | $0.0407 | 22.68 |
| ingest + rank (code) | local | - | - | - | - | 1 | 0 | - | - | - | $0 API (local compute unknown) | 0.09 |

Summed call durations are not wall-clock time; the wall-clock figures above are from a clock around the whole run.

### Rates used (editable: `cost/rates.csv`)

| Model | Item | Price per unit | Currency | Source | Checked |
|---|---|---|---|---|---|
| claude-sonnet-5-5 | input_tokens | 0.000002000000 per token | USD | https://platform.claude.com/docs/en/models/overview | 2026-10-02 |
| claude-sonnet-5-5 | output_tokens | 0.000010000000 per token | USD | https://platform.claude.com/docs/en/models/overview | 2026-10-02 |
| jev-1.13.0 | input_tokens | 0.000000042000 per token | USD | https://docs.typesafe.ai/models | 2026-10-02 |
| jev-1.13.0 | output_tokens | 0.000000000000 per token | USD | https://docs.typesafe.ai/models | 2026-10-02 |

Item cost = billed units x price per unit (per-million prices divided by 1,000,000). Input and output are mutually exclusive items; Jev bills input only (output price 0); no cached-input or batch tier was used. Per-call lines: `cost/cost_lines.csv`; raw usage: `cost/usage.csv`.

Local compute: Pipeline code runs on a Windows laptop. Electricity and hardware time are not metered: reported as unknown, not zero.

### Reconciliation with provider dashboards

Provider-reported usage compared with our call logs (scope may cover all runs that day, not only the pilot). Screenshots are in `cost/reconciliation/`.

| Checked | Provider | Scope | Metric | Provider dashboard | Our logs | Difference | Screenshot |
|---|---|---|---|---|---|---|---|
| 2026-10-02 | anthropic | all real calls on 2026-10-02 (API key spotify-pipeline) | input_tokens | 33183 | 33183 | 0 | [2026-10-02_anthropic_usage.png](reconciliation/2026-10-02_anthropic_usage.png) |
| 2026-10-02 | anthropic | all real calls on 2026-10-02 (API key spotify-pipeline) | output_tokens | 12954 | 12954 | 0 | [2026-10-02_anthropic_usage.png](reconciliation/2026-10-02_anthropic_usage.png) |
| 2026-10-02 | anthropic | claude-haiku-4-5 on 2026-10-02 | total_tokens | 39077 | 39077 | 0 | [2026-10-02_anthropic_usage.png](reconciliation/2026-10-02_anthropic_usage.png) |
| 2026-10-02 | anthropic | claude-sonnet-5-5 on 2026-10-02 | total_tokens | 7060 | 7060 | 0 | [2026-10-02_anthropic_usage.png](reconciliation/2026-10-02_anthropic_usage.png) |
| 2026-10-02 | anthropic | claude-haiku-4-5 on 2026-10-02 | cost_usd | 0.08 | 0.0806 | within rounding | [2026-10-02_anthropic_cost.png](reconciliation/2026-10-02_anthropic_cost.png) |
| 2026-10-02 | anthropic | claude-sonnet-5-5 on 2026-10-02 | cost_usd | 0.03 | 0.0347 | within rounding | [2026-10-02_anthropic_cost.png](reconciliation/2026-10-02_anthropic_cost.png) |
| 2026-10-02 | anthropic | all real calls on 2026-10-02 (API key spotify-pipeline) | cost_usd | 0.12 | 0.1153 | within rounding | [2026-10-02_anthropic_cost.png](reconciliation/2026-10-02_anthropic_cost.png) |
| 2026-10-02 | typesafe | all real calls in the last 24 h to 2026-10-02 (all traffic) | requests | 38 | 38 | 0 | [2026-10-02_typesafe_usage.webp](reconciliation/2026-10-02_typesafe_usage.webp) |
| 2026-10-02 | typesafe | all real calls in the last 24 h to 2026-10-02 (all traffic) | total_tokens | 837789 | 837789 | 0 | [2026-10-02_typesafe_usage.webp](reconciliation/2026-10-02_typesafe_usage.webp) |
| 2026-10-02 | typesafe | all real calls in the last 24 h to 2026-10-02 (all traffic) | cost_usd | 0.0224 | 0.0224 | 0 | [2026-10-02_typesafe_usage.webp](reconciliation/2026-10-02_typesafe_usage.webp) |
| 2026-10-02 | typesafe | account balance | balance_usd | 5.00 | 4.9776 expected | not yet deducted | [2026-10-02_typesafe_usage.webp](reconciliation/2026-10-02_typesafe_usage.webp) |
| 2026-10-13 | typesafe | all real calls in the last 30 days (all runs incl. full corpus) | requests | 13988 | 13988 | 0 | [2026-10-12_typesafe_usage_full_run.webp](reconciliation/2026-10-12_typesafe_usage_full_run.webp) |
| 2026-10-13 | typesafe | all real calls in the last 30 days (all runs incl. full corpus) | total_tokens | 300714724 | 300714724 | 0 | [2026-10-12_typesafe_usage_full_run.webp](reconciliation/2026-10-12_typesafe_usage_full_run.webp) |
| 2026-10-13 | typesafe | all real calls in the last 30 days (all runs incl. full corpus) | cost_usd | 7.64 | 7.6407 | within rounding | [2026-10-12_typesafe_usage_full_run.webp](reconciliation/2026-10-12_typesafe_usage_full_run.webp) |
| 2026-10-13 | typesafe | account balance | balance_usd | 3.35 | 3.36 expected (5 + 6 top-up - 7.64) | within rounding | [2026-10-12_typesafe_usage_full_run.webp](reconciliation/2026-10-12_typesafe_usage_full_run.webp) |
| 2026-10-13 | anthropic | all real calls in the last 30 days (API key spotify-pipeline) | input_tokens | 60964 | 60964 | 0 | [2026-10-12_anthropic_usage_full_run.webp](reconciliation/2026-10-12_anthropic_usage_full_run.webp) |
| 2026-10-13 | anthropic | all real calls in the last 30 days (API key spotify-pipeline) | output_tokens | 24866 | 24866 | 0 | [2026-10-12_anthropic_usage_full_run.webp](reconciliation/2026-10-12_anthropic_usage_full_run.webp) |

## Full-run projection (estimates, not measurements)

Per-unit usage source: **analysis_10000** (refreshed from a larger run). Projected rows: 660,622 (all source rows); 660,609 nonempty classifications and 13 empty-text quarantines at the course volume; exact-text reuse leaves 484,189 distinct texts for first-pass enrichment. Fixed overhead (memo, issue discovery) is counted once, never per review.

Controls: budget **$10.00**, max workers **1**, Claude output cap **4000** tokens, max fallback fraction **0.0** (No stronger-model fallback is used; invalid outputs are retried once then quarantined.)

| Scenario | Reuse | Enrich | Verify | Group assign | Fixed (memo, discovery) | **Total** | Est. time | Budget check |
|---|---|---|---|---|---|---|---|---|
| base | with exact text reuse | $6.27 | $0.1506 | $0.8363 | $0.0384 | **$7.29** | 0.72 h | within budget |
| base | no reuse | $8.55 | $0.2054 | $1.14 | $0.0384 | **$9.94** | 0.99 h | within budget |
| conservative | with exact text reuse | $7.49 | $0.3600 | $0.9998 | $0.0767 | **$8.93** | 1.10 h | within budget |
| conservative | no reuse | $10.22 | $0.4912 | $1.36 | $0.0767 | **$12.15** | 1.50 h | **OVER BUDGET** |

Assumptions: base = retry 1%, verify 1%; conservative = retry 5%, +15% tokens, verify 2%, memo x2, +50% time. Time = requests x measured seconds per request / workers.

Per-unit measurements used:

```json
{
  "run": "pilot_cost_100",
  "records_completed": 100,
  "direct_labelled": 100,
  "negative_share": 0.4446,
  "jev_assign_share": 0.6925326135852452,
  "enrich": {
    "tokens_per_review": 305.13529829545456,
    "sec_per_request": 0.2187988165680473,
    "attempts": 169,
    "model": "jev-1.13.0"
  },
  "verify": {
    "tokens_per_review": 733.0295857988166,
    "sec_per_request": 0.2925,
    "model": "jev-1.13.0"
  },
  "group_assign": {
    "tokens_per_review": 132.23838908736602,
    "sec_per_request": 0.14631818181818182,
    "model": "jev-1.13.0"
  },
  "group_discovery": {
    "input_tokens": 13412,
    "output_tokens": 3376,
    "seconds": 51.536,
    "model": "claude-haiku-4-5-20251001"
  },
  "memo": {
    "input_tokens": 4765,
    "output_tokens": 2884,
    "seconds": 23.53,
    "attempts": 1,
    "model": "claude-sonnet-5-5"
  },
  "source": "analysis_10000"
}
```
