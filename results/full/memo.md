## Recommendation
Prioritize **usability** next quarter, led by `usability.excessive_ad_frequency`, then `usability.unavailable_playback_controls` and `usability.other_usability`. Run a closely related billing track on `billing.excessive_paywall_restrictions`, since the free-tier ad load and the paywall complaints overlap in the reviews. In the topic_rollup table, usability has the highest severity_sum (206389), ahead of billing (168434) and playback (132785).

## Evidence
- `usability.excessive_ad_frequency` has 33331 [C1] complaints and a priority_score of 83778 [C2].
- `billing.excessive_paywall_restrictions` has 49604 [C3] complaints and a mean_severity of 2.930288 [C4].
- `usability.other_usability` has a priority_score of 44092 [C7]. `usability.unavailable_playback_controls` has a priority_score of 40788 [C5].
- Topic_rollup complaint_count: usability 75305, billing 56811. These are different numbers, and usability is higher.
- Representative reviews: ad complaints in `9f7e2151-cb7b-4ace-8c80-dd0ff0625f93` and `4c74fc5c-c363-4efe-ad8a-10f9041ff679`. Paywall frustration in `d9bfee4f-4ec6-4972-88e5-2c4fde32ba0f`. Removed voice controls, framed as a safety concern, in `e06d93e4-fa25-4a78-879a-9de771e54b2c`.

## Alternatives considered
- **Playback:** `playback.other_playback` has a mean_severity of 3.406514 [C6], and the topic_rollup mean_severity for playback is 3.552681. Volume is lower than usability, and the issue is a catch-all bucket. Reviews such as `3d702696-8185-467c-9b17-9c6cbae8ce3e` describe unwanted autoplay, which could be scoped as a targeted fix.
- **Access:** the topic_rollup shows the highest mean_severity (3.971434) but a small severity_sum (42959). This suggests a narrow, severe problem rather than a broad quarter-long program.
- **Support:** the smallest topic in topic_rollup, with a complaint_count of 809.
- **`other.general`:** it ranks first with a priority_score of 186723 [C8], but it is general dissatisfaction with no specific product fix. Some of its evidence concerns company conduct rather than product defects. It is not one of the four candidate areas.

## Limitations
- The data are self-selected public app reviews from a historical window, so they are not representative of all users.
- Cancellation language (26098 records in run_totals intents) is stated intent, not observed churn. This memo makes no revenue, churn or causal estimates.
- Issue labels come from automated classification. The notes report an any-field disagreement rate of 0.268 on a verifier sample of 4842, so labels are noisy.
- Run_totals shows 13 quarantined records, which are excluded.
- Severity is a model-assigned score, and the priority_score weights volume and severity equally by construction.
