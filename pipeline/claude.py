"""Claude adapter for the generative roles (issue naming, memo), plus an offline fake.

Structured outputs constrain the response to a JSON schema; code still validates every ID and
number afterwards. SDK retries are disabled so each attempt is logged by the caller.
"""

import json
import time
import uuid

from pipeline.jev import CallResult

DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"   # issue naming
MEMO_MODEL = "claude-sonnet-5-5"            # memo writing (stronger reasoning, chosen after Haiku memo errors)
MEMO_EFFORT = "high"


class ClaudeClient:
    def __init__(self, model=DEFAULT_CLAUDE_MODEL, timeout=300.0, max_tokens=4000, effort=None):
        import anthropic
        from dotenv import load_dotenv
        from pipeline.contract import ROOT
        load_dotenv(ROOT / ".env")
        self.model, self.max_tokens, self.effort = model, max_tokens, effort
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(max_retries=0, timeout=timeout)

    def ask_json(self, system, user, schema, max_tokens=None):
        a = self._anthropic
        output_config = {"format": {"type": "json_schema", "schema": schema}}
        if self.effort:  # Sonnet 5.5 thinks adaptively; effort sets depth (Haiku 4.5 takes no effort setting)
            output_config["effort"] = self.effort
        start = time.perf_counter()
        try:
            r = self._client.messages.create(
                model=self.model, max_tokens=max_tokens or self.max_tokens, system=system,
                messages=[{"role": "user", "content": user}], output_config=output_config)
        except (a.RateLimitError, a.InternalServerError, a.APIConnectionError, a.APITimeoutError) as e:
            status = getattr(e, "status_code", None)
            return CallResult(False, request_id=f"local-{uuid.uuid4()}", status=status,
                              error=f"{type(e).__name__}: {e}"[:300], transient=True,
                              seconds=time.perf_counter() - start)
        except a.APIStatusError as e:
            return CallResult(False, request_id=getattr(e, "request_id", None) or f"local-{uuid.uuid4()}",
                              status=e.status_code, error=f"{type(e).__name__}: {e}"[:300],
                              transient=e.status_code == 529, seconds=time.perf_counter() - start)
        res = CallResult(True, r.model, {}, r.usage.input_tokens, r.usage.output_tokens,
                         r._request_id or f"local-{uuid.uuid4()}", 200, seconds=time.perf_counter() - start)
        if r.stop_reason in ("refusal", "max_tokens"):
            res.ok, res.error = False, f"stop_reason={r.stop_reason}"
            return res
        text = next((b.text for b in r.content if b.type == "text"), "")
        try:
            res.answers = json.loads(text)
        except json.JSONDecodeError as e:
            res.ok, res.error = False, f"invalid JSON: {e}"
        return res


class FakeClaude:
    """Offline stand-in: `responder(system, user, schema) -> dict` builds the JSON answer."""

    def __init__(self, responder, model="fake-claude"):
        self.responder, self.model, self.calls, self.max_tokens = responder, model, 0, 4000

    def ask_json(self, system, user, schema, max_tokens=4000):
        self.calls += 1
        out = self.responder(system, user, schema)
        return CallResult(True, self.model, out, (len(system) + len(user)) // 4, len(json.dumps(out)) // 4,
                          f"fake-claude-{uuid.uuid4()}", 200)
