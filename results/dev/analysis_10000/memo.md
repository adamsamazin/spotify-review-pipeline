## Recommendation

Prioritise **usability** for the next quarter, with the free-tier paywall and ad experience as the lead workstream. Among the four candidate areas, usability has the highest topic severity_sum, 3271 (topic_rollup). Billing is next at 2541 (topic_rollup), then playback at 2145 and access at 622 (both topic_rollup).

Within that, scope two issues first: `billing.excessive_paywall_restrictions` and `usability.excessive_ad_frequency`. Treat playback reliability as a second-line item. Treat access and support as monitor-only.

## Evidence

- `billing.excessive_paywall_restrictions` has 753 [C1] complaints and a priority_score of 2201 [C2], with a mean_severity of 2.922975 [C3]. It is the highest-ranked issue within the four themes.
- `usability.excessive_ad_frequency` has 521 [C4] complaints and a priority_score of 1304 [C5].
- `other.general` ranks first overall with a priority_score of 2701 [C8]. It is a catch-all of general dissatisfaction and privacy complaints, not a scoped product area, so I do not recommend it as the main workstream. Samples such as `21ddfe12-8433-4bad-b0f8-e7f605c056ae` suggest a privacy sub-theme that could be split out.
- `playback.other_playback` has the highest mean_severity among the ranked issues shown, 3.431734 [C6]. Its volume is lower than the paywall and ad issues. Example: `0c8b53c5-0c87-496f-b124-1d7457781ed8`.
- Paywall examples: `fbb8cab0-eb66-49de-9624-a06015514118` and `986e5431-3132-4496-9a79-f1d1ad99e858`.
- Ad examples: `ee11e1df-cb73-4c3a-b5e8-7268c7872b01` and `3e3b92ef-dc95-4ddd-97e4-5b992c60db26`.
- Locked controls, `usability.unavailable_playback_controls`, have a priority_score of 698 [C7]. Example: `e85607c3-a8b4-4a61-a548-a58b17b0eae1`.
- Run_totals shows 4446 complaint_or_cancellation records out of 10000 records.

## Alternatives considered

- **Billing/support as the lead area:** the paywall issue is the strongest single scoped issue. However, the support topic is small (complaint_count 12 in topic_rollup), so the billing signal is mainly about paywalling, not support handling.
- **Playback:** playback has a high topic mean_severity of 3.563123 (topic_rollup) but a lower topic severity_sum than usability or billing.
- **Access:** access has the highest topic mean_severity, 3.987179 (topic_rollup), but only 156 complaints (topic_rollup). It could warrant a targeted fix for severe cases rather than a quarter-long effort.

## Limitations

- Reviews are self-selected public app reviews from a historical window, so they may not represent all users.
- Cancellation language is stated intent, not observed churn. For example, `7913fe22-645a-4f46-a3be-7bd1ed3c8953` mentions canceling. This memo makes no revenue, churn or causal estimates.
- The verifier notes report an any-field disagreement rate of 0.189, so the classifications are noisy.
- Topic boundaries overlap: locked playback controls and paywall restrictions are related but sit in different topics, so the topic rollups should be read with that in mind.
