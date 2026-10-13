# Evidence quote and entity check (full run)

- Entities: 531,454 on 484,189 directly labelled records; **0 not found in the review text**.
- Quotes: **0** not exact substrings (also confirmed by `check_submission.py`).
- Quote support, seeded sample of 20 long reviews (population 39,236), **judged by the assistant, not a human**: 15 support, 4 partial, 1 do not support.

| # | review_id | label | verdict | reason |
|---|---|---|---|---|
| 1 | `3ce8d966` | usability/complaint/3 | supports | ads in the free tier = usability |
| 2 | `8e2bd7f8` | billing/cancellation/3 | partial | quote supports billing (premium paywall); the cancellation wording is later in the review, outside the quote |
| 3 | `9a33ec2e` | billing/praise/1 | supports | first specific praised feature is price = billing praise |
| 4 | `80aebf51` | other/praise/1 | partial | supports praise, but the praised feature (AI DJ) arguably makes the topic catalog, not other |
| 5 | `842c6f03` | usability/complaint/3 | does_not_support | 'this update is so disgusting' is generic; the specific problem (choosing songs/loop locked to premium) is in the next sentence and points to billing |
| 6 | `8cf3e66d` | usability/complaint/3 | supports | navigation worse after update = usability |
| 7 | `4a3e0aa6` | usability/complaint/3 | supports | ads every song = usability |
| 8 | `b4c0ea1c` | billing/cancellation/3 | supports | shuffle can't be turned off without premium = billing |
| 9 | `37d5b7ed` | usability/complaint/3 | supports | too many ads = usability |
| 10 | `6f292da6` | other/praise/1 | supports | general long-time praise = other |
| 11 | `1205eec9` | billing/complaint/3 | supports | pay to read lyrics = billing |
| 12 | `ff45ba62` | playback/complaint/4 | supports | podcasts won't play / crash = playback, core task blocked |
| 13 | `1f8d1bdc` | billing/cancellation/4 | supports | previous/next locked to premium = billing; deletion intent follows the quote |
| 14 | `5cf85c8f` | catalog/request/1 | supports | asks for artist stations = catalog request |
| 15 | `40987a24` | usability/complaint/3 | partial | supports the complaint, but free-tier skip/shuffle limits are billing under the contract, not usability |
| 16 | `0dffcb5c` | billing/request/1 | partial | supports billing (premium-only shuffle); intent 'request' is debatable since limits are called annoying |
| 17 | `c3665fcb` | playback/complaint/3 | supports | songs pause repeatedly = playback degraded |
| 18 | `9ddc33ce` | billing/complaint/3 | supports | premium-only listening and cost = billing |
| 19 | `42d6271a` | billing/cancellation/3 | supports | premium-only features + deleted app = billing cancellation |
| 20 | `9b51ab84` | usability/complaint/3 | supports | interface and inconsistent controls = usability |

**Finding:** Quote selection picks the sentence with the most topic keywords; when the specific problem is stated in a later sentence (case 5) or the label is itself debatable (cases 4, 15, 16), the quote can be weaker evidence than the full review. Two partial cases (15, 16) reflect the known usability/billing boundary for free-tier limits.
