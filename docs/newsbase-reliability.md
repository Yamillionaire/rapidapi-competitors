# The news API whose JSON actually parses

Google News by BFD (7,316 subscribers, rated 3/5) carries two recurring
complaints in its own RapidAPI Discussions: responses that are not
valid JSON, breaking client parsers, and article images routed through
a provider image proxy that serves them broken. NewsBase Headlines was
built so both failure modes have nowhere to live: RSS feeds are parsed
into records on our server and serialized by us, so the response is
valid JSON by construction, and there is no image proxy at all. When a
feed carries a publisher image URL we return that URL directly, and
when it does not, the field is omitted.

Verified against the live NewsBase service on 2026-10-29:

| Test | Result |
| --- | --- |
| Top headlines (US edition) | 200, valid JSON, publisher and timestamp on every article |
| Non-default edition (country=IN) | 200, that edition's real headlines, valid JSON |
| Search (q=artificial intelligence) | 200, matching stories, valid JSON |
| Topic feed (SPORTS) and outlet feeds (BBC, Guardian, NYT, NPR, Al Jazeera) | 200, valid JSON on every one |
| Article image on an outlet story | The BBC's own CDN URL, returned directly; loads as image/jpeg (no proxy anywhere in the path) |
| Unknown topic, unknown source, missing query, bad country code | Structured JSON error naming the problem and the valid options, never a bare 500 or a malformed body |
| Every response in the launch test set, success and error alike | Parsed with a strict JSON parser: 27 of 27 valid |

And the pricing answers too: the incumbent's Pro tier is $25 a month.
NewsBase Pro is $15, Ultra $40 against their $50, Mega $90 against
their $100, all hard limits.
