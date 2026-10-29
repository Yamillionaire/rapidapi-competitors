# "API unreachable" is not a status: the translation reliability fix

Google Translate by Hark Translate (5,975 subscribers) shows an 84%
service level on its own listing, which means roughly one request in
six fails at the platform level, and its Discussions carry a fresh,
unanswered "API unreachable" complaint: the endpoint stops answering
and subscribers get silence. SwiftTranslate was built against exactly
that:

| Complaint | SwiftTranslate's answer |
| --- | --- |
| "API unreachable", unanswered | A 24h translation cache serves the last good answer (flagged stale) instead of failing, and the engine call retries once before any error is returned |
| 84% service level | Explicit JSON error objects on every failure, with the reason stated; no silent drops, no bare 500s |
| Bare failures with no explanation | Every rejection names the problem: missing text, unsupported language (with the endpoint that lists the codes), or text over the 5,000-character limit, with the length received |
| Mysterious engine | Every response labels its engine ("gemini", Gemini 3.6 Flash); nothing is passed off as another provider's engine |
| Pro tier costs $9 | The same tier is free here: 10,000 requests a month at $0 |

Same surface, deliberate: translate, detect, and languages live at the
same v2 paths with the same response envelope (data.translations,
data.detections, data.languages) as the incumbent, so existing code
migrates by changing the host and the key.

Engine check before launch (production payload, direct engine call):
Spanish to English returned "The fast brown fox jumps over the lazy
dog. Buenos Aires is the capital of Argentina." with the proper name
intact and the source detected as Spanish, in about 4.1 seconds;
French detection returned the correct code in about 2.6 seconds.
Transient engine 503s were observed twice during testing, which is
precisely why the retry and the stale-cache answer exist.

Pricing answers too: Ultra is $9 against their $19, Mega $29 against
$39, and their $9 Pro tier is free here.
