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
| 4 | GeoDB Cities (wirefreethought) | 50,222 | 3/5 (60) | $20/$40/$80 | Basic free x2 quota; $10/$30/$70 | 86 | WAVE 3, live-verified 2026-10-28. PUBLISHED LIVE 2026-10-28 as GeoBase Cities: https://rapidapi.com/YamilLittle/api/geobase-cities (API ID api_9af674f9-3086-4269-b6b8-347582f52296, Render srv-dbh7o66c6qcc73b6k3fg). Plans: BASIC $0 2,000/day, PRO $10 27,777/day, ULTRA $30 49,999/day, MEGA $70 94,443/day, all hard (RapidAPI caps quotas per price; prices kept, quotas at platform max). Gateway-verified (Rome search 200 through the Hub), Spotlight "The cities other APIs lose are here" live on the Overview. |
| 5 | Article Extractor and Summarizer (restyler) | 11,784 | 3/5 | $15/$95/$195 | $5/$85/$185 | 82 | PUBLISHED LIVE 2026-10-28 as CleanExtract: https://rapidapi.com/YamilLittle/api/cleanextract (API ID api_47083d92-7a84-4272-bb6a-712449631a9b, Render srv-dbh8kp6c6qcc73em76sg). Stdlib extraction + extractive summarizer on-server (no Gemini dependency; summaries honestly labeled extractive), SSRF-hardened. Plans: BASIC $0/250mo, PRO $5/5,000mo, ULTRA $85/50,000mo, MEGA $185/250,000mo hard. Gateway-verified through the Hub (Wikipedia extraction 200, 9,347 words); Spotlight "Extraction that answers, with the error, instead of a bare 503" live on the Overview. |
| 6 | Paraphrasing / Rewriter (NeuralWriter) | 5,632 | 3/5 | Ultra $19.99, Mega $34.99 | $9.99/$24.99 | 68 | BUILT AND LISTED 2026-10-28 as SwiftRewrite (API ID api_01c1558f-60b3-465c-b6b5-e164a1fe6e7f, Render srv-dbh99i67bikc73dv5lm0), PRIVATE. Plans: BASIC $0/250mo, PRO $3.99/3,500mo, ULTRA $9.99/25,000mo, MEGA $24.99/50,000mo hard. Proxy gate verified. KEY GATE CLEARED 2026-10-29: user added GEMINI_API_KEY in the Render dashboard; model set to gemini-3.6-flash (2.5-flash retired for new users, 3.8-flash too slow) in env and code (commit 002e4d20); AI engine verified end to end through the proxy gate (engine "gemini", names preserved). PUBLISHED LIVE 2026-10-29 on his tap ("Publish it" in the voice call). Hub https://rapidapi.com/YamilLittle/api/swiftrewrite. Gateway test through RapidAPI: 200, engine gemini, names preserved (cold start 12.3s at 3 AM ET). Spotlight posting at launch from docs/swiftrewrite-speed.md. Launch baseline in the watch state file. |
| 7 | WordsAPI (dpventures) | 1,561 | 2/5 (53) | $10/$49/$89 | Pro FREE; $39/$79 | 66 | WAVE 3, live-verified. Valid keys get 403s; Discussions abandoned (spam sitting unmoderated). BUILT 2026-10-29 as WordBase Dictionary (wordbase/app.py, spec docs/spec-wordsapi-competitor.md, Spotlight doc docs/wordbase-accuracy.md ready, not posted). WordNet 3.1 + CMUdict + FrequencyWords, all downloaded at boot (tarball too large for the snapshot route); 147,478 lemmas. Local test set all passing (serendipity full record, run 57 senses, geese -> goose, clean documented 404s, search filters). Plans: BASIC $0/1,000mo, PRO $0/10,000mo, ULTRA $39/300,000mo, MEGA $79/1,000,000mo hard (or platform max at price). Keep-warm final fleet state: nine services, window 09:00-11:00 ET (558h worst month). DEPLOYED 2026-10-29: GitHub commit a18d1c7f, Render srv-dbhfdb6c6qcc73f9geh0, https://wordbase-dictionary.onrender.com, deploy live; live test battery all passing (health 147,478 lemmas; serendipity full record; run 57 senses; documented 404s; search; geese -> goose). PUBLISH AUTHORIZED by the user 2026-10-29 (full-run voice authorization; the earlier per-build tap gate is lifted for this build). Remaining launch steps, run via the parent's browser tasks: Studio listing (PRIVATE first), proxy-secret wiring with gate verification (401/200), publish public, Hub gateway test, Spotlight post from docs/wordbase-accuracy.md via its GitHub blob URL. Mark PUBLISHED LIVE with the Hub URL here once the gateway test returns 200. |
| 8 | Google Translate (Hark Translate) | 5,975 | 4/5 (41 votes) | $9/$19/$39 | Ultra $9, Mega $29 | 66 | Fresh "API unreachable" complaint, unanswered. Service level 84%. BUILT AND DEPLOYED 2026-10-29 as SwiftTranslate (swifttranslate/app.py, spec docs/spec-swifttranslate.md, Spotlight doc docs/swifttranslate-reliability.md ready, not posted). Render srv-dbhfe08n74is73d8e020, https://swifttranslate-72rx.onrender.com (Render suffixed the subdomain; the bare name was taken globally). Gemini 3.6 Flash wrapper on the incumbent's v2 surface (/language/translate/v2, /detect, /languages; same response envelope), 107 languages, 24h cache with stale-on-error, one engine retry, explicit JSON errors. Engine verified pre-launch through the connector with the production payload (es to en correct with proper names intact ~4.1s, fr detect ~2.6s; two transient Google 503s observed, hence the retry). Plans: BASIC $0/1,000mo, PRO $0/10,000mo (their $9 Pro free), ULTRA $9/100,000mo, MEGA $29/500,000mo hard. BLOCKED before listing/publish: (1) GEMINI_API_KEY must be added to the swifttranslate Render env by the user (same one-time step as SwiftRewrite; deployed /health verified reporting "awaiting key", translate/detect return an explicit 503 until then); (2) the Studio listing (PRIVATE first), proxy-secret wiring with gate verification, publish, Hub gateway test (engine "gemini"), and Spotlight post from docs/swifttranslate-reliability.md remain, run via the parent's browser tasks. Mark PUBLISHED LIVE once the gateway test returns 200. |
| 9 | Google News (BFD) | 7,316 | 3/5 | $25/$50/$100 | $15/$40/$90 | 64 | BUILT AND DEPLOYED 2026-10-29 as NewsBase Headlines (Render srv-dbhfe5o473hc739rmad0, https://newsbase-headlines.onrender.com). RSS build (Google News RSS editions/search/topics + BBC, NPR, Guardian, Al Jazeera, NYT feeds): responses serialized from parsed records (valid JSON by construction; 27/27 strict-parse checks across local and live suites), NO image proxy (publisher image URLs returned directly; live BBC CDN image verified 200 image/jpeg). Endpoints: /headlines, /search, /topic/{topic}, /source/{source}, /topics, /health. Plans to save in Studio: BASIC $0/250mo, PRO $15/10,000mo, ULTRA $40/75,000mo, MEGA $90/300,000mo hard. Listing package ready: listings/newsbase-openapi.json; Spotlight proof doc docs/newsbase-reliability.md ("The news API whose JSON actually parses"). REMAINING (parent browser route): Studio listing in chunks (basics, endpoints, pricing + proxy secret), gate verify 401/200, publish, Hub gateway test, Spotlight post, launch baseline. |

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
