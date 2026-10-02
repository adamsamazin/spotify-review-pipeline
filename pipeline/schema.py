"""Code-owned parts of a record: mapping Jev answers into the shared schema, deterministic
evidence quotes and entities, consistency rules, and validation."""

import re

from pipeline.contract import INTENT_PRECEDENCE, TOPICS

POST_VERSION = "post_v2"  # recorded per record; not part of label_config (model+prompt+schema)
QUOTE_FULL_TEXT_MAX = 280     # short reviews: the whole text is the evidence quote
NEEDS_REVIEW_MAX_PROB = 0.60  # flag when a top option is below this; ~19% of checkpoint_500 (dev data)

# Feature terms matched in code for `entities` and for choosing the quote sentence of long reviews.
LEXICON = {
    "access": ["login", "log in", "logged out", "sign in", "signup", "sign up", "password", "account",
               "facebook", "google login", "verification", "email"],
    "usability": ["ads", "advert", "commercial", "interface", "ui", "layout", "navigation", "button",
                  "queue", "playlist", "library", "home screen", "update", "design", "widget", "dj"],
    "playback": ["crash", "freez", "lag", "stops playing", "pause", "buffer", "connection", "bluetooth",
                 "android auto", "car", "audio", "sound", "quality", "battery", "background", "glitch", "bug"],
    "downloads": ["download", "offline", "saved", "storage", "sd card", "cache"],
    "catalog": ["song", "artist", "album", "podcast", "search", "recommend", "discover", "lyrics",
                "audiobook", "radio", "genre", "music selection"],
    "billing": ["premium", "price", "subscription", "pay", "charged", "refund", "free trial", "family plan",
                "duo", "student", "skip", "shuffle", "paywall", "money", "cost"],
    "support": ["support", "customer service", "help center", "contact", "response", "agent", "chat"],
}
_TERMS = sorted({t for terms in LEXICON.values() for t in terms}, key=len, reverse=True)
_TERM_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in _TERMS) + r")", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*", re.UNICODE)


def entities(text):
    seen = []
    for m in _TERM_RE.finditer(text):
        term = m.group(1).lower()
        if term not in seen:
            seen.append(term)
    return seen


def evidence_quote(text, topic):
    """An exact substring of the review. Long reviews: the sentence with most topic terms."""
    if len(text) <= QUOTE_FULL_TEXT_MAX:
        return text
    terms = LEXICON.get(topic, [])
    best, best_hits = None, -1
    for m in _SENTENCE_RE.finditer(text):
        sent = m.group(0).strip()
        if len(sent) < 8:
            continue
        hits = sum(sent.lower().count(t) for t in terms)
        if hits > best_hits:
            best, best_hits = sent, hits
    quote = best if best and best_hits > 0 else text[:QUOTE_FULL_TEXT_MAX].rstrip()
    return quote if quote in text else text


def top_prob(answer):
    return max(answer["probabilities"].values())


def to_record(text, answers):
    """answers: {'topic': {...}, 'intent': {...}, 'severity': {...}, 'sentiment': {...}} raw Jev dicts."""
    topic = answers["topic"]["choice"]
    intent = answers["intent"]["choice"]
    severity = int(answers["severity"]["choice"])
    sentiment = round(answers["sentiment"]["score"] / 2 - 1, 3)  # Score 0..4 -> -1..1
    rules = []
    # Shared definitions: severity 1 means no reported problem, which is what praise/request/unclear mean;
    # a complaint is a negative experience, so at least severity 2.
    if intent in ("praise", "request", "unclear") and severity != 1:
        rules.append(f"severity {severity}->1 for intent={intent}")
        severity = 1
    if intent == "complaint" and severity == 1:
        rules.append("severity 1->2 for intent=complaint")
        severity = 2
    low = [f for f in ("topic", "intent", "severity") if top_prob(answers[f]) < NEEDS_REVIEW_MAX_PROB]
    return {
        "topic": topic, "intent": intent, "sentiment": sentiment, "severity": severity,
        "entities": entities(text), "evidence_quote": evidence_quote(text, topic),
        "needs_review": bool(low),
        "detail": {
            "probabilities": {f: answers[f]["probabilities"] for f in ("topic", "intent", "severity", "sentiment")},
            "confidence": {f: answers[f].get("confidence") for f in ("topic", "intent", "severity", "sentiment")},
            "sentiment_score": answers["sentiment"]["score"],
            "low_confidence_fields": low,
            "rules_applied": rules,
            "post_version": POST_VERSION,
        },
    }


def validate(rec, text):
    """Return a list of problems; empty means the record is valid."""
    p = []
    if rec.get("topic") not in TOPICS:
        p.append(f"topic {rec.get('topic')!r} not allowed")
    if rec.get("intent") not in INTENT_PRECEDENCE:
        p.append(f"intent {rec.get('intent')!r} not allowed")
    s = rec.get("severity")
    if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= 5:
        p.append(f"severity {s!r} not an integer 1-5")
    v = rec.get("sentiment")
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not -1 <= v <= 1:
        p.append(f"sentiment {v!r} not in [-1, 1]")
    if not isinstance(rec.get("entities"), list):
        p.append("entities not a list")
    q = rec.get("evidence_quote")
    if not isinstance(q, str) or not q or q not in text:
        p.append("evidence_quote not an exact source substring")
    if not isinstance(rec.get("needs_review"), bool):
        p.append("needs_review not a boolean")
    return p
