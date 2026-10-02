"""Shared constants plus the course-provided hashing/profile helpers.

row_sha() and profile() come from the instructor's check_submission.py so our hashes
match the checker byte-for-byte. That file ships in the dataset ZIP (data/).
"""

import hashlib
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER_PATH = Path(os.environ.get("A5_CHECKER", ROOT / "data" / "check_submission.py"))

if not CHECKER_PATH.exists():
    raise FileNotFoundError(
        f"{CHECKER_PATH} not found. Unzip the course dataset into data/ (see data/README.md) "
        "or set A5_CHECKER to the path of check_submission.py."
    )
_spec = importlib.util.spec_from_file_location("check_submission", CHECKER_PATH)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

FIELDS = checker.FIELDS
TOPICS = checker.TOPICS
INTENT_PRECEDENCE = ("cancellation", "complaint", "request", "praise", "unclear")
assert set(INTENT_PRECEDENCE) == set(checker.INTENTS)

row_sha = checker.row_sha
file_sha = checker.sha
csv_rows = checker.csv_rows
profile = checker.profile
write_json = checker.write_json
read_json = checker.read_json
mean_string = checker.mean_string

# Expected full-corpus facts from the assignment brief and data/manifest.json.
FULL_SHA256 = "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6"
FULL_EXPECTED = {"records": 660622, "empty_review_text": 13, "missing_app_version": 159701,
                 "duplicate_review_ids": 0, "distinct_nonempty_texts": 484189}


def text_sha(text):
    """Exact-text cache key component: no trimming or normalization."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
