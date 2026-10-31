# Spec: SwiftRead (article-to-speech; the user's own product, queue #11)

Originated by the user in a voice call on 2026-10-30: "an API that
reads articles aloud - give it an article and it reads it, like the
play button on a news article." Built and launched under his standing
full-automation authorization for this lane (2026-10-29). Not a
competitor clone: a new product in the lane's house style.

## The product

POST a URL, get spoken audio back. The service fetches the page,
extracts the article's main text, and synthesizes it with a natural
neural voice, returning audio/mpeg directly - the "listen to this
article" button as an API, for read-it-later apps, accessibility
tools, newsletters, and content platforms.

- Extraction: the lane's proven stack, shared with CleanExtract -
  stdlib density-scored main-content extraction, SSRF-hardened fetch
  (public addresses only, checked on every redirect hop), size and
  time caps, boilerplate and navigation stripped by construction.
- Speech: the free Microsoft Edge read-aloud neural voices via the
  edge-tts package. Zero marginal cost, no key, no paid TTS. Text is
  chunked at sentence boundaries (1,600 characters per chunk) and the
  MP3 segments are concatenated in order so playback is seamless.
- POST /read-url {url, voice?, rate?} -> audio/mpeg. POST /speak
  {text, voice?, rate?} -> audio/mpeg for caller-supplied text.
  GET /voices lists the curated set of 10 voices (US and UK, male
  and female). GET /health is lane-standard.
- Caps and errors, stated not hidden: 15,000 characters of extracted
  or supplied text per request; beyond the cap a 422 names the cap
  and the length received. A page with no extractable article text
  returns a clear 422 no_article_text. Unknown voice or malformed
  rate returns a 422 naming the valid values. Rate accepts a
  multiplier (0.5-2.0) or a percent string, clamped to -50%..+100%.
- Server: the scaffold's conventions (RapidAPI proxy-secret gate,
  401 JSON without the header, /health open, structured JSON errors)
  extended with POST JSON bodies and binary audio responses, since
  the shared GET/JSON scaffold cannot carry either.
- Audio responses carry X-SwiftRead-Voice, X-SwiftRead-Characters,
  X-SwiftRead-Chunks, and (for /read-url) X-SwiftRead-Title headers,
  so callers can log what was read without parsing the audio.

Copyright posture: a read-aloud tool the caller points at content
they supply. Listing copy stays generic ("turn articles and web
pages into natural spoken audio") and never markets the service as
a way to obtain any specific publisher's content.

## Pricing (RapidAPI, hard limits, monthly quotas)

BASIC $0 / 100 per month, PRO $5 / 1,000, ULTRA $20 / 10,000,
MEGA $60 / 50,000. Net after RapidAPI's 25% fee: $3.75 / $15 / $45.
Audio generation is the heaviest workload in the fleet, so the free
tier is deliberately modest; the engine itself costs $0 per call.

## Costs and risks

$0 end to end: extraction is on-server stdlib; the voices are the
free Edge read-aloud set; hosting is the eleventh Render free
service. Keep-warm math must be re-budgeted: 2h window x 11 services
x 31 days = 682h worst month against the 750h workspace cap, about
68h of headroom for organic traffic - the tightest the fleet has
run; if a twelfth service lands, the window narrows.

Two honest environment notes. (1) The build sandbox's egress cannot
complete the speech engine's websocket connection (direct egress is
intercepted at the network level; the sandbox proxy mangles the
websocket upgrade), so synthesis is verified live on Render - the
same pattern WhoisBase used for port-43, which the sandbox blocks
and Render passes. Extraction, the gate, and every error path are
verified locally. (2) A 15,000-character article is roughly 15
minutes of speech and can take tens of seconds to synthesize;
callers should treat /read-url as a slow endpoint, and the listing
says so.

## Local test log (2026-10-30, build sandbox, test proxy secret set)

/health open without the secret, reporting the edge-tts engine and
the 15,000-character cap. GET /voices: 401 without the header, 200
with it, 10 voices. POST /speak: 401 without the header. Named 422s
verified: unknown voice (lists the valid ids), malformed rate,
over-cap text at 15,999 characters (states the cap and the length),
missing text, missing URL. SSRF guard verified: a 127.0.0.1 URL is
refused with fetch_refused. Extraction verified live locally:
example.com's body text passed extraction and reached the synthesis
stage (which then returned the structured 502 the sandbox's blocked
websocket causes), and a page whose paragraphs are all short
returned the clean 422 no_article_text. Synthesis itself is
verified on the deployed service (see docs/swiftread-reliability.md).
