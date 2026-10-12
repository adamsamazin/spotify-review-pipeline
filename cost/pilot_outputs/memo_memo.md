## Recommendation
Put next quarter's effort into **usability**, focused on free-tier experience: `usability.excessive_ad_frequency`, `usability.unavailable_playback_controls` and `usability.interface_and_ui_problems`. Review the paywall policy behind `billing.excessive_paywall_restrictions` alongside it. Many reviews tie missing controls and ads to the premium upsell, so the two may need one joint decision.

## Evidence
- In topic_rollup, usability has complaint_count 16, severity_sum 46 and mean_severity 2.875000, the largest severity_sum of any topic.
- `other.general` ranks first with 11 [C1] complaints and priority_score 21 [C2]. It is generic dissatisfaction (e.g. `06a45bd5-3ed9-43af-b7f2-8b9487e2ffff`), so it gives no actionable direction.
- `billing.excessive_paywall_restrictions` ranks second with 7 [C3] complaints, mean_severity 2.857143 [C4] and priority_score 20 [C5]. This is below `other.general` on priority_score. Example: `a78d831a-69f4-428a-9235-cfdd9775c509`.
- `usability.excessive_ad_frequency` has 6 [C6] complaints and priority_score 16 [C7]. Example: `c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd`.
- `usability.interface_and_ui_problems` has priority_score 15 [C8] and mean_severity 3.000000 [C9]. Reviews cite updates that removed basic features: `7084ced1-0428-4093-9328-442f74719b4f`.
- `usability.unavailable_playback_controls` has 4 [C10] complaints and mean_severity 3.000000 [C11], the same mean_severity as the interface issue. Example: `a3605554-5c3a-441d-836e-e9fdea83eb2e`, which describes skip and previous-song removal for non-subscribed users.
- Run_totals shows complaint_or_cancellation 50 out of records 100.

## Alternatives considered
- **Access:** `access.login_authentication_failures` has only 2 [C12] complaints but the highest mean_severity at 4.000000 [C13]; see `32fb340f-4f9f-4551-8dae-755221e58d6a`. The topic_rollup shows access with complaint_count 2 and severity_sum 8. Worth a targeted fix, but it is small in volume.
- **Playback (topic):** topic_rollup lists playback with complaint_count 7, severity_sum 25 and mean_severity 3.571429. That is higher per complaint than usability's 2.875000 but lower in total.
- **Billing/support:** topic_rollup shows billing with complaint_count 7 and severity_sum 20, and support with complaint_count 1 and severity_sum 2. Billing is covered by the joint paywall review above.

## Limitations
The data are self-selected public app reviews from a historical window, so they do not represent all users. Cancellation language is stated intent, not observed churn (e.g. `035213ba-b1b9-411c-b028-70296e5f0e73`). This memo makes no revenue, churn or causal estimates. The verifier notes report verifier_any_field_disagreement_rate 0.15, so some labels may be wrong. Issue categorisation is imperfect: related free-tier restriction complaints are split between billing and usability.
