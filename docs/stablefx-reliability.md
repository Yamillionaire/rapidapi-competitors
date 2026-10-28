# Why StableFX stays up when currency APIs go down

Most currency APIs fail the same way: an upstream hiccup becomes your outage.
StableFX is built the opposite way.

## How it works

- **Primary source:** daily reference rates from the European Central Bank,
  served through Frankfurter, with an independent fallback feed if the
  primary ever fails.
- **Last-good cache:** if both feeds are unreachable, StableFX serves the
  last good rates with an explicit `"stale": true` flag in the response.
  You get honest data with a warning, never a bare 503.
- **Honest labeling:** every response states `rate_type: daily_reference`.
  These are central-bank reference rates for accounting, billing and
  display. We never dress them up as real-time trading quotes.
- **Errors are real errors:** failures return structured JSON with a reason.
  No silent empty responses, no mystery 500s.

## What that means in practice

Currency data is a commodity. Reliability is the product. StableFX targets
99.9% uptime, caches aggressively so warm responses land in milliseconds,
and publishes changes instead of shipping them silently.

Endpoints: `/latest`, `/convert`, `/historical` (back to 1999),
`/currencies`, `/health`.

Live on RapidAPI: search "StableFX Currency Rates".
