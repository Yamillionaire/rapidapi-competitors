# Extraction that answers, with the error, instead of a bare 503

Article Extractor and Summarizer (11,784 subscribers, service level 74%)
carries years of unanswered user reports in its own RapidAPI Discussions:
503 service unavailable, 403s, 401s, and 500s, with no provider replies.
CleanExtract was built so those failure modes have nowhere to live:
extraction and summarization run entirely on our own server, with no
external AI call and no third-party extractor in the chain.

Verified against the live CleanExtract service on 2026-10-28:

| Test | Result |
| --- | --- |
| Full encyclopedia article (9,347 words) | Title, metadata, and clean body text returned |
| Summarize the same article | The article's own key sentences, method labeled extractive in the response |
| Source page that returns 404 | Structured error naming the source's HTTP status, not a generic 503 |
| Non-public addresses (localhost, cloud metadata range) | Refused before fetching, SSRF-hardened on every redirect hop |
| Page with no article body | Structured "no article text" error explaining what happened |

And the quota complaint gets answered too: the incumbent's Pro tier is
$15 for 500 requests a month. CleanExtract Pro is $5 for 5,000.
