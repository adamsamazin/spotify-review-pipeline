# Golden-50 evaluation: `probe_golden_shared`

label_config: `jev-1.13.0+enrich_shared_v1+schema_v1+post_v1`

Completed 50/50; ambiguous (human-marked) 15.

| Metric | Value |
|---|---|
| Topic agreement | 78% |
| Intent agreement | 88% |
| Severity exact | 78% |
| Severity MAE | 0.28 |
| Sentiment within ±0.5 | 94% |
| Sentiment MAE | 0.133 |
| Evidence quote exact substring | 100% |

Excluding ambiguous cases: topic 86%, intent 94%, severity 83%, sentiment 100%

needs_review as an error predictor: {'flagged': 1, 'records_with_label_errors': 21, 'precision': 0.0, 'recall': 0.0}

## Disagreements

| # | text | field | gold | pred | amb |
|---|---|---|---|---|---|
| 1 | Staff must be full of mentally ill kool-aid heads. Banning conservativ | topic | other | catalog |  |
| 2 | Great app use it every chance I get | topic | access | other |  |
| 9 | Spotify is awesome and and very diverse :) | topic | catalog | other | y |
| 10 | Duo Premium .... No ads at all! | topic | usability | billing |  |
| 12 | Update: I reached out to Spotify Support and with some help from Sarah | severity | 3 | 4 |  |
| 14 | Great... | intent | unclear | praise | y |
| 14 | Great... | sentiment | 0.0 | 0.655 | y |
| 16 | I like it but god I hate it when the music Interrupts my ads | sentiment | 0.5 | -0.145 | y |
| 17 | Lhat ng song nasa spotify | topic | other | catalog |  |
| 17 | Lhat ng song nasa spotify | intent | unclear | complaint |  |
| 17 | Lhat ng song nasa spotify | severity | 1 | 3 |  |
| 19 | asem, lirik nya kdang gaada kek mana?? | topic | other | catalog | y |
| 19 | asem, lirik nya kdang gaada kek mana?? | intent | unclear | complaint | y |
| 19 | asem, lirik nya kdang gaada kek mana?? | severity | 1 | 3 | y |
| 24 | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | intent | complaint | request |  |
| 24 | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | severity | 2 | 1 |  |
| 28 | Unconditional love, Stoli Canales | intent | praise | unclear | y |
| 28 | Unconditional love, Stoli Canales | sentiment | 1.0 | 0.255 | y |
| 29 | Deleting this App. The new update suck, we can't choose our fvrt songs | topic | billing | usability | y |
| 29 | Deleting this App. The new update suck, we can't choose our fvrt songs | severity | 2 | 3 | y |
| 30 | It's my best music app but now it's not...everything basic features is | severity | 2 | 3 |  |
| 31 | I hate this app and sweden .I love islam | intent | unclear | complaint | y |
| 31 | I hate this app and sweden .I love islam | severity | 1 | 2 | y |
| 32 | What is happening with Spotify?? Recently I'm trying to play a song bu | topic | access | playback | y |
| 33 | Are you out of your mind? This is dangerous! Listening to music in a n | severity | 3 | 5 | y |
| 34 | Beth, we all got to give me a free dollar to go with 3 months, bro I c | topic | other | billing |  |
| 43 | I gave one star because I can't give any less than that. the new updat | severity | 3 | 4 |  |
| 44 | I find Spotify very good, it finds and play whatever music you want an | topic | playback | catalog | y |
| 45 | paying for subscribing but unable to play in offline mode really? | topic | playback | downloads | y |
| 46 | Worst app ever too much ad | severity | 2 | 3 |  |
| 47 | Too expensive and the free version is pretty much unusable with consta | severity | 2 | 3 | y |
