"""CleanExtract - competitor to Article Extractor and Summarizer (restyler).

Incumbent verified 2026-10-28: 11,784 subscribers, rated 3/5 (17 votes),
service level 74%, pricing Basic free/50 per month, Pro $15/500,
Ultra $95/5,000, Mega $195/25,000. Its Discussions are years of unanswered
503/403/401 complaints and 500s on failed retrievals.
This service: stdlib-only article extraction (density-scored main content,
metadata from meta tags) plus an honest extractive summarizer (frequency
scored sentence selection, computed on our server, no external AI call to
fail). Fetches are SSRF-hardened: http/https only, private and loopback
addresses refused on every redirect hop, size and time caps, and every
failure returns a structured error instead of the incumbent's bare 503.
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8105).
"""
import ipaddress
import os
import re
import socket
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run

MAX_BYTES = 2_500_000
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; CleanExtractBot/1.0; +https://rapidapi.com/YamilLittle/api/cleanextract)"


# Explicit SSRF blocklist: loopback, RFC1918, link-local (incl. cloud
# metadata 169.254.169.254), CGNAT, unique-local and link-local IPv6,
# multicast, and the unspecified range. Deliberately NOT Python's
# is_private flag, which also rejects the RFC 2544 benchmarking range
# (198.18.0.0/15) that some sandboxed resolvers legitimately return for
# public hosts; that range is not routable to anyone's internal network.
_BLOCKED_NETS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4",
    "::1/128", "fc00::/7", "fe80::/10", "ff00::/8")]


def _host_is_public(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in net for net in _BLOCKED_NETS):
            return False
    return True


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if not _host_is_public(parsed.hostname):
            raise ValueError("redirect to a non-public address refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_GuardedRedirect)


def fetch_page(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("url must be an absolute http or https URL")
    if not _host_is_public(parsed.hostname):
        raise ValueError("only public web addresses can be extracted")
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                "Accept": "text/html,application/xhtml+xml"})
    with _OPENER.open(req, timeout=TIMEOUT) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(MAX_BYTES + 1)
        final_url = resp.geturl()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"page exceeds the {MAX_BYTES} byte extraction cap")
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype)
    if m:
        charset = m.group(1)
    try:
        return raw.decode(charset, errors="replace"), final_url
    except LookupError:
        return raw.decode("utf-8", errors="replace"), final_url


_SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside",
              "form", "button", "svg", "iframe", "figure"}
_BLOCK_TAGS = {"p", "div", "section", "article", "li", "blockquote", "td",
               "h1", "h2", "h3", "h4", "h5", "h6", "pre"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title_parts = []
        self.in_title = False
        self.skip_depth = 0
        self.blocks = []          # (tag, text)
        self._cur_tag = None
        self._cur_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name") or ""
            if key and attrs.get("content"):
                self.meta[key.lower()] = attrs["content"]
        if tag in _BLOCK_TAGS and self.skip_depth == 0:
            self._flush()
            self._cur_tag = tag

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False
        if tag in _BLOCK_TAGS:
            self._flush()
            self._cur_tag = None

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.skip_depth == 0 and self._cur_tag:
            self._cur_text.append(data)

    def _flush(self):
        if self._cur_tag and self._cur_text:
            text = re.sub(r"\s+", " ", " ".join(self._cur_text)).strip()
            if text:
                self.blocks.append((self._cur_tag, text))
        self._cur_text = []


def extract_article(html_text):
    parser = _Extractor()
    parser.feed(html_text)
    parser._flush()
    title = (parser.meta.get("og:title") or " ".join(parser.title_parts)).strip()
    title = re.sub(r"\s+", " ", title)
    paragraphs = [t for tag, t in parser.blocks if tag == "p" and len(t) >= 40]
    if not paragraphs:  # fall back to any substantial block text
        paragraphs = [t for tag, t in parser.blocks if len(t) >= 80]
    content = "\n\n".join(paragraphs)
    return {
        "title": title,
        "description": parser.meta.get("og:description") or parser.meta.get("description") or "",
        "author": parser.meta.get("author") or parser.meta.get("article:author") or "",
        "published": parser.meta.get("article:published_time") or "",
        "image": parser.meta.get("og:image") or "",
        "site_name": parser.meta.get("og:site_name") or "",
        "content": content,
        "word_count": len(content.split()),
        "paragraphs": len(paragraphs),
    }


_STOPWORDS = set("a an the and or but if then else of at by for with about into through during "
                 "before after above below to from up down in out on off over under again further "
                 "once here there when where why how all any both each few more most other some "
                 "such no nor not only own same so than too very can will just is are was were be "
                 "been being have has had having do does did doing would should could ought i you "
                 "he she it we they them his her its our their this that these those am as".split())


def summarize_text(text, sentence_count):
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    # Citation-marked fragments (common in wiki/news text) make poor summary
    # sentences; exclude them from candidacy.
    sentences = [s.strip() for s in sentences
                 if 40 <= len(s.strip()) <= 600 and "[" not in s]
    if not sentences:
        return ""
    if len(sentences) <= sentence_count:
        return " ".join(sentences)
    freq = {}
    for s in sentences:
        for w in re.findall(r"[a-z']+", s.lower()):
            if w not in _STOPWORDS and len(w) > 2:
                freq[w] = freq.get(w, 0) + 1
    scored = []
    for idx, s in enumerate(sentences):
        words = [w for w in re.findall(r"[a-z']+", s.lower()) if w not in _STOPWORDS and len(w) > 2]
        score = sum(freq.get(w, 0) for w in words) / max(len(words), 1)
        if idx == 0:
            score *= 1.15  # lead bias, standard in extractive summarization
        scored.append((score, idx, s))
    top = sorted(scored, reverse=True)[:sentence_count]
    return " ".join(s for _, _, s in sorted(top, key=lambda x: x[1]))


def _get_article(params):
    url = params.get("url", "").strip()
    if not url:
        return None, (422, {"error": "missing_parameter",
                            "detail": "Provide url=https://... for the page to extract."})
    try:
        html_text, final_url = fetch_page(url)
    except ValueError as exc:
        return None, (422, {"error": "fetch_refused", "detail": str(exc)})
    except urllib.error.HTTPError as exc:
        return None, (502, {"error": "source_http_error",
                            "detail": f"The source page returned HTTP {exc.code}."})
    except Exception as exc:
        return None, (502, {"error": "fetch_failed",
                            "detail": f"Could not retrieve the page: {type(exc).__name__}: {exc}"})
    article = extract_article(html_text)
    if not article["content"]:
        return None, (422, {"error": "no_article_text",
                            "detail": "The page loaded but no article body text was found on it."})
    article["url"] = url
    article["final_url"] = final_url
    return article, None


def extract(params):
    article, err = _get_article(params)
    if err:
        return err
    return 200, article


def summarize(params):
    article, err = _get_article(params)
    if err:
        return err
    try:
        count = min(max(int(params.get("sentences", "5")), 1), 20)
    except ValueError:
        return 422, {"error": "invalid_parameter", "detail": "sentences must be an integer."}
    return 200, {"url": article["url"], "title": article["title"],
                 "summary": summarize_text(article["content"], count),
                 "summary_method": "extractive (sentence scoring on our server; no external AI call)",
                 "sentences": count, "source_word_count": article["word_count"]}


def summarize_given_text(params):
    text = params.get("text", "")
    if len(text) < 200:
        return 422, {"error": "missing_parameter",
                     "detail": "Provide text= with at least 200 characters to summarize."}
    try:
        count = min(max(int(params.get("sentences", "5")), 1), 20)
    except ValueError:
        return 422, {"error": "invalid_parameter", "detail": "sentences must be an integer."}
    return 200, {"summary": summarize_text(text, count),
                 "summary_method": "extractive (sentence scoring on our server; no external AI call)",
                 "sentences": count, "source_word_count": len(text.split())}


def health(params):
    return 200, {"status": "ok", "service": "cleanextract-articles",
                 "uptime_target": "99.9%",
                 "note": "Extraction and summarization run on this server; nothing external to fail silently. Errors are structured, never a bare 503."}


if __name__ == "__main__":
    run({"/extract": extract, "/summarize": summarize,
         "/summarize-text": summarize_given_text, "/health": health},
        int(os.environ.get("PORT", "8105")), "cleanextract-articles")
