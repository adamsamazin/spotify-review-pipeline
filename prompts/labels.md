# Shared labels, severity rubric and worked examples

These are the common definitions from `data/GRADING_CONTRACT.md` as applied in this project.
The machine-readable versions sent to Jev are in [`pipeline/questions.py`](../pipeline/questions.py)
(`shared_v1` for enrichment, `verify_v1` for the verifier). Examples below come from the
**development** file `analysis_10000.csv` (rows 501+), never from the golden 50. IDs are shortened
to the first 8 characters.

## Topics (exactly one per review)

| topic | Covers | Not this topic |
|---|---|---|
| `access` | login, signup, password, account access | a paid plan mentioned in passing |
| `usability` | navigation, controls, layout, queue/playlist management, ad interruptions | controls that are explicitly locked to premium (→ billing) |
| `playback` | playback failure, crashes, lag, connection failures, audio quality, battery/data use | downloads failing offline (→ downloads) |
| `downloads` | downloading, saved music, offline listening, disappearing downloads | |
| `catalog` | missing songs/artists, search/discovery, recommendations, lyrics availability | |
| `billing` | price, charges, subscriptions, paywalls, premium entitlement, premium-only controls | music crashing for a paying user (→ playback) |
| `support` | contacting support and the support response | |
| `other` | general praise/criticism, unrelated content, no supported specific topic | |

**Tie rules:** pick the problem with the highest supported severity; on a tie, the first specific
problem mentioned. For positive reviews, the first specific praised feature; general praise is `other`.

## Intent (precedence order)

`cancellation` (explicitly leaving, uninstalling, cancelling, or threatening to) → `complaint`
(negative experience, including mixed praise/criticism and generic "bad app") → `request`
(desired change without a reported failure) → `praise` → `unclear` (meaningless/unrelated text,
bare boycott slogans).

## Severity (1-5)

| | Meaning |
|---|---|
| 1 | No reported problem: praise, neutral/unclear content, or a pure feature request |
| 2 | Dislike, generic criticism, minor annoyance, cosmetic issue; no functional loss |
| 3 | Degraded or restricted function; some use or a workaround remains |
| 4 | A core task clearly blocked (cannot log in, cannot play music) |
| 5 | Explicit serious financial, privacy or data harm. Price, a crash, or angry words alone are not enough |

Stars are metadata only and never decide intent or severity. Cancellation intent does not by
itself raise severity. Missing context sets `needs_review`.

**Code-enforced consistency rules** (`pipeline/schema.py`, recorded in each record's `rules_applied`):
praise/request/unclear → severity 1; complaint with severity 1 → severity 2.

## Worked examples (development data)

| ID | Review (excerpt) | topic | intent | sev | Why |
|---|---|---|---|---|---|
| `4d154e8f` | "I can't log in with Google pleas help" | access | complaint | 4 | Login is a core task and it is blocked |
| `df50af34` | "Too many ads Do something 'bout it" | usability | complaint | 2 | Ad interruptions are usability; annoyance, no functional loss |
| `db73c4f7` | "without premium there is no queue, no repeat, no way to go to previous song" | billing | complaint | 3 | Controls explicitly locked to premium → billing; restricted function, playback still possible |
| `8cf70f3f` | "always crashing down; unable to play and just stop working" | playback | complaint | 4 | Cannot play music: core task blocked |
| `9397488c` | "Why does it constantly need internet to open up downloaded playlists?" | downloads | complaint | 3 | Offline listening degraded; online use remains |
| `12b0406d` | "The quality of recommendations keeps going down" | catalog | complaint | 2 | Recommendations; dislike without functional loss |
| `26c74111` | "...awful music recommendations, subpar audio quality, obnoxious ads, and useless customer support" | catalog | complaint | 2 | Several generic criticisms of equal severity → first specific problem mentioned |
| `2de6923d` | "Works well and customer service is great" | support | praise | 1 | First specific praised feature is support |
| `305c3fe1` | "Unable to login, can not reach tech support. Looks like the account was hacked." | access | complaint | 5 | Explicit account-security (privacy/data) harm outranks the login block |
| `b116e1c4` | "...Its premium membership is also a scam" | billing | complaint | 2 | "Scam" is angry wording, not an explicit financial harm |
| `f11035b1` | "No sound, bad sound quality!! ... Have just uninstalled" | playback | cancellation | 4 | Uninstalled → cancellation takes precedence; no sound blocks listening |
| `cbc5d976` | "Please add feature where we can play the songs which are Saved..." | usability | request | 1 | Desired change with no reported failure |
| `84b770bb` | "Good app. Highly recommended" | other | praise | 1 | General praise ("recommended" here is not the recommendations feature) |

Hard cases are kept, not dropped: multilingual reviews are classified from the text as written,
and low-confidence answers set `needs_review` (top option probability below 0.60).
