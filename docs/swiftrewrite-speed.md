# Ten seconds is not "Very Fast": the speed and honesty fix

Paraphrasing and Rewriter API (5,632 subscribers) advertises "Very Fast"
and "NO limits" while its own listing shows 9,978ms latency, paid tiers
capped at 1 request per second, and discussion threads full of
unexplained "text is too long or too short" rejections and rewrites
that changed character names. SwiftRewrite was built against those
exact complaints:

| Complaint | SwiftRewrite's answer |
| --- | --- |
| 9,978ms latency under a "Very Fast" claim | Gemini Flash rewriting, typically 1 to 3 seconds |
| "Text is too long or too short" with no numbers | Every rejection states the limit AND the length received (documented window: 10 to 2,000 characters) |
| Rewrites changing character names | Names are extracted before the rewrite and verified in the output; the response reports names_preserved |
| Free tier of 5 requests a day, light mode only | 250 requests a month on the free tier, all modes |
| Unanswered 400/403/500 threads | Structured errors on every failure, and a built-in fallback engine that answers (labeled) instead of a 500 |

Pricing answers too: Ultra is $9.99 against their $19.99, Mega $24.99
against $34.99, at the same quotas.
