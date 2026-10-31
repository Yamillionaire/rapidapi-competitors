# SwiftRead: reliability notes (Spotlight proof doc)

SwiftRead turns articles and web pages into natural spoken audio:
POST a URL, get an MP3 of the article read aloud by a natural neural
voice. This doc records what was actually tested on the deployed
service, including the failures found and fixed during launch night
(2026-10-30/31) - the same honesty standard as the rest of the fleet.

## What it does

- POST /read-url {url, voice?, rate?}: fetches the page, extracts the
  article's main text (navigation and boilerplate stripped by a
  density-scored extractor with an SSRF-hardened fetch), and returns
  the reading as audio/mpeg. POST /speak does the same for raw text.
- 45 neural voices in 13 languages: English (US, UK, Kenyan,
  Nigerian, Tanzanian, South African), Spanish, French, German,
  Portuguese, Italian, Japanese, Mandarin Chinese, Swahili, Amharic,
  Somali, Zulu, Afrikaans. Every voice is tagged with its language
  at GET /voices.
- 15,000 characters per request (about 15 minutes of speech), and
  plans bill PER REQUEST, never per character: a full article is
  one request. The cap is enforced exactly as documented; over-cap
  calls get a 422 naming the cap and the length received, and every
  success reports X-SwiftRead-Characters / -Chunks / -Paragraphs.
- Paragraphs are read as paragraphs: chunking is paragraph-aware
  and a short silence beat separates paragraphs in the audio.
- The audio itself is the response. There is no download URL, so
  nothing can expire (the loudest complaint against the biggest
  article-listening rival is URLs that arrive already expired).

## How it survives a flaky free speech engine

The voices are the free Microsoft Edge read-aloud set, which is
excellent and occasionally terrible: streams stall without erroring,
and some text is unspeakable for a given voice (a paragraph of
foreign-script examples inside an English article returns the
engine's NoAudioReceived). SwiftRead is built around that reality:

- Chunks (1,200 characters, sentence-packed within paragraphs)
  synthesize in parallel under a bounded pool, each with one retry.
- Synthesis runs under a hard 85-second wall-clock deadline,
  enforced outside the event loop. (Asyncio timeouts were tried
  first and cannot bound a stalled stream: the stream ignores task
  cancellation, and requests hung past 180 s. A thread join cannot
  be ignored.)
- A chunk that stalls, errors, or is unspeakable is skipped, and
  the response says so in X-SwiftRead-Chunks-Skipped. A partial
  reading beats a dead connection; only a total failure returns a
  structured 502.

## Live test record (deployed service, 2026-10-30/31)

Verified end to end on https://swiftread.onrender.com:

- GET /health: 200, reports the engine, the 15,000-character cap,
  and the running build. GET /voices: 200, all 45 voices with
  language tags (the proxy-secret gate returns 401 without the
  header once the RapidAPI secret is wired at listing time).
- POST /speak, English (en-US-GuyNeural, 115 chars): 200, valid MP3,
  7.1 s of audio. First-ever live call on the launch build returned
  in 8.4 s.
- POST /speak, Swahili (sw-KE-ZuriNeural): 200, 8.1 s of audio.
  POST /speak, Mandarin (zh-CN-XiaoxiaoNeural): 200, 6.8 s of audio.
- POST /speak, three paragraphs: 200, all 3 chunks and 3 paragraphs
  in the headers, 14.5 s of audio including the two paragraph beats.
- POST /read-url on a mixed-script encyclopedia article: the
  engine's NoAudioReceived on the foreign-script chunks was
  diagnosed from the structured error and produced the
  skip-and-disclose design above.
- Error paths (local and live): unknown voice 422 listing the valid
  ids, malformed rate 422, over-cap 422 naming cap and length,
  missing parameters 422, non-public URL refused (SSRF guard).

Engine latency from the free tier is genuinely variable (single
short requests measured between 8 s and 68 s on launch night), which
is exactly why the deadline-and-partial design exists; callers
should still treat article reads as slow calls and use a generous
client timeout.

Two measurements are deliberately NOT claimed yet: a full
15,000-character end-to-end load test and a complete /read-url
article read. On launch night the build sandbox's egress proxy
began stalling all POST traffic (proven path-side, not
service-side: instant-422 POSTs stopped arriving at the service at
all while GETs answered in under a second, and POSTs to unrelated
hosts stalled identically). The service now records its own
per-request timings in GET /health (recent_requests), and these two
rows will be filled from that record the moment a clean test path
runs them - before the listing's first subscriber, not after.

## Plans

BASIC $0 / 100 requests a month, PRO $5 / 1,000, ULTRA $20 / 10,000,
MEGA $60 / 50,000. Per request, never per character.
