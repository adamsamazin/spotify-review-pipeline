"""100-review cost and runtime calculator (COST_CALCULATOR.md).

Offline replay is the default and needs no API key:
    python -m cost.calculator                         # recompute from saved usage x cost/rates.csv
    python -m cost.calculator --rate-multiplier 2     # check: API spend doubles, measured time unchanged
    python -m cost.calculator --refresh runs/checkpoint_500 --refresh runs/analysis_10000
    python -m cost.calculator --records 1000000       # projection volume only; pilot numbers unchanged

Paid pilot execution is a separate, explicit command:
    python -m cost.calculator pilot --confirm-paid    # cold run on data/cost_100.csv, then warm rerun

Importing this module never makes a model call.
"""

import argparse
import csv
import json
import math
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COST = ROOT / "cost"
PILOT_RUN = "pilot_cost_100"
PILOT_CSV = ROOT / "data" / "cost_100.csv"
PILOT_SHA = "c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e"


# ---------------------------------------------------------------- rates & usage
def load_rates(path, multiplier=1.0):
    rates, meta = {}, {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rates[(r["model"], r["billing_item"])] = float(r["price_per_unit"]) * multiplier
            meta[r["model"]] = (r["provider"], r["source_url"], r["checked_on"], r["currency"])
    return rates, meta


def price(rates, model, item):
    if model.startswith("fake-"):
        return 0.0
    if (model, item) not in rates:
        raise KeyError(f"no rate for {model} {item} in rates.csv; add it (unknown costs are never treated as $0)")
    return rates[(model, item)]


def call_cost(rates, c):
    """Mutually exclusive billing items x price per unit. Unknown usage stays unknown (None)."""
    if c.get("input_tokens") is None:
        return None
    return c["input_tokens"] * price(rates, c["model"], "input_tokens") + \
        (c.get("output_tokens") or 0) * price(rates, c["model"], "output_tokens")


def read_jsonl(path):
    return [json.loads(l) for l in Path(path).open(encoding="utf-8") if l.strip()] if Path(path).exists() else []


# ---------------------------------------------------------------- per-unit measurements from a run
def unit_measurements(calls, run_dir, rates):
    """Per-stage usage per unit of work, from a run's call log and state."""
    db = sqlite3.connect(Path(run_dir) / "state.sqlite")
    completed = db.execute("SELECT COUNT(*) FROM records WHERE status='completed'").fetchone()[0]
    direct = db.execute("SELECT COUNT(*) FROM results WHERE cache_source_id IS NULL").fetchone()[0]
    negatives = sum(1 for (r,) in db.execute("SELECT record_json FROM results")
                    if json.loads(r)["intent"] in ("complaint", "cancellation"))
    jev_group = [c for c in calls if c["role"] == "group" and c["model"].startswith(("jev", "fake-jev"))]
    claude_group = [c for c in calls if c["role"] == "group" and not c["model"].startswith(("jev", "fake-jev"))]
    by = defaultdict(list)
    for c in calls:
        by[c["role"]].append(c)

    def tok(cs, k="input_tokens"):
        return sum(c.get(k) or 0 for c in cs)

    def secs(cs):
        return sum(c.get("seconds") or 0 for c in cs)
    verified = sum(len(c["review_ids"]) for c in by["verify"] if c["outcome"] == "succeeded")
    assigned = sum(len(c["review_ids"]) for c in jev_group if c["outcome"] == "succeeded")
    m = {
        "run": Path(run_dir).name, "records_completed": completed, "direct_labelled": direct,
        "negative_share": negatives / completed if completed else None,
        "enrich": {"tokens_per_review": tok(by["enrich"]) / direct if direct else None,
                   "sec_per_request": secs(by["enrich"]) / len(by["enrich"]) if by["enrich"] else None,
                   "attempts": len(by["enrich"]), "model": by["enrich"][0]["model"] if by["enrich"] else None},
        "verify": {"tokens_per_review": tok(by["verify"]) / verified if verified else None,
                   "sec_per_request": secs(by["verify"]) / len(by["verify"]) if by["verify"] else None,
                   "model": by["verify"][0]["model"] if by["verify"] else None},
        "group_assign": {"tokens_per_review": tok(jev_group) / assigned if assigned else None,
                         "sec_per_request": secs(jev_group) / len(jev_group) if jev_group else None,
                         "model": jev_group[0]["model"] if jev_group else None},
        "group_discovery": {"input_tokens": tok(claude_group), "output_tokens": tok(claude_group, "output_tokens"),
                            "seconds": secs(claude_group), "model": claude_group[0]["model"] if claude_group else None},
        "memo": {"input_tokens": tok(by["memo"]), "output_tokens": tok(by["memo"], "output_tokens"),
                 "seconds": secs(by["memo"]), "attempts": len(by["memo"]),
                 "model": by["memo"][0]["model"] if by["memo"] else None},
    }
    return m


# ---------------------------------------------------------------- projection
def project(units, a, rates, rows, scenario_name):
    s = a["scenarios"][scenario_name]
    scale = rows / a["full_rows"]  # volume override scales every row count proportionally
    distinct = round(a["full_distinct_nonempty"] * scale)
    nonempty = round(a["full_nonempty"] * scale)
    out = {}
    for label, D in (("with_exact_text_reuse", distinct), ("no_reuse", nonempty)):
        lines, secs, unknown = [], 0.0, []
        workers = max(1, a["max_workers"])

        def var(stage, n_units, per_req_units=50):
            u = units[stage]
            if u["tokens_per_review"] is None or u["model"] is None:
                unknown.append(f"{stage}: not measured in the chosen run")
                return 0.0, 0.0
            toks = u["tokens_per_review"] * n_units * (1 + s["token_inflation"]) * (1 + s["retry_rate"])
            cost = toks * price(rates, u["model"], "input_tokens")
            t = math.ceil(n_units / per_req_units) * (u["sec_per_request"] or 0) / workers * (1 + s["time_inflation"])
            lines.append({"stage": stage, "units": round(n_units), "tokens": round(toks), "cost_usd": cost,
                          "seconds": t, "model": u["model"]})
            return cost, t
        c1, t1 = var("enrich", D)
        c2, t2 = var("verify", max(a["verify_min"], math.ceil(s["verify_fraction"] * D)))
        neg = units["negative_share"] or 0
        c3, t3 = var("group_assign", neg * D)
        fixed = []
        for stage, mult in (("group_discovery", 0 if a["catalog_reused_in_full_run"] else 1),
                            ("memo", s["memo_attempts"] / max(1, units["memo"]["attempts"] or 1))):
            u = units[stage]
            if u["model"] is None:
                unknown.append(f"{stage}: not measured")
                continue
            cost = (u["input_tokens"] * price(rates, u["model"], "input_tokens")
                    + u["output_tokens"] * price(rates, u["model"], "output_tokens")) * mult
            fixed.append({"stage": stage + " (fixed, once)", "units": 1, "tokens": round(u["input_tokens"] * mult),
                          "cost_usd": cost, "seconds": u["seconds"] * mult, "model": u["model"]})
        lines += fixed
        total = sum(l["cost_usd"] for l in lines)
        secs = sum(l["seconds"] for l in lines)
        out[label] = {"distinct_units": D, "lines": lines, "total_usd": total, "seconds": secs,
                      "over_budget": total > a["budget_usd"], "unknown": unknown}
    return out


# ---------------------------------------------------------------- report
def fmt_usd(x):
    return "unknown" if x is None else f"${x:,.4f}" if x < 1 else f"${x:,.2f}"


def replay(args):
    a = json.loads(Path(args.assumptions).read_text(encoding="utf-8"))
    if args.budget is not None:
        a["budget_usd"] = args.budget
    if args.workers is not None:
        a["max_workers"] = args.workers
    rates, meta = load_rates(args.rates, args.rate_multiplier)
    calls = read_jsonl(COST / "pilot_calls.jsonl")
    if not calls:
        sys.exit("cost/pilot_calls.jsonl not found: run `python -m cost.calculator pilot --confirm-paid` first")
    cold_s = json.loads((COST / "pilot_summary_cold.json").read_text(encoding="utf-8"))
    warm_s = json.loads((COST / "pilot_summary_warm.json").read_text(encoding="utf-8"))
    records = read_jsonl(COST / "pilot_records.jsonl")
    pilot_ids = [r["review_id"] for r in records]
    with PILOT_CSV.open(encoding="utf-8", newline="") as f:
        csv_ids = [r["review_id"] for r in csv.DictReader(f)]

    # ---- measured cost by pilot phase and stage
    lines = []
    for c in calls:
        cost = call_cost(rates, c)
        lines.append({**c, "cost_usd": cost})
    with (COST / "cost_lines.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["pilot_phase", "request_id", "role", "model", "outcome", "billing_item", "units",
                    "price_per_unit_usd", "item_cost_usd"])
        for c in lines:
            for item in ("input_tokens", "output_tokens"):
                units = c.get(item)
                p = price(rates, c["model"], item)
                w.writerow([c["pilot_phase"], c["request_id"], c["role"], c["model"], c["outcome"], item,
                            "" if units is None else units, f"{p:.12f}", "" if units is None else f"{units * p:.10f}"])
    stage = defaultdict(lambda: {"requests": set(), "attempts": 0, "failed": 0, "in": 0, "out": 0, "cost": 0.0,
                                 "unknown": 0, "models": set(), "configs": set(), "reviews": 0})
    for c in lines:
        key = (c["pilot_phase"], c["role"])
        st = stage[key]
        st["attempts"] += 1
        st["failed"] += c["outcome"] == "failed"
        st["in"] += c.get("input_tokens") or 0
        st["out"] += c.get("output_tokens") or 0
        st["models"].add(c["model"])
        st["configs"].add(c["label_config"])
        st["reviews"] += len(c["review_ids"]) if c["outcome"] == "succeeded" else 0
        if c["cost_usd"] is None:
            st["unknown"] += 1
        else:
            st["cost"] += c["cost_usd"]
    cold_total = sum(v["cost"] for (ph, _), v in stage.items() if ph == "cold")
    warm_total = sum(v["cost"] for (ph, _), v in stage.items() if ph == "warm")
    warm_enrich = stage[("warm", "enrich")]["attempts"] if ("warm", "enrich") in stage else 0
    completed = sum(1 for r in records if r["status"] == "completed")
    failed = len(records) - completed
    cache_hits = sum(1 for r in records if r.get("cache_source_id"))
    unique_texts = cold_s["ingest"]["extras"]["distinct_nonempty_texts"]

    # ---- per-unit measurements: pilot, or a larger refresh run
    pilot_units = unit_measurements([c for c in calls if c["pilot_phase"] == "cold"], ROOT / "runs" / PILOT_RUN, rates)
    refresh = []
    for r in args.refresh or []:
        rc = read_jsonl(Path(r) / "calls.jsonl")
        if rc:
            refresh.append(unit_measurements(rc, r, rates))
    units = dict(pilot_units)
    for ref in refresh:  # larger runs give steadier per-unit rates; fill stages the pilot could not measure
        for k in ("enrich", "verify", "group_assign", "group_discovery", "memo", "negative_share"):
            v = ref[k]
            if (isinstance(v, dict) and v.get("model")) or (k == "negative_share" and v is not None):
                units[k] = v
        units["source"] = ref["run"]
    units.setdefault("source", PILOT_RUN)
    rows = args.records or a["full_rows"]
    proj = {sc: project(units, a, rates, rows, sc) for sc in a["scenarios"]}

    # ---- write report
    L = []
    w = L.append
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    w(f"# 100-review cost & runtime report\n\nGenerated {now} by offline replay "
      f"(`python -m cost.calculator`{' --rate-multiplier ' + str(args.rate_multiplier) if args.rate_multiplier != 1 else ''}). "
      "No API key or model call is used to produce this report.\n")
    w("## Measured pilot (real calls on `data/cost_100.csv`)\n")
    w(f"- Input checksum `{cold_s['input_sha256']}` - matches course manifest: **{cold_s['input_sha256'] == PILOT_SHA}**")
    w(f"- Pilot IDs saved: {len(pilot_ids)}; identical to cost_100.csv IDs in order: **{pilot_ids == csv_ids}**")
    w(f"- Records: {completed} completed, {failed} not completed; unique texts {unique_texts}; result-cache hits {cache_hits}")
    w(f"- Cold run: empty result cache (fresh run directory), 1 worker. Warm run: same settings, saved results.")
    w(f"- **Wall-clock (measured with a clock): cold {cold_s['wall_seconds']:.2f} s, warm {warm_s['wall_seconds']:.2f} s**")
    w(f"- **API cost: cold {fmt_usd(cold_total)}, warm (incremental) {fmt_usd(warm_total)}**; "
      f"warm enrichment calls: **{warm_enrich}**")
    w(f"- Cost per 1,000 input rows (cold): {fmt_usd(cold_total / len(records) * 1000)}; "
      f"per completed record: {fmt_usd(cold_total / completed if completed else None)}; "
      f"throughput {len(records) / cold_s['wall_seconds']:.1f} rows/s end-to-end")
    w("")
    w("### By stage (cold run)\n")
    w("| Stage | Provider | Exact model | Effort / settings | Prompt / schema version | Batch | Workers | "
      "Requests (attempts / failed) | Reviews sent | Input tok | Output tok | Cost | Stage time (s) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    effort = {"enrich": "no effort control (Jev); 4 questions/review", "verify": "no effort control (Jev)",
              "group": "Jev assign / Haiku discovery: no extended thinking, JSON schema",
              "memo": "Haiku: no extended thinking, JSON schema, max_tokens 4000"}
    for role in ("enrich", "verify", "group", "memo"):
        st = stage.get(("cold", role))
        if not st:
            w(f"| {role} | - | - | - | - | - | 1 | 0 | 0 | 0 | 0 | $0 | {cold_s['timings'].get(role, 0):.2f} |")
            continue
        provs = ", ".join(sorted({meta.get(m, ("fake",))[0] for m in st["models"]}))
        w(f"| {role} | {provs} | {', '.join(sorted(st['models']))} | {effort[role]} | {', '.join(sorted(st['configs']))} | "
          f"{'<=50' if role != 'memo' else '1'} | 1 | {st['attempts']} / {st['failed']} | {st['reviews']} | {st['in']:,} | "
          f"{st['out']:,} | {fmt_usd(st['cost'])}{' + ' + str(st['unknown']) + ' unknown' if st['unknown'] else ''} | "
          f"{cold_s['timings'].get(role, 0):.2f} |")
    w(f"| ingest + rank (code) | local | - | - | - | - | 1 | 0 | - | - | - | $0 API (local compute unknown) | "
      f"{cold_s['timings'].get('ingest', 0) + cold_s['timings'].get('rank', 0):.2f} |")
    w("\nSummed call durations are not wall-clock time; the wall-clock figures above are from a clock around the whole run.\n")
    w("### Rates used (editable: `cost/rates.csv`)\n")
    w("| Model | Item | Price per unit | Currency | Source | Checked |")
    w("|---|---|---|---|---|---|")
    used = {c["model"] for c in calls}
    for (model, item), p in sorted(rates.items()):
        if model in used:
            prov, url, checked, cur = meta[model]
            w(f"| {model} | {item} | {p:.12f} per token | {cur} | {url} | {checked} |")
    w(f"\nItem cost = billed units x price per unit (per-million prices divided by 1,000,000). Input and output are "
      f"mutually exclusive items; Jev bills input only (output price 0); no cached-input or batch tier was used. "
      f"Per-call lines: `cost/cost_lines.csv`; raw usage: `cost/usage.csv`.\n")
    w(f"Local compute: {a['local_compute']}\n")

    w("## Full-run projection (estimates, not measurements)\n")
    w(f"Per-unit usage source: **{units['source']}**" + (" (refreshed from a larger run)" if refresh else " (pilot)") +
      f". Projected rows: {rows:,} (all source rows); {a['full_nonempty']:,} nonempty classifications and "
      f"{a['full_empty_quarantine']} empty-text quarantines at the course volume; exact-text reuse leaves "
      f"{a['full_distinct_nonempty']:,} distinct texts for first-pass enrichment. Fixed overhead (memo, issue discovery) "
      f"is counted once, never per review.\n")
    w(f"Controls: budget **${a['budget_usd']:.2f}**, max workers **{a['max_workers']}**, Claude output cap "
      f"**{a['claude_output_token_cap']}** tokens, max fallback fraction **{a['max_fallback_fraction']}** "
      f"({a['fallback_note']})\n")
    w("| Scenario | Reuse | Enrich | Verify | Group assign | Fixed (memo, discovery) | **Total** | Est. time | Budget check |")
    w("|---|---|---|---|---|---|---|---|---|")
    for sc, pr in proj.items():
        for label, p in pr.items():
            get = {l["stage"].split(" ")[0]: l["cost_usd"] for l in p["lines"]}
            fixed = sum(l["cost_usd"] for l in p["lines"] if "fixed" in l["stage"])
            flag = "**OVER BUDGET**" if p["over_budget"] else "within budget"
            w(f"| {sc} | {label.replace('_', ' ')} | {fmt_usd(get.get('enrich'))} | {fmt_usd(get.get('verify'))} | "
              f"{fmt_usd(get.get('group_assign'))} | {fmt_usd(fixed)} | **{fmt_usd(p['total_usd'])}** | "
              f"{p['seconds'] / 3600:.2f} h | {flag} |")
    unknowns = sorted({u for pr in proj.values() for p in pr.values() for u in p["unknown"]})
    if unknowns:
        w("\nNot yet measured (excluded from totals, refresh with a larger run): " + "; ".join(unknowns))
    s = a["scenarios"]
    w(f"\nAssumptions: base = retry {s['base']['retry_rate']:.0%}, verify {s['base']['verify_fraction']:.0%}; "
      f"conservative = retry {s['conservative']['retry_rate']:.0%}, +{s['conservative']['token_inflation']:.0%} tokens, "
      f"verify {s['conservative']['verify_fraction']:.0%}, memo x{s['conservative']['memo_attempts']}, "
      f"+{s['conservative']['time_inflation']:.0%} time. Time = requests x measured seconds per request / workers.\n")
    w("Per-unit measurements used:\n")
    w("```json\n" + json.dumps({k: v for k, v in units.items()}, indent=2, default=str) + "\n```")
    report = "\n".join(L) + "\n"
    out = Path(args.out)
    out.write_text(report, encoding="utf-8")
    print(report if args.print else f"wrote {out}: cold {fmt_usd(cold_total)} / {cold_s['wall_seconds']:.2f}s, "
          f"warm {fmt_usd(warm_total)} / {warm_s['wall_seconds']:.2f}s, warm enrich calls {warm_enrich}; "
          + " | ".join(f"{sc} {fmt_usd(pr['with_exact_text_reuse']['total_usd'])}" for sc, pr in proj.items()))
    return {"cold_total": cold_total, "warm_total": warm_total, "projection": proj}


# ---------------------------------------------------------------- explicit paid pilot
def pilot(args):
    if not args.confirm_paid:
        sys.exit("The pilot makes real paid API calls. Re-run with --confirm-paid to proceed.")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from pipeline.export import records
    from pipeline.run import run
    run_dir = ROOT / "runs" / PILOT_RUN
    if run_dir.exists():
        if not args.fresh:
            sys.exit(f"{run_dir} exists; pass --fresh to delete it and start a new cold pilot")
        shutil.rmtree(run_dir)
    cold = run(PILOT_CSV, PILOT_RUN, label="cold", budget=args.budget)
    n_cold = len(read_jsonl(run_dir / "calls.jsonl"))
    warm = run(PILOT_CSV, PILOT_RUN, label="warm", budget=args.budget)
    calls = read_jsonl(run_dir / "calls.jsonl")
    with (COST / "pilot_calls.jsonl").open("w", encoding="utf-8") as f:
        for i, c in enumerate(calls):
            f.write(json.dumps({**c, "pilot_phase": "cold" if i < n_cold else "warm"}) + "\n")
    with (COST / "usage.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["pilot_phase", "request_id", "role", "model", "outcome", "attempt", "n_reviews",
                    "input_tokens", "output_tokens", "seconds", "started_at", "usage_status"])
        for i, c in enumerate(calls):
            w.writerow(["cold" if i < n_cold else "warm", c["request_id"], c["role"], c["model"], c["outcome"],
                        c.get("attempt"), len(c["review_ids"]), c.get("input_tokens"), c.get("output_tokens"),
                        c.get("seconds"), c.get("started_at"),
                        "provider-reported" if c.get("input_tokens") is not None else "missing (unknown)"])
    with (COST / "pilot_records.jsonl").open("w", encoding="utf-8") as f:
        for r in records(run_dir):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    man = json.loads((run_dir / "data_manifest.json").read_text(encoding="utf-8"))
    ing = json.loads((run_dir / "ingestion_report.json").read_text(encoding="utf-8"))
    for label, s in (("cold", cold), ("warm", warm)):
        s = {**s, "input_sha256": man["input_sha256"], "ingest": {"extras": ing["extras"]}}
        (COST / f"pilot_summary_{label}.json").write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")
    for name in ("memo/memo.md", "memo/claims.csv", "rank/ranking.csv", "group/catalog.json", "verify/disagreements.json"):
        src = run_dir / name
        if src.exists():
            (COST / "pilot_outputs").mkdir(exist_ok=True)
            shutil.copy(src, COST / "pilot_outputs" / name.replace("/", "_"))
    print(f"pilot saved: {n_cold} cold calls, {len(calls) - n_cold} warm calls")
    args.refresh = []
    replay(args)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="replay", choices=["replay", "pilot"])
    ap.add_argument("--rates", default=COST / "rates.csv")
    ap.add_argument("--assumptions", default=COST / "assumptions.json")
    ap.add_argument("--rate-multiplier", type=float, default=1.0, help="scale every API price (sensitivity check)")
    ap.add_argument("--refresh", action="append", help="larger run dir for steadier per-unit rates")
    ap.add_argument("--records", type=int, help="projected row count (default: full corpus)")
    ap.add_argument("--budget", type=float, help="override budget_usd in assumptions")
    ap.add_argument("--workers", type=int, help="override max_workers in assumptions")
    ap.add_argument("--out", default=COST / "report.md")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--confirm-paid", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    pilot(args) if args.command == "pilot" else replay(args)


if __name__ == "__main__":
    main()
