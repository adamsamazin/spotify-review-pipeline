"""Write results/full/run_manifest.json: one record tying the final run's input, code, prompts, models,
settings and outputs together (offline, from saved artifacts).

    .venv/Scripts/python scripts/make_run_manifest.py
"""
import hashlib, json, sqlite3, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "runs" / "full"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main():
    db = sqlite3.connect(RUN / "state.sqlite")
    dm = json.loads((RUN / "data_manifest.json").read_text(encoding="utf-8"))
    roles = [dict(zip(("role", "model", "label_config", "calls", "failed", "input_tokens", "output_tokens", "cost_usd"), r))
             for r in db.execute("SELECT role, model, label_config, COUNT(*), SUM(outcome='failed'), SUM(input_tokens), "
                                 "SUM(output_tokens), ROUND(SUM(cost_usd), 6) FROM calls GROUP BY role, model, label_config")]
    sessions = [dict(zip(("session", "role", "phase", "started_at", "ended_at", "stop_reason"), r)) for r in db.execute(
        "SELECT session_id, role, phase, started_at, ended_at, stop_reason FROM sessions ORDER BY session_id")]
    outputs = sorted([p for p in (ROOT / "grading").iterdir() if p.is_file() and p.name != "ranking_regenerated.csv"]
                     + [p for p in (ROOT / "results" / "full").iterdir() if p.is_file() and p.name != "run_manifest.json"])
    prompts = sorted((ROOT / "prompts").rglob("*.*"))
    man = {
        "run_id": "full",
        "input": {"file": dm["input_name"], "bytes": dm["input_bytes"], "sha256": dm["input_sha256"],
                  "parsed_rows_sha256": dm["parsed_rows_sha256"]},
        "code_version": {
            "at_ingest": dm["code_version"],
            "explanation": "The '-dirty' flag at run start came from files not yet committed: scripts/full_run_demo.py and "
                           "dashboard changes. `git diff f58b182 d92742c -- pipeline/` is empty, so the pipeline code that "
                           "produced the run is exactly commit f58b182; d92742c committed the demo script and outputs.",
            "pipeline_code_commit": "f58b182", "outputs_committed_in": "d92742c", "manifest_written_at_commit": git("rev-parse", "--short", "HEAD")},
        "models_and_label_configs": roles,
        "settings": {"enrich_batch_size": 50, "enrich_workers": 4, "enrich_variant": "shared_v1", "schema": "schema_v1",
                     "post_version": "post_v2", "needs_review_max_prob": 0.60, "verify_fraction": 0.01,
                     "verify_seed": "a5-verify-v1", "transient_attempts": 4, "invalid_output_retries": 1,
                     "spend_cap_usd_all_runs": 10.0, "issue_catalog": "prompts/catalog_accepted.json",
                     "issue_catalog_sha256": sha(ROOT / "prompts" / "catalog_accepted.json"),
                     "memo_model": "claude-sonnet-5-5", "memo_effort": "high", "memo_max_tokens": 16000,
                     "interruption": "--max-batches 40 (initial), resume --max-batches 40, then completion"},
        "sessions": sessions,
        "prompts": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in prompts},
        "outputs": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in outputs},
    }
    (ROOT / "results" / "full" / "run_manifest.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    print(f"run_manifest.json: {len(roles)} role/model configs, {len(sessions)} sessions, {len(man['prompts'])} prompt files, "
          f"{len(man['outputs'])} outputs hashed")


if __name__ == "__main__":
    main()
