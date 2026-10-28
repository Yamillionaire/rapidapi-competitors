# RapidAPI Competitor Services - Build Status

User directed 2026-10-28: build all three competitors (Currency, Email, Yahu Financials).
All three run on one shared zero-dependency Python scaffold (shared/rapidapi_server.py):
stdlib HTTP server, explicit JSON error objects (never a silent 204 or bare 500),
TTL cache with stale-on-error serving, optional RapidAPI proxy-secret check via
RAPIDAPI_PROXY_SECRET env. Zero dependencies means free-tier hosting anywhere
(Render free account is the planned deploy target) and instant cold starts.

## 1. currency/ - StableFX Currency Rates (vs fyhao Currency Exchange)
Endpoints: /latest, /convert, /historical, /currencies, /health.
Data: Frankfurter (ECB daily reference rates), Fawaz API fallback, last-good cache
served flagged stale instead of a 503. Honest label: daily reference, not trading quotes.
TESTED LIVE 2026-10-28:
- /latest USD: EUR 0.89686, GBP 0.7503 (2026-10-27 ECB day). Cold 1,267ms (upstream-bound).
- Same call warm from cache: 2ms. Incumbent's listed latency: 23,769ms at 22% service level.
- /convert 100 USD to EUR = 89.686. Correct.
- /historical 2024-01-15 returns that day's rates.
Pricing (from spec): Basic free 1,000/mo; Pro free 10,000/mo (hook); Ultra $10 (net $7.50);
Mega $20 (net $15). Incumbent: $10 / $20 / $30.
TERMS VERIFIED 2026-10-28: Frankfurter is open source (MIT) and its rates are
free for commercial use (ECB and central-bank reference data). Fawaz is the
fallback only. Deploy package ready (render.yaml at project root).
REMAINING: deploy to Render from the user's account, create RapidAPI provider
listing (user's account, preview first). Noted upgrade path: Frankfurter v2
covers 160+ currencies from 100+ central banks versus v1's ECB-only set.

## 2. emailcheck/ - CleanList Email Verifier (vs Top-Rated E-mail Check)
Endpoint: /check?email= with separately labeled checks: syntax, disposable,
MX/DNS via DNS-over-HTTPS, role account. Mailbox probing deliberately NOT faked:
it ships as a separate labeled mode later.
TESTED LIVE 2026-10-28 (5-case set, then re-tested after fixes, all passing):
- Real Gmail address: valid, low risk, MX found.
- mailinator.com address: rejected as disposable.
- Bad syntax: rejected.
- Non-existent domain: rejected, no MX/A records.
- example.com: rejected after fix - it publishes a null MX (RFC 7505, accepts no mail).
  First pass wrongly accepted it; the hard re-check caught it and the code was fixed.
UPDATE 2026-10-28: the full open disposable list is loaded (FFraud-com list, MIT
license, 224,300 domains in data/disposable_domains.txt, rebuilt upstream every
30 minutes; production refetches daily). Verified live: addresses at idwager.com
and bialode.com, the two domains the incumbent's own users publicly complained
it missed, are both REJECTED here; Gmail regression still passes.
REMAINING: accuracy test set publication, deploy, listing.
First production run is planned as the dogfood pass on the user's own email database.

## 3. financials/ - EDGAR Fundamentals (vs ApiDojo Yahu Financials)
Endpoints mirror the incumbent's paths: /stock/get-fundamentals, /stock/v2/get-timeseries.
Data: SEC EDGAR company-facts (free, public domain, no key), cached 24h.
TESTED LIVE 2026-10-28:
- AAPL annualTotalRevenues: 19 consecutive annual periods, 2007-2025, zero nulls,
  zero gaps after merging EDGAR's alias tags (filers changed revenue tags over the
  years; merging was required - the first pass had gaps in 2018-2020 and the
  re-check caught it). FY2018 = 265,595,000,000 and FY2020 = 274,515,000,000,
  matching Apple's reported figures exactly. All-periods revenue count: 36.
  Incumbent: series capped at 5, revenues null except the last period.
- TSLA annual revenues: 17 periods, 2009-2025.
- pegRatio returns an explicit explanation object plus a real trailing
  earningsGrowth5yrPct computed from filings (AAPL 7.39%), never a silent null.
FREE ENDPOINTS ADDED 2026-10-28 (user approved free-only launch the same day):
/stock/v2/get-summary serves company name, exchange, SIC industry, fiscal year
end and HQ from EDGAR (AAPL and TSLA verified live), filling the incumbent's
missing name/exchange complaint at $0. /stock/v2/get-recommendations serves
related tickers as SEC SIC industry peers (AAPL returns DELL, OMCL, OSS, OURA,
SCKT; method labeled in the response, not passed off as a popularity feed).
REMAINING (the one real cost decision, deferred by the user until revenue):
quotes/charts need a licensed feed whose
terms allow redistribution (Yahoo data is personal-use only, no commercial route
published). Feed pricing researched 2026-10-28 from the providers' own pages:
Tiingo publishes redistribution pricing on its product pages, $250/mo for
startups ($500 enterprise); its $50/mo Commercial plan is INTERNAL use only and
does not cover resale. Massive (formerly Polygon) marks every self-serve plan
individual use; its Business plan with a commercial license runs about
$2,000/mo. Financial Modeling Prep requires a separate Data Display and
Licensing Agreement (no self-serve price). PLAN: launch fundamentals-only at
$0 (that is where the incumbent's complaints and our proven fix are), and add
quotes only when the API's own subscription revenue covers the license
(breakeven roughly 17 Ultra subs at $15 net or 2 Mega at $217.50 net against a
$250/mo Tiingo startup redistribution tier), so the license is never an
out-of-pocket cost. Then build the quote endpoints and related tickers
(EDGAR industry peers), deploy, listing.

## Sequence
Currency deploy-ready first (done at prototype level), Email second, Financials
third once the quote feed is chosen. Nothing is published until the user approves
each listing preview. PayPal payout linking on RapidAPI is the user's own tap.
