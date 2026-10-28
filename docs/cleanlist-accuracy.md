# The disposable domains other checkers miss

Email verification is only worth paying for if it catches what a free
syntax check cannot. CleanList was built around the cases that slip
through typical checkers.

## What every check runs

1. **Syntax:** full address parsing, not a regex shrug.
2. **Disposable domains:** checked against a list of 224,300 known
   disposable and temporary-mail domains, refreshed from a maintained
   public source.
3. **Mail-server reality:** MX records resolved live, including the
   RFC 7505 "null MX" case, where a domain publishes a record that
   explicitly says "we accept no mail." Many checkers read that as valid.
   CleanList rejects it.
4. **Role accounts:** postmaster@, admin@ and friends are flagged, not
   silently passed.

## Proof, not promises

Domains that users publicly reported slipping through a popular competing
checker, `idwager.com` and `bialode.com`, are rejected by CleanList as
disposable. A disposable test address returns
`valid: false, risk: high, recommendation: reject` with the reason stated
in plain language.

Every response separates the individual checks, so you can see exactly
why an address passed or failed. No black-box score.

Live on RapidAPI: search "CleanList Email Verifier".
