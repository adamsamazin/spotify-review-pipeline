## Recommendation

Prioritize **usability** next quarter, centered on `usability.excessive_ad_interruptions` and `usability.ui_redesign_usability_issues`. Treat `billing.premium_paywall_expansion` as a closely related second track, since ad and paywall complaints often appear together in reviews.

In the topic_rollup table, usability has the largest severity_sum (170) and the largest complaint_count (63), with a mean_severity of 2.698413.

## Evidence

- `usability.excessive_ad_interruptions` has 73 [C1] priority score, and `usability.ui_redesign_usability_issues` has 43 [C2] priority score. Representative reviews: `3bfefa06-133c-419b-a435-1fea919d6a44` and `71095e1c-86d0-4639-8db0-9b74afdf6d4e` (ad load), and `45c561b9-cc47-4d80-95d3-f0d20bc84af3` (update made the app unusable for the reviewer).
- `billing.premium_paywall_expansion` has 31 [C3] complaints and a mean severity of 2.935484 [C4]. See `890aeb60-e7cf-4f0d-a321-03a1c8b65757`.
- `other.general` has the highest-ranked priority score, 120 [C5], but it is a catch-all of general dissatisfaction with no specific fix to scope. I do not recommend it as a work item.
- In topic_rollup, billing has severity_sum 139 and playback has severity_sum 133. Playback has the highest mean_severity of the three large topics (3.694444). `playback.other_playback` has a mean severity of 3.714286 [C6]. See `f1abd13b-2391-4b04-8109-efa7f3cfed0b` for intermittent stopping.
- run_totals reports 237 complaint_or_cancellation records, of which 25 are cancellation intents (intents table). These are stated intent, not observed churn.

## Alternatives considered

- **Billing/support:** `billing.premium_paywall_expansion` is the strongest single actionable issue after the catch-all. Billing as a topic (topic_rollup) has complaint_count 46 and severity_sum 139, below usability on both. Support has complaint_count 1 in topic_rollup, so there is little evidence for dedicated support investment.
- **Playback:** Complaints are fewer but more severe per review. `playback.intermittent_playback_failures` has a mean severity of 3.545455 [C7]. This is a strong candidate if reliability is weighted over breadth.
- **Access:** topic_rollup shows the highest mean_severity of any topic (4.100000) but complaint_count of only 10 and severity_sum of 41. No access issue appears in the ranking table, so I cannot compare it at issue level.

## Limitations

- The data are self-selected public app reviews from a historical window and may not represent all users.
- Severity values and issue labels come from the pipeline's classification, and the ranking multiplies count by mean severity, so it favors frequent issues over rare severe ones.
- Cancellation language is stated intent only. This memo makes no revenue, churn or causal estimates.
- Ads and paywall complaints may overlap in cause, so the usability and billing boundaries are imperfect.
