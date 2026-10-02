"""Thin adapter over the TypeSafe SDK (plus an offline fake for free testing).

SDK auto-retries are disabled: every attempt is made and logged by our own code, so
failures, retries and their usage are visible in calls.jsonl.
"""

import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass, field

TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504, 529}


@dataclass
class CallResult:
    ok: bool
    model: str | None = None
    answers: dict = field(default_factory=dict)  # question_id -> plain dict
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str = ""
    status: int | None = None
    error: str = ""
    transient: bool = False
    seconds: float = 0.0


class JevClient:
    def __init__(self, model, timeout=60.0):
        from dotenv import load_dotenv
        from typesafe_sdk import RetryPolicy, TypeSafeClient
        from pipeline.contract import ROOT
        load_dotenv(ROOT / ".env")
        self.model = model
        self._client = TypeSafeClient(model=model, retry=RetryPolicy(max_retries=0), timeout=timeout)

    def ask(self, state, questions):
        import typesafe_sdk as t
        start = time.perf_counter()
        try:
            r = self._client.system_one(state=state, questions=questions, model=self.model)
            dumped = r.model_dump()
            return CallResult(True, dumped.get("model"), {k: dict(v) for k, v in dumped["answers"].items()},
                              r.usage.input_tokens, r.usage.output_tokens, r.request_id or f"local-{uuid.uuid4()}",
                              200, seconds=time.perf_counter() - start)
        except t.TypeSafeAPIError as e:
            return CallResult(False, request_id=getattr(e, "request_id", None) or f"local-{uuid.uuid4()}",
                              status=e.status, error=f"{type(e).__name__}: {str(e)[:300]}",
                              transient=e.status in TRANSIENT_STATUSES, seconds=time.perf_counter() - start)
        except (t.TypeSafeAPITimeoutError, t.TypeSafeAPIConnectionError) as e:
            # The request may still have been billed; usage is unknown and is charged at the estimate.
            return CallResult(False, request_id=f"local-{uuid.uuid4()}", error=f"{type(e).__name__}: {e}"[:300],
                              transient=True, seconds=time.perf_counter() - start)


class FakeJev:
    """Deterministic offline stand-in for tests: answers derive from a hash of the question.
    `fail_plan` maps call number -> 'transient' | 'malformed' | 'drop_one' to rehearse failures."""

    def __init__(self, model="fake-jev", fail_plan=None):
        self.model, self.calls, self.fail_plan = model, 0, fail_plan or {}

    def ask(self, state, questions):
        self.calls += 1
        mode = self.fail_plan.get(self.calls)
        rid = f"fake-{uuid.uuid4()}"
        if mode == "transient":
            return CallResult(False, request_id=rid, status=529, error="fake overload", transient=True)
        answers = {}
        for qid, q in questions.items():
            q = q.model_dump() if hasattr(q, "model_dump") else dict(q)
            ref = json.dumps(q.get("instructions"))
            h = int(hashlib.sha256((ref + json.dumps(state, sort_keys=True)).encode()).hexdigest(), 16)
            rng = random.Random(h)
            if q["type"] == "choice":
                opts = list(q["criteria"])
                w = [rng.random() ** 3 for _ in opts]
                s = sum(w)
                probs = {o: x / s for o, x in zip(opts, w)}
                answers[qid] = {"type": "choice", "choice": max(probs, key=probs.get),
                                "probabilities": probs, "confidence": max(probs.values())}
            else:
                n = len(q["criteria"])
                answers[qid] = {"type": "score", "score": rng.uniform(0, n - 1),
                                "probabilities": {str(i): 1 / n for i in range(n)}, "confidence": 0.5,
                                "legend": {str(i): c for i, c in enumerate(q["criteria"])}}
        if mode == "malformed":
            k = next(iter(answers))
            answers[k] = {"type": "choice", "choice": "not-a-label", "probabilities": {"x": 1.0}}
        if mode == "drop_one":
            answers.pop(next(iter(answers)))
        tokens = len(json.dumps(state)) // 4 + sum(len(json.dumps(
            q.model_dump() if hasattr(q, "model_dump") else q)) for q in questions.values()) // 4
        return CallResult(True, self.model, answers, tokens, 10 * len(questions), rid, 200, seconds=0.0)
