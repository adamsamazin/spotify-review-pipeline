"""Jev question sets for the enrich and verify roles.

A request's state holds up to 50 reviews keyed r01..r50. Each review gets four questions
(topic, intent, severity, sentiment) that point at its key. The definitions follow
data/GRADING_CONTRACT.md; prompts/labels.md is the human-readable version with examples.

Variants are separate label_configs so results are never mixed in the cache:
  inline_v1 - full option descriptions repeated in every question's criteria
  shared_v1 - definitions sent once in the state; questions carry bare option names
"""

from typesafe_sdk import Choice, Score

SCHEMA_VERSION = "schema_v1"

TOPIC_CRITERIA = {
    "access": "Login, signup, password or account access problems",
    "usability": "Navigation, controls, layout, queue or playlist management, ad interruptions",
    "playback": "Playback failure, crashes, lag, connection failures, audio quality, battery or data use",
    "downloads": "Downloading, saved music, offline listening, disappearing downloads",
    "catalog": "Missing songs or artists, search, discovery, recommendations, lyrics",
    "billing": "Price, charges, subscriptions, paywalls, premium entitlement, "
               "features or limits locked to premium (e.g. free-tier skip or shuffle limits)",
    "support": "Contacting customer support and the support response",
    "other": "General praise or criticism with no specific feature, unrelated or meaningless text",
}
TOPIC_RULE = ("If several problems are mentioned, pick the most severe; if tied, the first mentioned. "
              "For a positive review pick the first specific praised feature; general praise is other. "
              "Mentioning a paid plan alone is not billing.")

INTENT_CRITERIA = {
    "cancellation": "Explicitly leaving, uninstalling, cancelling or threatening to",
    "complaint": "Negative experience, including mixed praise and criticism or a generic 'bad app'",
    "request": "Asks for a change without reporting a failure",
    "praise": "Positive experience only",
    "unclear": "Meaningless, unrelated, or a bare boycott slogan with no product complaint",
}
INTENT_RULE = "If several apply, choose the first in this order: cancellation, complaint, request, praise, unclear."

SEVERITY_CRITERIA = {
    "1": "No reported problem: praise, neutral or unclear text, or a pure feature request",
    "2": "Dislike, generic criticism, minor annoyance or cosmetic issue; no functional loss",
    "3": "A degraded or restricted function; some use or a workaround remains",
    "4": "A core task clearly blocked, such as cannot log in or cannot play music",
    "5": "Explicit serious financial, privacy or data harm; price, a crash or angry words alone are not enough",
}

SENTIMENT_LEVELS = ["Very negative", "Somewhat negative", "Neutral or mixed", "Somewhat positive", "Very positive"]

DEFINITIONS = {  # shared_v1 sends this once per request in the state
    "topic": {**TOPIC_CRITERIA, "rule": TOPIC_RULE},
    "intent": {**INTENT_CRITERIA, "rule": INTENT_RULE},
    "severity": SEVERITY_CRITERIA,
}

VARIANTS = ("inline_v1", "shared_v1")
VERIFY_VARIANT = "verify_v1"  # independent wording for the verifier role
FIELDS = ("topic", "intent", "severity", "sentiment")


def review_key(i):
    return f"r{i + 1:02d}"


def build_state(texts, variant):
    reviews = {review_key(i): t for i, t in enumerate(texts)}
    if variant == "shared_v1":
        return {"definitions": DEFINITIONS, "reviews": reviews}
    return {"reviews": reviews}


def questions_for(key, variant, prefix=""):
    """Four questions about `reviews.<key>`. Returns {question_id: Question}."""
    ref = f"`reviews.{key}`"
    if variant == "inline_v1":
        topic = Choice(instructions=f"What is the primary topic of the app review {ref}? {TOPIC_RULE}",
                       criteria=TOPIC_CRITERIA)
        intent = Choice(instructions=f"What is the intent of the app review {ref}? {INTENT_RULE}",
                        criteria=INTENT_CRITERIA)
        severity = Choice(instructions=f"How severe is the problem reported in the app review {ref}?",
                          criteria=SEVERITY_CRITERIA)
    elif variant == "shared_v1":
        topic = Choice(instructions=f"Primary topic of {ref}, using `definitions.topic`.",
                       criteria=dict.fromkeys(TOPIC_CRITERIA))
        intent = Choice(instructions=f"Intent of {ref}, using `definitions.intent`.",
                        criteria=dict.fromkeys(INTENT_CRITERIA))
        severity = Choice(instructions=f"Severity of the problem in {ref}, using `definitions.severity`.",
                          criteria=dict.fromkeys(SEVERITY_CRITERIA))
    elif variant == "verify_v1":
        # Verifier: inline rubric with its own wording; it never sees the enricher's answer.
        topic = Choice(instructions=f"Read the app review {ref}. Which product area is it mainly about? "
                                    f"{TOPIC_RULE}", criteria=TOPIC_CRITERIA)
        intent = Choice(instructions=f"Read the app review {ref}. What is the reviewer doing? {INTENT_RULE}",
                        criteria=INTENT_CRITERIA)
        severity = Choice(instructions=f"Read the app review {ref}. Using only what the text states, "
                                       f"how much harm or loss of function is reported?", criteria=SEVERITY_CRITERIA)
    else:
        raise ValueError(f"unknown variant {variant}")
    sentiment = Score(instructions=f"Overall sentiment of the app review {ref}", criteria=SENTIMENT_LEVELS)
    return {f"{prefix}{key}.topic": topic, f"{prefix}{key}.intent": intent,
            f"{prefix}{key}.severity": severity, f"{prefix}{key}.sentiment": sentiment}


def build_request(texts, variant):
    state = build_state(texts, variant)
    questions = {}
    for i in range(len(texts)):
        questions.update(questions_for(review_key(i), variant))
    return state, questions
