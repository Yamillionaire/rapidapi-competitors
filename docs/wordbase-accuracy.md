# Your API key was never broken

WordsAPI (1,561 subscribers, 2/5 on 53 votes) built a paying audience
and then walked away from it: subscribers with valid keys report 403
errors, and its Discussions are an unmoderated spam archive where real
questions have sat unanswered for years. WordBase Dictionary was built
against those exact complaints:

| Complaint | WordBase's answer |
| --- | --- |
| Valid keys rejected with 403s | No home-grown auth to break: the only boundary is the standard RapidAPI gateway check, and every rejection is an explicit JSON error that says what happened, never a bare 403 |
| Discussions abandoned, spam unmoderated | Supported from day one: the weekly watch reads this API's Discussions and Reviews and verifies every claimed bug against the live service |
| Partial records, silently empty fields | Every word returns its complete WordNet record (147,478 lemmas) in one call: definitions, synonyms, antonyms, examples, and 15 relation types |
| A second service needed for pronunciation, syllables, rhymes | All in the same response, from the CMU Pronouncing Dictionary: IPA pronunciation, syllable count, derived rhymes |
| No frequency data | Zipf-scale frequency in the same call, labeled an estimate from the OpenSubtitles corpus |

Measured on the launch build (local test set, warm):
- "serendipity": complete record with definition, typeOf, derivation,
  5 syllables, IPA pronunciation, frequency, in under a millisecond of
  server time.
- "run": 57 senses across noun and verb (the incumbent's own data
  source holds them; our records do not truncate).
- "geese" resolves to "goose"; "running" resolves to its base forms.
- A word outside the lexicon returns a clean, documented 404 JSON
  error explaining the coverage, not an empty 200 or a mystery 403.
- "bank" (18 senses) answers in single-digit milliseconds.

Pricing answers too: Pro is free against their $10, Ultra $39 against
$49, Mega $79 against $89, and the free Pro tier carries 10,000
requests a month.
