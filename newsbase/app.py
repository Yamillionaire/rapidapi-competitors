"""NewsBase Headlines - competitor to Google News (BFD) on RapidAPI.

Incumbent verified 2026-10-28: 7,316 subscribers, rated 3/5, pricing
Basic free, Pro $25, Ultra $50, Mega $100. Complaints in its Discussions:
responses that are not valid JSON, and a broken image proxy that serves
dead article images.
This service: RSS aggregation on the shared scaffold. Sources are Google
News RSS (top headlines, search, topic sections, country/language
editions) plus direct RSS from major outlets. Feeds are parsed into
typed records on this server and serialized by us, so every response is
valid JSON by construction; upstream content is never passed through
raw. There is deliberately NO image proxy: when a feed carries a
publisher image URL we return that URL directly, and when it does not,
the field is omitted instead of routed through anything that can break.
Feeds are TTL-cached; on upstream failure the last good edition is
served flagged stale instead of an error.
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8109).
"""
import gzip
import html as html_lib
import os
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run, cache_get, cache_set

UA = "Mozilla/5.0 (compatible; NewsBaseBot/1.0; +https://rapidapi.com/YamilLittle/api/newsbase-headlines)"
TIMEOUT = 20
MAX_BYTES = 4_000_000
FEED_TTL = 600  # seconds

TOPICS = ["WORLD", "NATION", "BUSINESS", "TECHNOLOGY",
          "ENTERTAINMENT", "SPORTS", "SCIENCE", "HEALTH"]

SOURCES = {
    "bbc": ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    "npr": ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
    "guardian": ("The Guardian", "https://www.theguardian.com/world/rss"),
    "aljazeera": ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    "nytimes": ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
}

MEDIA_NS = "{http://search.yahoo.com/mrss/}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(MAX_BYTES + 1)
        encoding = resp.headers.get("Content-Encoding", "")
    if len(raw) > MAX_BYTES:
        raise ValueError(f"feed exceeds the {MAX_BYTES} byte cap")
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


_TAG_RE = re.compile(r"<[^>]+>")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(text, cap=None):
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = _CTRL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if cap and len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0].strip()
    return text


def parse_date(raw):
    """RFC 822 (RSS) or ISO 8601 (Atom) -> ISO 8601 UTC string, or None."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _child_text(elem, tag):
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _article(title, link, publisher, published_raw, summary_raw, image_url):
    article = {
        "title": clean_text(title),
        "link": (link or "").strip(),
        "publisher": clean_text(publisher),
        "published": parse_date(published_raw),
        "summary": clean_text(summary_raw, cap=300),
    }
    if image_url:
        # The publisher's own URL, returned directly. Never proxied.
        article["image"] = image_url.strip()
    return article


def parse_feed(raw):
    """Parse RSS 2.0 or Atom into a list of article dicts.

    Raises on malformed XML; callers turn that into a structured error
    or a stale-cache serve. This normalization step is the product: the
    incumbent's invalid-JSON complaint came from passing upstream
    content through, which we never do.
    """
    root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    articles = []
    if root.tag == f"{ATOM_NS}feed" or root.tag == "feed":
        feed_title = _child_text(root, f"{ATOM_NS}title") or _child_text(root, "title")
        for entry in root.findall(f"{ATOM_NS}entry"):
            link = ""
            for link_elem in entry.findall(f"{ATOM_NS}link"):
                if link_elem.get("rel") in (None, "alternate") and link_elem.get("href"):
                    link = link_elem.get("href")
                    break
            articles.append(_article(
                _child_text(entry, f"{ATOM_NS}title"), link, feed_title,
                _child_text(entry, f"{ATOM_NS}published") or _child_text(entry, f"{ATOM_NS}updated"),
                _child_text(entry, f"{ATOM_NS}summary"), ""))
        return [a for a in articles if a["title"] and a["link"]]
    channel = root.find("channel")
    if channel is None:
        raise ValueError("feed has no channel element")
    feed_title = _child_text(channel, "title")
    for item in channel.findall("item"):
        image = ""
        for tag in (f"{MEDIA_NS}content", f"{MEDIA_NS}thumbnail"):
            media = item.find(tag)
            if media is not None and media.get("url"):
                image = media.get("url")
                break
        source = item.find("source")
        publisher = source.text.strip() if source is not None and source.text else feed_title
        link = _child_text(item, "link")
        if not link:
            guid = _child_text(item, "guid")
            if guid.startswith("http"):
                link = guid
        articles.append(_article(
            _child_text(item, "title"), link, publisher,
            _child_text(item, "pubDate"), _child_text(item, "description"), image))
    seen = set()
    unique = []
    for a in articles:
        if a["title"] and a["link"] and a["link"] not in seen:
            seen.add(a["link"])
            unique.append(a)
    return unique


def get_feed(url):
    """Return (articles, stale_flag). Raises if the feed fails with no cache."""
    cached, is_stale = cache_get(url)
    if cached is not None and not is_stale:
        return cached, False
    try:
        articles = parse_feed(fetch_bytes(url))
        if not articles:
            raise ValueError("feed returned no articles")
        cache_set(url, articles, FEED_TTL)
        return articles, False
    except Exception:
        if cached is not None:
            return cached, True
        raise


def _edition(params):
    country = params.get("country", "US").strip().upper()
    language = params.get("language", "en").strip().lower()
    if not re.fullmatch(r"[A-Z]{2}", country):
        return None, (422, {"error": "invalid_parameter",
                            "detail": "country must be a 2-letter code such as US, GB, IN, DE."})
    if not re.fullmatch(r"[a-z]{2}", language):
        return None, (422, {"error": "invalid_parameter",
                            "detail": "language must be a 2-letter code such as en, es, de, fr."})
    return (country, language), None


def _limit(params):
    try:
        return min(max(int(params.get("limit", "20")), 1), 50), None
    except ValueError:
        return None, (422, {"error": "invalid_parameter",
                            "detail": "limit must be an integer between 1 and 50."})


def _google_url(path, country, language):
    hl = f"{language}-{country}"
    return f"https://news.google.com/rss{path}?hl={hl}&gl={country}&ceid={country}:{language}"


def _serve(params, url, feed_label, extra=None):
    limit, err = _limit(params)
    if err:
        return err
    try:
        articles, stale = get_feed(url)
    except urllib.error.HTTPError as exc:
        return 502, {"error": "upstream_http_error",
                     "detail": f"The news feed returned HTTP {exc.code}. Try again shortly."}
    except Exception as exc:
        return 502, {"error": "upstream_error",
                     "detail": f"Could not retrieve the news feed: {type(exc).__name__}: {exc}"}
    payload = {"feed": feed_label, "count": min(limit, len(articles)),
               "articles": articles[:limit], "stale": stale}
    if extra:
        payload.update(extra)
    return 200, payload


def headlines(params):
    edition, err = _edition(params)
    if err:
        return err
    country, language = edition
    url = _google_url("", country, language)
    return _serve(params, url, "top-headlines",
                  {"edition": {"country": country, "language": language}})


def search(params):
    query = params.get("q", "").strip()
    if not query:
        return 422, {"error": "missing_parameter",
                     "detail": "Provide q= with the search terms, for example q=climate summit."}
    edition, err = _edition(params)
    if err:
        return err
    country, language = edition
    url = _google_url(f"/search?q={quote_plus(query)}", country, language)
    return _serve(params, url, "search",
                  {"query": query, "edition": {"country": country, "language": language}})


def topic(params):
    name = params.get("topic", "").strip().upper()
    if name not in TOPICS:
        return 422, {"error": "unknown_topic",
                     "detail": f"topic must be one of: {', '.join(TOPICS)}."}
    edition, err = _edition(params)
    if err:
        return err
    country, language = edition
    url = _google_url(f"/headlines/section/topic/{name}", country, language)
    return _serve(params, url, f"topic-{name.lower()}",
                  {"topic": name, "edition": {"country": country, "language": language}})


def source(params):
    key = params.get("source", "").strip().lower()
    if key not in SOURCES:
        return 422, {"error": "unknown_source",
                     "detail": f"source must be one of: {', '.join(sorted(SOURCES))}."}
    name, url = SOURCES[key]
    return _serve(params, url, f"source-{key}", {"publisher": name})


def topics(params):
    return 200, {"topics": TOPICS,
                 "sources": {k: v[0] for k, v in SOURCES.items()},
                 "editions": "Any country (2-letter) and language (2-letter) pair "
                             "Google News publishes, for example country=GB&language=en "
                             "or country=IN&language=hi.",
                 "image_policy": "Publisher image URLs are returned directly when a "
                                 "feed provides them and omitted when it does not. "
                                 "Images are never proxied."}


def health(params):
    return 200, {"status": "ok", "service": "newsbase-headlines",
                 "uptime_target": "99.9%",
                 "note": "Every response is serialized by this server from parsed feed "
                         "records, so it is valid JSON by construction. Article images "
                         "are the publishers' own URLs, returned directly, never proxied."}


if __name__ == "__main__":
    run({"/headlines": headlines, "/search": search,
         "/topic/{topic}": topic, "/source/{source}": source,
         "/topics": topics, "/health": health},
        int(os.environ.get("PORT", "8109")), "newsbase-headlines")
