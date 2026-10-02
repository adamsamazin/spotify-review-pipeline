"""Interactive helper for hand-labeling the golden 50. Human labels only, no model calls.

    .venv\\Scripts\\python evals\\label_golden.py            # label / resume
    .venv\\Scripts\\python evals\\label_golden.py --redo ID  # relabel one review
    .venv\\Scripts\\python evals\\label_golden.py --review   # print a summary of saved labels

Saves after every review to evals/golden_50_labeled.csv; quit any time with q.
These labels are evaluation answers: never paste them into prompts or examples.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "golden_50_to_label.csv"
OUT = ROOT / "evals" / "golden_50_labeled.csv"
LABEL_COLS = ["topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review"]
EXTRA_COLS = ["ambiguous", "notes"]

TOPICS = {
    "1": ("access", "login, signup, password, account access"),
    "2": ("usability", "navigation, controls, layout, queue/playlist mgmt, ad interruptions"),
    "3": ("playback", "playback failure, crashes, lag, connection, audio quality, battery/data"),
    "4": ("downloads", "downloading, saved music, offline, disappearing downloads"),
    "5": ("catalog", "missing songs/artists, search/discovery, recommendations, lyrics"),
    "6": ("billing", "price, charges, subscriptions, paywalls, premium entitlement, premium-only controls"),
    "7": ("support", "contacting support and the support response"),
    "8": ("other", "general praise/criticism, unrelated, no supported specific topic"),
}
INTENTS = {
    "1": ("cancellation", "explicitly leaving/uninstalling/cancelling or threatening to"),
    "2": ("complaint", "negative experience, incl. mixed praise+criticism, generic 'bad app'"),
    "3": ("request", "desired change, no reported failure"),
    "4": ("praise", "positive"),
    "5": ("unclear", "meaningless/unrelated text, bare boycott slogans"),
}
SEVERITY = {
    "1": "no problem: praise, neutral/unclear, pure feature request",
    "2": "dislike, generic criticism, minor annoyance, cosmetic; no functional loss",
    "3": "degraded/restricted function; some use or workaround remains",
    "4": "core task clearly blocked (can't log in, can't play music)",
    "5": "explicit serious financial, privacy or data harm (price/crash/anger alone is NOT enough)",
}
SENTIMENT = {"1": -1.0, "2": -0.5, "3": 0.0, "4": 0.5, "5": 1.0}

RULES = """Rules: highest-severity problem wins; tie -> first specific problem mentioned.
Positive review -> first specific praised feature; general praise = other.
Paid-plan mention alone is NOT billing. Stars are metadata: judge the text only."""


class Quit(Exception):
    pass


def ask(prompt, valid=None, default=None):
    while True:
        raw = input(prompt).strip()
        if raw.lower() == "q":
            raise Quit
        if not raw and default is not None:
            return default
        if valid is None or raw in valid:
            return raw
        print("  ? not a valid choice")


def menu(title, options):
    print(f"\n{title}")
    for k, v in options.items():
        name, desc = v if isinstance(v, tuple) else (k, v)
        print(f"  {k}) {name:<13} {desc}" if isinstance(v, tuple) else f"  {k}) {desc}")


def label_one(row, n, total):
    text = row["review_text"]
    print("\n" + "=" * 78)
    print(f"[{n}/{total}] {row['review_id']}   (stars: {row['review_rating']} - metadata only)")
    print("-" * 78)
    print(text)
    print("-" * 78)
    print(RULES)

    menu("TOPIC", TOPICS)
    topic = TOPICS[ask("topic 1-8: ", TOPICS)][0]
    menu("INTENT (precedence top to bottom)", INTENTS)
    intent = INTENTS[ask("intent 1-5: ", INTENTS)][0]
    menu("SEVERITY", SEVERITY)
    severity = int(ask("severity 1-5: ", SEVERITY))

    print("\nSENTIMENT  1) -1 very negative  2) -0.5  3) 0 neutral/mixed  4) +0.5  5) +1 very positive")
    while True:
        raw = ask("sentiment 1-5 (or a number from -1 to 1): ")
        if raw in SENTIMENT:
            sentiment = SENTIMENT[raw]
            break
        try:
            sentiment = float(raw)
            if -1 <= sentiment <= 1:
                break
        except ValueError:
            pass
        print("  ? enter 1-5 or a number between -1 and 1")

    print("\nEVIDENCE QUOTE: exact substring of the review that supports your labels.")
    while True:
        quote = input("quote (Enter = whole review text): ")
        if quote.strip().lower() == "q":
            raise Quit
        quote = quote or text
        if quote in text:
            break
        print("  ? not an exact substring of the review (copy/paste a piece of it)")

    ents = input("\nENTITIES: features/products named in the text, comma-separated (Enter = none): ").strip()
    if ents.lower() == "q":
        raise Quit
    entities = json.dumps([e.strip() for e in ents.split(",") if e.strip()], ensure_ascii=False)

    needs_review = ask("\nNEEDS_REVIEW - missing context / can't tell impact? y/N: ",
                       {"y", "n", "Y", "N"}, "n").lower() == "y"
    ambiguous = ask("AMBIGUOUS - would another careful labeler reasonably pick differently? y/N: ",
                    {"y", "n", "Y", "N"}, "n").lower() == "y"
    notes = input("notes (why, esp. if ambiguous; Enter = none): ").strip()
    if notes.lower() == "q":
        raise Quit
    return {"topic": topic, "intent": intent, "sentiment": sentiment, "severity": severity,
            "entities": entities, "evidence_quote": quote, "needs_review": str(needs_review).lower(),
            "ambiguous": str(ambiguous).lower(), "notes": notes}


def load():
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as f:
            saved = {r["review_id"]: r for r in csv.DictReader(f)}
        for r in rows:
            if r["review_id"] in saved:
                r.update({k: saved[r["review_id"]].get(k, "") for k in LABEL_COLS + EXTRA_COLS})
    return rows


def save(rows):
    cols = list(rows[0].keys())
    for c in EXTRA_COLS:
        if c not in cols:
            cols.append(c)
    tmp = OUT.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(OUT)  # atomic: a crash never leaves a half-written file


def summary(rows):
    from collections import Counter
    done = [r for r in rows if r.get("topic")]
    print(f"labeled {len(done)}/{len(rows)}")
    for col in ("topic", "intent", "severity", "needs_review", "ambiguous"):
        print(f"  {col:<13}", dict(Counter(r[col] for r in done)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redo", help="review_id to relabel")
    ap.add_argument("--review", action="store_true", help="print a summary and exit")
    args = ap.parse_args()
    rows = load()
    if args.review:
        return summary(rows)
    todo = [r for r in rows if (r["review_id"] == args.redo) if args.redo] or \
           ([] if args.redo else [r for r in rows if not r.get("topic")])
    if args.redo and not todo:
        sys.exit(f"review_id {args.redo} not found")
    done = len(rows) - len([r for r in rows if not r.get("topic")])
    print(f"{done}/{len(rows)} already labeled. Type q at any prompt to save and quit.")
    try:
        for r in todo:
            r.update(label_one(r, rows.index(r) + 1, len(rows)))
            save(rows)
    except (Quit, KeyboardInterrupt, EOFError):
        print("\nSaved. Run again to resume.")
    summary(rows)


if __name__ == "__main__":
    main()
