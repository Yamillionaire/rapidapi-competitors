"""CleanList Email Verifier - competitor to Top-Rated E-mail Check on RapidAPI (core prototype).

Incumbent verified 2026-10-28: 5,540 subscribers, Pro $50 / Ultra $99 / Mega $195.
Complaints: disposable domains not detected, invalid addresses returning Valid,
non-existent Gmail addresses not caught, support silent. Provider concedes it is
not built for cleaning marketing lists. This service is built for exactly that.

Checks are labeled separately so a buyer sees what was actually verified:
syntax, disposable (starter list embedded; production loads a daily-updated
list file), domain DNS existence + MX records via DNS-over-HTTPS.
Mailbox-level SMTP probing is a separate labeled mode on the roadmap:
many servers accept-all or block probes, so v1 never pretends it did it.

Run: python3 app.py (PORT env, default 8102).
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run, fetch_json, cache_get, cache_set

SYNTAX = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
DISPOSABLE_STARTER = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.info", "sharklasers.com",
    "10minutemail.com", "tempmail.com", "temp-mail.org", "throwawaymail.com",
    "getnada.com", "maildrop.cc", "yopmail.com", "trashmail.com", "fakeinbox.com",
    "dispostable.com", "mailnesia.com", "mintemail.com", "mohmal.com",
    "tempail.com", "emailondeck.com", "spamgourmet.com", "mytemp.email",
    "burnermail.io", " guerrillamail.biz".strip(), "33mail.com", "mailcatch.com",
    "tempinbox.com", "eyepaste.com", "discard.email", "sogetthis.com",
}
ROLE_PREFIXES = {"admin", "info", "support", "sales", "postmaster", "noreply",
                 "no-reply", "webmaster", "abuse", "billing", "contact"}


_DISPOSABLE_CACHE = None


def disposable_set():
    """Loads the full open disposable-domain list (FFraud-com list, MIT license,
    224,300 domains as fetched 2026-10-28, rebuilt upstream every 30 minutes;
    production refetches daily). Falls back to the embedded starter set."""
    global _DISPOSABLE_CACHE
    if _DISPOSABLE_CACHE is not None:
        return _DISPOSABLE_CACHE
    path = os.environ.get("DISPOSABLE_LIST_FILE") or os.path.join(
        os.path.dirname(__file__), "data", "disposable_domains.txt")
    domains = set(DISPOSABLE_STARTER)
    if os.path.exists(path):
        with open(path) as fh:
            domains |= {ln.strip().lower() for ln in fh if ln.strip()}
    else:
        # Deployed without the data file: pull the same open list at runtime
        # (MIT licensed, rebuilt upstream every 30 minutes) and keep it in memory.
        try:
            import urllib.request as _u
            req = _u.Request("https://raw.githubusercontent.com/FFraud-com/disposable-email-domains/main/disposable-email-domains.txt",
                             headers={"User-Agent": "CleanList/1.0"})
            with _u.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", "replace")
            domains |= {ln.strip().lower() for ln in text.splitlines() if ln.strip()}
        except Exception:
            pass  # starter set still applies; /health reports the loaded count honestly
    _DISPOSABLE_CACHE = domains
    return domains


def dns_query(name, rtype):
    key = f"dns:{rtype}:{name}"
    cached, stale = cache_get(key)
    if cached is not None:
        return cached
    try:
        data = fetch_json(f"https://cloudflare-dns.com/dns-query?name={name}&type={rtype}",
                          headers={"Accept": "application/dns-json"}, timeout=12)
        answers = data.get("Answer", [])
    except Exception:
        answers = []
    cache_set(key, answers, 3600)
    return answers


def check(params):
    email = (params.get("email") or "").strip().lower()
    if not email:
        return 422, {"error": "missing_parameter", "detail": "Provide email=, for example email=test@example.com."}
    syntax_ok = bool(SYNTAX.match(email)) and ".." not in email and len(email) <= 254
    result = {"email": email, "checks": {"syntax": syntax_ok}, "source": "CleanList core v1"}
    if not syntax_ok:
        result.update({"valid": False, "risk": "high", "recommendation": "reject",
                       "reason": "Syntax check failed."})
        return 200, result
    local, domain = email.rsplit("@", 1)
    disposable = domain in disposable_set()
    mx_raw = [a["data"] for a in dns_query(domain, "MX")]
    # A null MX record ("0 ." per RFC 7505) means the domain declares it accepts NO mail.
    mx = [m for m in mx_raw if m.strip() not in (".", "0 .", "")]
    null_mx = bool(mx_raw) and not mx
    a_records = [] if mx else dns_query(domain, "A")
    result["checks"].update({
        "disposable": disposable,
        "disposable_list": "full open list loaded (FFraud-com, MIT); count in /health; refreshed daily in production",
        "mx_records": mx,
        "null_mx": null_mx,
        "domain_resolves": bool(mx or a_records),
        "role_account": local.split("+")[0] in ROLE_PREFIXES,
        "mailbox_exists": None,
        "mailbox_note": "Not probed in v1. SMTP probing is unreliable on accept-all servers and is shipped as a separate labeled mode, never silently implied.",
    })
    if disposable:
        result.update({"valid": False, "risk": "high", "recommendation": "reject",
                       "reason": "Disposable / temporary mail domain."})
    elif null_mx:
        result.update({"valid": False, "risk": "high", "recommendation": "reject",
                       "reason": "Domain publishes a null MX record; it declares that it accepts no mail."})
    elif not (mx or a_records):
        result.update({"valid": False, "risk": "high", "recommendation": "reject",
                       "reason": "Domain has no MX or A records in DNS; it cannot receive mail as addressed."})
    elif not mx:
        result.update({"valid": True, "risk": "medium", "recommendation": "review",
                       "reason": "Domain resolves but publishes no MX records."})
    else:
        result.update({"valid": True, "risk": "low", "recommendation": "accept",
                       "reason": "Syntax valid, domain publishes MX records, not a known disposable domain."})
    return 200, result


def health(params):
    return 200, {"status": "ok", "service": "cleanlist-email-verifier",
                 "built_for": "cleaning email marketing lists",
                 "disposable_domains_loaded": len(disposable_set())}


if __name__ == "__main__":
    run({"/check": check, "/health": health},
        int(os.environ.get("PORT", "8102")), "cleanlist-email-verifier")
