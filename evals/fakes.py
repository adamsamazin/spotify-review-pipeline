"""Offline fake responders for the Claude roles (synthetic; used only by free tests)."""

import json

from pipeline.claude import FakeClaude


def _payload(user):
    start = user.index("{")
    depth = 0
    for i, ch in enumerate(user[start:], start):  # first balanced JSON object in the prompt
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            return json.loads(user[start:i + 1])
    raise ValueError("no JSON payload")


def responder(system, user, schema, bad_memo=False):
    data = _payload(user)
    data = data.get("reviews_by_topic", data)
    if "issues" in schema["properties"]:
        return {"issues": [{"topic": t, "slug": "main_problem", "name": f"Main {t} problem",
                            "definition": f"The most common {t} complaint.",
                            "example_ids": [e["id"] for e in ex[:3]] + ["not-a-real-id"]}
                           for t, ex in data.items()]}
    top = data["ranking_top"][0]
    pack = data["evidence_pack"][top["issue_id"]]
    rid = pack[0]["review_id"] if pack else None
    value = "999" if bad_memo else top["complaint_count"]
    memo = (f"## Recommendation\nPrioritize `{top['issue_id']}`: {value} [C1] complaints with severity sum "
            f"{top['severity_sum']} [C2].\n\n## Evidence\n" + (f"See `{rid}`.\n" if rid else "") +
            "\n## Alternatives considered\nOther issues rank lower.\n\n## Limitations\nSelf-selected reviews.\n")
    return {"memo_markdown": memo, "cited_review_ids": [rid] if rid else [],
            "claims": [{"claim_id": "C1", "issue_id": top["issue_id"], "metric": "complaint_count", "value": value},
                       {"claim_id": "C2", "issue_id": top["issue_id"], "metric": "severity_sum",
                        "value": top["severity_sum"]}]}


def fake_claude(bad_first_memo=False):
    state = {"n": 0}

    def r(system, user, schema):
        if "issues" not in schema["properties"]:
            state["n"] += 1
            return responder(system, user, schema, bad_memo=bad_first_memo and state["n"] == 1)
        return responder(system, user, schema)
    return FakeClaude(r)
