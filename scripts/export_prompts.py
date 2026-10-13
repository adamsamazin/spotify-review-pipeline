"""Export every role's prompt/question set to prompts/roles/ from the exact code constants (offline).

    .venv\\Scripts\\python scripts\\export_prompts.py

The files are generated, not hand-written, so they always match what the pipeline sends.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import group, memo, questions  # noqa: E402
from pipeline.schema import NEEDS_REVIEW_MAX_PROB, POST_VERSION, QUOTE_FULL_TEXT_MAX  # noqa: E402

OUT = ROOT / "prompts" / "roles"


def dump_questions(variant):
    texts = ["<review text 1>", "<review text 2>"]
    state, qs = questions.build_request(texts, variant)
    return {"state_shape": state, "questions_for_two_reviews": {
        k: (v.model_dump(exclude_none=True) if hasattr(v, "model_dump") else v) for k, v in qs.items()}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "enrich_shared_v1.json": {
            "role": "enrich", "model": "jev-1.13.0", "label_config": "jev-1.13.0+enrich_shared_v1+schema_v1",
            "notes": "Up to 50 reviews per request keyed r01..r50; definitions are sent once per request in the state. "
                     "Code then maps answers: sentiment = score/2 - 1; severity rules (praise/request/unclear -> 1, "
                     f"complaint >= 2); evidence quote = full text if <= {QUOTE_FULL_TEXT_MAX} chars else best keyword "
                     f"sentence; needs_review when a top option < {NEEDS_REVIEW_MAX_PROB}; post_version {POST_VERSION}.",
            **dump_questions("shared_v1")},
        "verify_v1.json": {
            "role": "verify", "model": "jev-1.13.0", "label_config": "jev-1.13.0+verify_v1+schema_v1",
            "notes": "Separate wording with inline rubric; sees only the review text, never the enricher's answer.",
            **dump_questions("verify_v1")},
        "group_discover_v2.json": {
            "role": "group (issue discovery)", "model": "claude-haiku-4-5", "version": group.DISCOVERY_PROMPT_VERSION,
            "system": group.DISCOVERY_SYSTEM,
            "user_format": "Topic definitions and complaint reviews grouped by topic (JSON): "
                           "{topic_definitions: {...}, reviews_by_topic: {topic: [{id, text<=300 chars}] x <=30}}",
            "output_schema": group.SCHEMA,
            "notes": "Run once on the analysis_10000 development run; a person then accepted the catalog "
                     "(prompts/catalog_edits.json -> prompts/catalog_accepted.json), which the full run reused."},
        "group_assign_v1.json": {
            "role": "group (assignment)", "model": "jev-1.13.0", "version": group.ASSIGN_VERSION,
            "state_shape": {"issues": {"<issue_id>": "<definition>"}, "reviews": {"r01": "<review text>"}},
            "question_template": {"type": "choice",
                                  "instructions": "Which issue in `issues` best describes the problem in `reviews.rNN`?",
                                  "criteria": "{<issue_id>: null, ...} for the review's topic only"},
            "notes": "Complaints are batched by topic (<=50 per request); single-issue topics and duplicate texts are "
                     "assigned by code; an unresolved answer falls back to the topic catch-all and is recorded."},
        "memo_v3.json": {
            "role": "memo", "model": "claude-sonnet-5-5", "effort": "high", "max_tokens": 16000,
            "version": memo.MEMO_PROMPT_VERSION, "system": memo.SYSTEM, "output_schema": memo.SCHEMA,
            "user_format": "Saved pipeline outputs (JSON): question, ranking_top (6 issues), ranking_rule, topic_rollup, "
                           "run_totals, evidence_pack (4 reviews x top issues, <=250 chars), notes",
            "notes": "Code inserts each claim's exact value before its [Cn] tag and rejects unknown IDs or numbers; "
                     "one retry with the problems listed."},
    }
    for name, body in files.items():
        (OUT / name).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"exported {len(files)} role prompt files to {OUT}")


if __name__ == "__main__":
    main()
