"""Apply a person's review decisions to a discovered issue catalog (offline, no model calls).

    python -m pipeline.accept_catalog runs/analysis_10000/group/catalog.json prompts/catalog_edits.json \
        --out prompts/catalog_accepted.json

Edits file (JSON list), applied in order:
  {"op": "merge", "from": ["billing.a", "billing.b"], "into": "billing.paywall", "name": "...", "definition": "..."}
  {"op": "move", "id": "access.x", "to_topic": "playback", "new_id": "playback.x"}
  {"op": "rename", "id": "usability.x", "name": "...", "definition": "..."}
  {"op": "drop", "id": "catalog.x"}          # its members fall to the topic catch-all
The accepted catalog keeps an `edits` log and `accepted_by` note so the change is traceable.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.group import catch_all_id


def apply(catalog, edits):
    issues = {i["issue_id"]: dict(i) for i in catalog["issues"]}
    log = []
    for e in edits:
        op = e["op"]
        if op == "merge":
            srcs = [issues.pop(i) for i in e["from"]]
            topic = e["into"].split(".")[0]
            issues[e["into"]] = {"issue_id": e["into"], "topic": topic, "name": e["name"], "definition": e["definition"],
                                 "example_ids": sorted({x for s in srcs for x in s.get("example_ids", [])}),
                                 "source": "human_merge", "merged_from": e["from"]}
        elif op == "move":
            i = issues.pop(e["id"])
            i.update(issue_id=e["new_id"], topic=e["to_topic"], source="human_move", moved_from=e["id"])
            issues[e["new_id"]] = i
        elif op == "rename":
            issues[e["id"]].update({k: e[k] for k in ("name", "definition") if k in e}, source="human_edit")
        elif op == "drop":
            issues.pop(e["id"])
        else:
            raise ValueError(f"unknown op {op}")
        log.append(e)
    for t in {i["topic"] for i in issues.values()} | {i["topic"] for i in catalog["issues"]}:
        if catch_all_id(t) not in issues:
            raise ValueError(f"catch-all {catch_all_id(t)} missing after edits")
    return {**catalog, "issues": sorted(issues.values(), key=lambda i: i["issue_id"]), "edits": log,
            "accepted_by": "human review of the analysis_10000 catalog",
            "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("edits", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    out = apply(json.loads(args.catalog.read_text(encoding="utf-8")), json.loads(args.edits.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"accepted catalog: {len(out['issues'])} issues after {len(out['edits'])} edits -> {args.out}")


if __name__ == "__main__":
    main()
