"""WhoisBase - competitor to Whois Lookup (Zozor54) on RapidAPI.

Incumbent verified 2026-10-29: 3,811 subscribers, rated 3/5 (16 votes),
pricing $10/$30/$80, all 29 Discussion threads Unanswered. Complaints:
stale cached records that stay wrong for hours despite the incumbent's
force flag, timeouts and bare 504s, and blank or null data for many
TLDs (.dev, .at, .rs, .pl, .eu, .fi named by users).
This service: live RDAP queries resolved through the IANA bootstrap
(data.iana.org/rdap/dns.json, the registries' own public protocol),
with a port-43 whois fallback for TLDs that run no RDAP endpoint
(.at, .rs, .eu, .de, .io, .ch). The cache is honest by construction:
records live 300 seconds, and every response carries a cache block
with the served record's age; the fresh parameter (alias force, the
incumbent's flag name) genuinely bypasses the cache and refetches
from the registry. Errors are always structured JSON; an unregistered
domain is a 200 with registered: false, never a blank record.
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8110).
"""
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run, fetch_json

UA = "WhoisBase/1.0 (+https://rapidapi.com/YamilLittle/api/whoisbase)"
BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
BOOTSTRAP_TTL = 24 * 3600
CACHE_TTL = 300          # seconds a positive record may be served from cache
NEGATIVE_TTL = 60        # seconds an unregistered result may be cached
RDAP_TIMEOUT = 12
WHOIS_TIMEOUT = 8
WHOIS_MAX_BYTES = 65536

# TLDs with no RDAP endpoint in the IANA bootstrap, and the registry's
# own port-43 whois server for each. This map is the .at/.rs/.eu fix:
# the incumbent returns blanks for these; we ask the registry directly.
PORT43_SERVERS = {
    "at": "whois.nic.at",
    "rs": "whois.rnids.rs",
    "eu": "whois.eu",
    "de": "whois.denic.de",
    "io": "whois.identity.digital",
    "ch": "whois.nic.ch",
    "li": "whois.nic.ch",
}

# Used only if the IANA bootstrap itself is unreachable, so routing for
# the major TLDs (including the complaint TLDs .dev, .pl, .fi) survives.
SEED_RDAP = {
    "com": ["https://rdap.verisign.com/com/v1/"],
    "net": ["https://rdap.verisign.com/net/v1/"],
    "org": ["https://rdap.publicinterestregistry.org/rdap/"],
    "dev": ["https://pubapi.registry.google/rdap/"],
    "pl": ["https://rdap.dns.pl/"],
    "fi": ["https://rdap.fi/rdap/rdap/"],
    "uk": ["https://rdap.nominet.uk/uk/"],
}

COMPLAINT_TLDS = ["dev", "at", "rs", "pl", "eu", "fi"]

_bootstrap = {"map": None, "publication": None, "fetched_at": 0.0, "seeded": False}
_bootstrap_lock = threading.Lock()
_cache = {}
_cache_lock = threading.Lock()


class LookupFailure(Exception):
    def __init__(self, status, error, detail):
        super().__init__(detail)
        self.status = status
        self.error = error
        self.detail = detail


# ---------------------------------------------------------------- bootstrap

def get_bootstrap():
    """Return (tld -> [rdap base urls], publication). Cached 24h."""
    now = time.time()
    with _bootstrap_lock:
        if _bootstrap["map"] is not None and now - _bootstrap["fetched_at"] < BOOTSTRAP_TTL:
            return _bootstrap["map"], _bootstrap["publication"]
    try:
        data = fetch_json(BOOTSTRAP_URL, headers={"User-Agent": UA,
                                                  "Accept": "application/json"},
                          timeout=15)
        mapping = {}
        for tlds, urls in data.get("services", []):
            for tld in tlds:
                mapping[tld.lower()] = urls
        if not mapping:
            raise ValueError("bootstrap contained no services")
        with _bootstrap_lock:
            _bootstrap.update({"map": mapping,
                               "publication": data.get("publication"),
                               "fetched_at": now, "seeded": False})
        return mapping, data.get("publication")
    except Exception:
        with _bootstrap_lock:
            if _bootstrap["map"] is None:
                _bootstrap.update({"map": dict(SEED_RDAP), "publication": None,
                                   "fetched_at": now, "seeded": True})
            return _bootstrap["map"], _bootstrap["publication"]


# ---------------------------------------------------------------- validation

_LABEL = r"(?!-)[a-z0-9-]{1,63}(?<!-)"
_DOMAIN_RE = re.compile(rf"^{_LABEL}(\.{_LABEL})+$")


def normalize_domain(raw):
    """Return (domain, tld) or raise LookupFailure(422)."""
    if raw is None or not str(raw).strip():
        raise LookupFailure(422, "missing_parameter",
                            "Provide domain= with a domain name, for example domain=example.com.")
    host = str(raw).strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split("?", 1)[0]
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    host = host.split(":", 1)[0].rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        host = ".".join(label.encode("idna").decode("ascii") if label else label
                        for label in host.split("."))
    except (UnicodeError, ValueError):
        raise LookupFailure(422, "invalid_domain",
                            f"'{raw}' is not a valid domain name.")
    if len(host) > 253 or not _DOMAIN_RE.fullmatch(host) or host.rsplit(".", 1)[1].isdigit():
        raise LookupFailure(422, "invalid_domain",
                            f"'{raw}' is not a valid domain name. Provide a registered "
                            "domain such as example.com (no scheme, no path).")
    return host, host.rsplit(".", 1)[1]


# ---------------------------------------------------------------- RDAP

def _vcard_props(entity):
    props = {}
    vcard = entity.get("vcardArray")
    if isinstance(vcard, list) and len(vcard) == 2 and isinstance(vcard[1], list):
        for item in vcard[1]:
            if isinstance(item, list) and len(item) == 4:
                props[item[0]] = item[3]
    return props


def _entity_with_role(entities, role):
    for entity in entities or []:
        if role in (entity.get("roles") or []):
            return entity
    return None


def parse_rdap(data, domain, tld, server):
    record = {
        "domain": data.get("ldhName", domain).lower(),
        "tld": tld,
        "registered": True,
        "source": "rdap",
        "registry_server": server,
        "registrar": None,
        "registrant": None,
        "created": None,
        "updated": None,
        "expires": None,
        "status": data.get("status") or [],
        "nameservers": sorted({ns.get("ldhName", "").lower()
                               for ns in data.get("nameservers") or []
                               if ns.get("ldhName")}),
        "dnssec": (data.get("secureDNS") or {}).get("delegationSigned"),
        "events": [],
    }
    for event in data.get("events") or []:
        action, date = event.get("eventAction"), event.get("eventDate")
        if not action or not date:
            continue
        record["events"].append({"action": action, "date": date})
        if action == "registration":
            record["created"] = date
        elif action == "expiration":
            record["expires"] = date
        elif action == "last changed":
            record["updated"] = date
    entities = data.get("entities") or []
    registrar = _entity_with_role(entities, "registrar")
    if registrar:
        props = _vcard_props(registrar)
        iana_id = None
        for pid in registrar.get("publicIds") or []:
            if pid.get("type") == "IANA Registrar ID":
                iana_id = pid.get("identifier")
        url = None
        for link in registrar.get("links") or []:
            if link.get("rel") == "self" or link.get("href"):
                url = link.get("href")
                break
        record["registrar"] = {"name": props.get("fn"),
                               "iana_id": iana_id, "url": url}
    registrant = _entity_with_role(entities, "registrant")
    if registrant:
        props = _vcard_props(registrant)
        adr = props.get("adr")
        country = None
        if isinstance(adr, list) and len(adr) >= 7:
            country = adr[6] or None
        elif isinstance(adr, str):
            country = None
        org = props.get("org")
        if isinstance(org, list):
            org = org[0] if org else None
        if org or country:
            record["registrant"] = {"organization": org, "country": country}
    return record


def _rdap_once(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/rdap+json, application/json"})
    with urllib.request.urlopen(req, timeout=RDAP_TIMEOUT) as resp:
        import json as _json
        return _json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_rdap(urls, domain, tld):
    """Return a normalized record, or raise LookupFailure."""
    last_error = None
    for base in urls:
        url = base.rstrip("/") + "/domain/" + quote(domain)
        server = re.sub(r"^https?://", "", base).split("/")[0]
        for attempt in range(2):
            try:
                data = _rdap_once(url)
                return parse_rdap(data, domain, tld, server)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return {"domain": domain, "tld": tld, "registered": False,
                            "source": "rdap", "registry_server": server,
                            "registrar": None, "registrant": None,
                            "created": None, "updated": None, "expires": None,
                            "status": [], "nameservers": [], "dnssec": None,
                            "events": []}
                if exc.code in (429, 503) and attempt == 0:
                    time.sleep(1.5)  # one backoff retry vs transient rate limits
                    continue
                last_error = LookupFailure(
                    502, "upstream_http_error",
                    f"The registry RDAP server at {server} returned HTTP {exc.code} "
                    f"for {domain}. Try again shortly.")
            except (TimeoutError, socket.timeout):
                last_error = LookupFailure(
                    502, "upstream_timeout",
                    f"The registry RDAP server at {server} did not answer within "
                    f"{RDAP_TIMEOUT} seconds for {domain}. This is a structured "
                    "error, not a bare gateway timeout; try again shortly.")
                break
            except Exception as exc:
                last_error = LookupFailure(
                    502, "upstream_error",
                    f"Could not reach the registry RDAP server at {server} for "
                    f"{domain}: {type(exc).__name__}: {exc}")
                if attempt == 0:
                    time.sleep(1.0)  # one retry against transient connection drops
                    continue
            break
    raise last_error or LookupFailure(502, "upstream_error",
                                      f"No RDAP server answered for {domain}.")


# ---------------------------------------------------------------- port 43

_NOT_FOUND_RES = [
    r"no match", r"not found", r"no data found", r"no entries found",
    r"no object found", r"no matching record", r"domain not found",
    r"status:\s*free", r"not registered", r"no whois record",
    r"object does not exist", r"is available for registration",
    r"returned 0 objects", r"object not found",
]
_DATE_FORMATS = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                 "%d-%b-%Y", "%Y.%m.%d", "%d.%m.%Y", "%d.%m.%Y %H:%M:%S",
                 "%Y%m%d %H:%M:%S", "%Y/%m/%d",
                 "%d %b %Y", "%b %d %Y", "%d-%b-%y"]


def _parse_date(raw):
    raw = re.split(r"[(\[]", raw.strip())[0].strip().rstrip(".")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(
                tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return raw or None


def query_port43(server, domain, port=43, timeout=WHOIS_TIMEOUT):
    """Raw port-43 whois query. Returns the response text."""
    try:
        sock = socket.create_connection((server, port), timeout=timeout)
    except (TimeoutError, socket.timeout):
        raise LookupFailure(502, "upstream_timeout",
                            f"The registry whois server {server} did not accept a "
                            f"connection within {timeout} seconds for {domain}.")
    except OSError as exc:
        raise LookupFailure(502, "upstream_unreachable",
                            f"Could not open a port-43 connection to the registry "
                            f"whois server {server} for {domain}: {exc}")
    try:
        sock.settimeout(timeout)
        sock.sendall((domain + "\r\n").encode())
        chunks, total = [], 0
        while total < WHOIS_MAX_BYTES:
            try:
                chunk = sock.recv(8192)
            except (TimeoutError, socket.timeout):
                raise LookupFailure(502, "upstream_timeout",
                                    f"The registry whois server {server} stopped "
                                    f"answering mid-response for {domain}.")
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    finally:
        sock.close()
    return b"".join(chunks).decode("utf-8", errors="replace")


def parse_whois_text(text, domain, tld, server):
    lowered = text.lower()
    if domain.lower() not in lowered:
        raise LookupFailure(502, "upstream_error",
                            f"The response from {server} did not mention {domain}; "
                            "treating it as an unreadable registry response rather "
                            "than returning blank fields.")
    registered = not any(re.search(p, lowered) for p in _NOT_FOUND_RES)
    record = {"domain": domain, "tld": tld, "registered": registered,
              "source": "whois-port43", "registry_server": server,
              "registrar": None, "registrant": None,
              "created": None, "updated": None, "expires": None,
              "status": [], "nameservers": [], "dnssec": None, "events": []}
    if not registered:
        return record
    lines = text.splitlines()
    nameservers, statuses = [], []
    in_ns_block = False
    registrar_name = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        low = stripped.lower()
        m = re.match(r"(?i)(?:nservers?|name\s*servers?|nameservers?|dns servers?)\s*:\s*(\S*)", stripped)
        if m:
            if m.group(1):
                nameservers.append(m.group(1).rstrip(".").lower())
                in_ns_block = False
            else:
                in_ns_block = True
            continue
        if in_ns_block:
            host = re.fullmatch(r"([a-z0-9.-]+\.[a-z]{2,})(\s+\S+)?", low)
            if host:
                nameservers.append(host.group(1).rstrip("."))
                continue
            in_ns_block = False
        m = re.match(r"(?i)registrar\s*:\s*(.*)$", stripped)
        if m:
            registrar_name = m.group(1).strip() or None
            if registrar_name is None and i + 1 < len(lines):
                nm = re.match(r"(?i)name\s*:\s*(.+)$", lines[i + 1].strip())
                if nm:
                    registrar_name = nm.group(1).strip()
            continue
        m = re.match(r"(?i)(?:domain\s+)?status\s*:\s*(.+)$", stripped)
        if m:
            statuses.append(m.group(1).strip())
            continue
        m = re.match(r"(?i)registrant\s*:\s*(.+)$", stripped)
        if m and record["registrant"] is None:
            record["registrant"] = {"organization": m.group(1).strip(), "country": None}
            continue
        for field, pattern in (
            ("created", r"(?i)(?:created|creation date|registered on|registration date|registered|domain created|created on)\s*:\s*(.+)$"),
            ("expires", r"(?i)(?:expires|expiry date|expiration date|expire date|valid until|renewal date|paid-till)\s*:\s*(.+)$"),
            ("updated", r"(?i)(?:updated|last updated|last modified|modified|changed|last update|updated date)\s*:\s*(.+)$"),
        ):
            if record[field] is None:
                dm = re.match(pattern, stripped)
                if dm:
                    record[field] = _parse_date(dm.group(1))
                    break
    record["nameservers"] = sorted(set(nameservers))
    record["status"] = sorted(set(statuses))
    if registrar_name:
        record["registrar"] = {"name": registrar_name, "iana_id": None, "url": None}
    if tld == "de":
        record["registry_note"] = ("DENIC publishes a restricted record by design; "
                                   "only the fields shown are released over port 43.")
    return record


def fetch_whois43(domain, tld):
    server = PORT43_SERVERS[tld]
    text = query_port43(server, domain)
    return parse_whois_text(text, domain, tld, server)


# ---------------------------------------------------------------- lookup core

def fetch_live(domain, tld):
    mapping, _ = get_bootstrap()
    if tld in mapping:
        return fetch_rdap(mapping[tld], domain, tld)
    if tld in PORT43_SERVERS:
        return fetch_whois43(domain, tld)
    raise LookupFailure(422, "unsupported_tld",
                        f"The .{tld} registry publishes no RDAP endpoint and we "
                        "have no port-43 route for it. See /tlds for the coverage map.")


def _cache_block(entry, cached, fresh, stale):
    age = 0 if entry is None else max(0, int(time.time() - entry["fetched_at"]))
    return {"cached": cached, "age_seconds": age if cached or stale else 0,
            "ttl_seconds": entry["ttl"] if entry else CACHE_TTL,
            "fresh_fetch": bool(fresh) or not cached,
            "served_stale": stale}


def do_lookup(domain, tld, fresh):
    now = time.time()
    with _cache_lock:
        entry = _cache.get(domain)
    if entry and not fresh and now - entry["fetched_at"] < entry["ttl"]:
        record = dict(entry["record"])
        record["cache"] = _cache_block(entry, cached=True, fresh=False, stale=False)
        return 200, record
    try:
        record = fetch_live(domain, tld)
    except LookupFailure as exc:
        if entry is not None:
            stale_record = dict(entry["record"])
            stale_record["cache"] = _cache_block(entry, cached=True, fresh=fresh, stale=True)
            stale_record["stale_reason"] = exc.detail
            return 200, stale_record
        return exc.status, {"error": exc.error, "detail": exc.detail, "domain": domain}
    ttl = CACHE_TTL if record["registered"] else NEGATIVE_TTL
    entry = {"record": record, "fetched_at": now, "ttl": ttl}
    with _cache_lock:
        _cache[domain] = entry
    out = dict(record)
    out["cache"] = _cache_block(entry, cached=False, fresh=fresh, stale=False)
    return 200, out


def _fresh_flag(params):
    for key in ("fresh", "force"):
        if params.get(key, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


# ---------------------------------------------------------------- endpoints

def lookup(params):
    try:
        domain, tld = normalize_domain(params.get("domain"))
    except LookupFailure as exc:
        return exc.status, {"error": exc.error, "detail": exc.detail}
    return do_lookup(domain, tld, _fresh_flag(params))


def lookup_path(params):
    try:
        domain, tld = normalize_domain(params.get("domain"))
    except LookupFailure as exc:
        return exc.status, {"error": exc.error, "detail": exc.detail}
    return do_lookup(domain, tld, _fresh_flag(params))


def tlds(params):
    mapping, publication = get_bootstrap()
    coverage = {}
    for tld in COMPLAINT_TLDS:
        coverage[tld] = "rdap" if tld in mapping else (
            "whois-port43" if tld in PORT43_SERVERS else "unsupported")
    return 200, {"rdap_tld_count": len(mapping),
                 "bootstrap_publication": publication,
                 "bootstrap_seeded_fallback": _bootstrap["seeded"],
                 "port43_tlds": {k: v for k, v in sorted(PORT43_SERVERS.items())},
                 "complaint_tld_coverage": coverage,
                 "note": "RDAP coverage comes from the live IANA bootstrap "
                         "(data.iana.org/rdap/dns.json). TLDs without an RDAP "
                         "endpoint are queried live on the registry's own "
                         "port-43 whois server."}


def health(params):
    mapping, publication = get_bootstrap()
    with _cache_lock:
        cached = len(_cache)
    return 200, {"status": "ok", "service": "whoisbase",
                 "uptime_target": "99.9%",
                 "rdap_tlds": len(mapping),
                 "port43_tlds": sorted(PORT43_SERVERS),
                 "bootstrap_publication": publication,
                 "cached_records": cached,
                 "note": "Live registry lookups via RDAP (IANA bootstrap) with a "
                         "port-43 fallback. Records are cached at most 300 seconds; "
                         "every response reports its cache state and age, and "
                         "?fresh=true always refetches from the registry."}


if __name__ == "__main__":
    run({"/lookup": lookup, "/domain/{domain}": lookup_path,
         "/tlds": tlds, "/health": health},
        int(os.environ.get("PORT", "8110")), "whoisbase")
