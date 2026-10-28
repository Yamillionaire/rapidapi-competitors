# Candidate Registry

Every candidate the pipeline has scored, with status. Scores follow the
rubric in `PIPELINE.md`. Full evidence for waves 1-2 lives in the report at
`~/workspace/goals/monetize-my-instagrams-and-facebook/files/rapidapi-competitor-targets-2026-10-28.md`.

## LIVE (built, deployed, published 2026-10-28)

| Candidate | Product | Subs | Rating | Score at pick |
|---|---|---|---|---|
| Yahu Financials (58,328) | EDGAR Fundamentals | 58,328 | 2/5 | 88 |
| Currency Exchange (22,987) | StableFX Currency Rates | 22,987 | 3/5 | 90 |
| E-mail Check (5,540) | CleanList Email Verifier | 5,540 | 4/5 | 74 |

## QUEUED (scored, awaiting the user's build tap)

| # | Candidate | Subs | Rating | Pricing | Undercut plan | Score | Notes |
|---|---|---|---|---|---|---|---|
| 4 | GeoDB Cities (wirefreethought) | 50,222 | 3/5 (60) | $20/$40/$80 | Basic free x2 quota; $10/$30/$70 | 86 | WAVE 3, live-verified 2026-10-28. Three complaint themes: recurring outages, cities wrong/missing/deleted, silent provider. Build: GeoNames (CC BY) + Wikidata (CC0) + tzdb; needs a real correction pipeline, the heaviest build in the queue. |
| 5 | Article Extractor and Summarizer (restyler) | 11,784 | 3/5 | $15/$95/$195 | $5/$85/$185 | 82 | Years of unanswered 503/403/401 complaints, service level 74%. Build: open-source extraction + Gemini API, $0. Lightest strong build in the queue. |
| 6 | Paraphrasing / Rewriter (NeuralWriter) | 5,632 | 3/5 | Ultra $19.99, Mega $34.99 | $9.99/$24.99 | 68 | 9,978ms latency against a "Very Fast" claim. Gemini wrapper. |
| 7 | WordsAPI (dpventures) | 1,561 | 2/5 (53) | $10/$49/$89 | Pro FREE; $39/$79 | 66 | WAVE 3, live-verified. Valid keys get 403s; Discussions abandoned (spam sitting unmoderated). Cleanest build in the queue: WordNet + Wiktionary + CMU dict, static data. |
| 8 | Google Translate (Hark Translate) | 5,975 | 4/5 (41 votes) | $9/$19/$39 | Ultra $9, Mega $29 | 66 | Fresh "API unreachable" complaint, unanswered. Service level 84%. Gemini wrapper. |
| 9 | Google News (BFD) | 7,316 | 3/5 | $25/$50/$100 | $15/$40/$90 | 64 | Invalid JSON and broken image proxy complaints. RSS-based build. |

## WATCHLIST

| Candidate | Subs | Why held |
|---|---|---|
| Alpha Vantage | 33,812 | Complaints are two 7-year-old forex threads; provider is the brand owner; overlaps EDGAR Fundamentals. |
| Weather (Api Dojo weather338) | 2,725 | Complaints are documentation/support only; 4/5 on 4 votes. |
| Twinword Sentiment Analysis | 1,900 | WAVE 3, live-verified: 5/5 rating rests on a single vote, so pain evidence is the two verified complaint themes only (bogus 711 quota errors, free-tier blocking). Pricing grid known from the provider's site, not yet read on RapidAPI itself. Score ~52. |

## EXCLUDED (with reason)

| Candidate | Reason |
|---|---|
| WeatherAPI.com (52,194) | $0 pricing on RapidAPI: nothing to undercut. |
| CoinGecko (11,580) | Free tier only on RapidAPI. |
| Yahoo Finance by enclout (1,163) | Free tier only; Yahoo resale terms risk. |
| NFL API Data (3,450) | Sports data licensing. |
| Binance (Glavier), Telize, Jobs Scanner, Real Time Email Verification, ViewStats, real-estate scrapers | Below subscriber floor, no complaint pattern, or no free legal data route. |
| Flight data, entire category (wave 3) | OpenSky requires a paid license for commercial use; AeroDataBox terms ban resale on every plan; ADSBexchange is non-commercial only. No $0 terms-clean route exists. |
| Phone validation, entire category (wave 3) | The HLR trap: the paid value is live carrier status; free libphonenumber covers format/region/allocation only. A clone would be a partial match by construction. |
| TMDB-based movie APIs (wave 3) | TMDB commercial use needs its $149/mo key. IMDb datasets are non-commercial; OMDb data is CC BY-NC. |
| PDF Generator (domware.apps) | Live-verified at 2 subscribers. Below floor. |
| URL To Screenshot (APILight) | Live-verified at 103 subscribers despite a real 11.9s latency wedge. Below floor. |
| Custom QR Code with Logo (qrcode-monkey) | Live-verified at 294 subscribers; verified 500-error complaints. Below floor. |
| Dad Jokes (API-Ninjas), Numbers API, barcode.monster, Screenshotlayer, Free IP Geolocation | Free tier only on RapidAPI. |

## WAVE 3 CALIBRATION NOTE (2026-10-28)

Utility APIs (PDF, screenshot, QR) concentrate at tiny subscriber counts
even when complaints are real (verified: 2, 103, 294). Demand concentrates
in data and content APIs. Future sweeps should weight categories
accordingly. Method note: listing pages are JavaScript-rendered, so
subscriber counts and ratings must be read in the live signed-in browser;
text fetching returns titles only. Complaint dossiers and pricing grids
are fetchable and were verified that way in wave 3.
