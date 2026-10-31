"""SwiftRead - article-to-speech API (the user's own product idea, 2026-10-30).

Give it an article URL (or raw text) and it returns spoken audio: the
"listen to this article" button as an API. Extraction is the lane's
proven stdlib stack, shared with CleanExtract (density-scored main
content, SSRF-hardened fetch, structured errors, never a bare 503).
Speech is synthesized with the free Microsoft Edge read-aloud neural
voices via the edge-tts package: zero marginal cost, no paid TTS, no
API key. Long text is chunked at sentence boundaries and the MP3
segments are concatenated in order, so playback is seamless.

The shared scaffold (shared/rapidapi_server.py) speaks GET/JSON only,
so this service carries its own small server that keeps the scaffold's
exact conventions: the RapidAPI proxy-secret gate (401 JSON without
the X-RapidAPI-Proxy-Secret header, /health always open) and explicit
structured JSON errors for every failure that is not audio.

Endpoints:
  POST /read-url  {url, voice?, rate?}          -> audio/mpeg
  POST /speak     {text, voice?, rate?}         -> audio/mpeg
  GET  /voices                                  -> the curated voice list
  GET  /health                                  -> service status
Run: python3 app.py (PORT env, default 8112). Needs: pip install edge-tts.
"""
import asyncio
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from urllib.parse import urlparse

SERVICE = "swiftread"
MAX_CHARS = 15_000          # extracted or supplied text cap per request
CHUNK_CHARS = 1_600         # per-synthesis chunk, packed at sentence boundaries
MAX_BODY = 300_000          # request body byte cap
DEFAULT_VOICE = "en-US-AriaNeural"

# Curated natural neural voices (Microsoft Edge read-aloud set).
VOICES = [
    {"id": "en-US-AriaNeural",       "name": "Aria",       "locale": "en-US", "gender": "Female", "style": "Warm, natural newsreader"},
    {"id": "en-US-JennyNeural",      "name": "Jenny",      "locale": "en-US", "gender": "Female", "style": "Friendly, conversational"},
    {"id": "en-US-MichelleNeural",   "name": "Michelle",   "locale": "en-US", "gender": "Female", "style": "Clear, professional"},
    {"id": "en-US-GuyNeural",        "name": "Guy",        "locale": "en-US", "gender": "Male",   "style": "Steady, broadcast"},
    {"id": "en-US-ChristopherNeural","name": "Christopher","locale": "en-US", "gender": "Male",   "style": "Calm, documentary"},
    {"id": "en-US-EricNeural",       "name": "Eric",       "locale": "en-US", "gender": "Male",   "style": "Measured, articulate"},
    {"id": "en-GB-SoniaNeural",      "name": "Sonia",      "locale": "en-GB", "gender": "Female", "style": "Polished British newsreader"},
    {"id": "en-GB-LibbyNeural",      "name": "Libby",      "locale": "en-GB", "gender": "Female", "style": "Bright British"},
    {"id": "en-GB-RyanNeural",       "name": "Ryan",       "locale": "en-GB", "gender": "Male",   "style": "Warm British"},
    {"id": "en-GB-ThomasNeural",     "name": "Thomas",     "locale": "en-GB", "gender": "Male",   "style": "Formal British"},
]
_VOICE_IDS = {v["id"] for v in VOICES}


# --------------------------------------------------------------------------
# Article fetching + extraction: the CleanExtract stack, shared verbatim in
# approach (SSRF-hardened fetch, density-scored block extraction).
# --------------------------------------------------------------------------
MAX_BYTES = 2_500_000
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; SwiftReadBot/1.0; +https://rapidapi.com/YamilLittle/api/swiftread)"

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
        raise ValueError("only public web addresses can be read")
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                "Accept": "text/html,application/xhtml+xml"})
    with _OPENER.open(req, timeout=TIMEOUT) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(MAX_BYTES + 1)
        final_url = resp.geturl()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"page exceeds the {MAX_BYTES} byte fetch cap")
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
        self.blocks = []
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
    if not paragraphs:
        paragraphs = [t for tag, t in parser.blocks if len(t) >= 80]
    content = "\n\n".join(paragraphs)
    return {"title": title, "content": content,
            "word_count": len(content.split()), "paragraphs": len(paragraphs)}


# --------------------------------------------------------------------------
# Speech synthesis (edge-tts; lazy import so /health and /voices answer
# even on a host where the package is missing, with an honest 503 there).
# --------------------------------------------------------------------------
def normalize_rate(rate):
    """Accept a multiplier (0.85) or a signed percent string ('-15%').
    Returns an edge-tts rate string clamped to -50%..+100%, or None."""
    if rate is None:
        return "+0%"
    if isinstance(rate, (int, float)) and not isinstance(rate, bool):
        pct = round((float(rate) - 1.0) * 100)
    elif isinstance(rate, str):
        m = re.fullmatch(r"\s*([+-]?\d{1,3})\s*%\s*", rate)
        if not m:
            return None
        pct = int(m.group(1))
    else:
        return None
    pct = max(-50, min(100, pct))
    return f"{pct:+d}%"


def chunk_text(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    chunks, cur = [], ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        while len(sent) > CHUNK_CHARS:  # pathological single sentence: hard split
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(sent[:CHUNK_CHARS])
            sent = sent[CHUNK_CHARS:]
        if len(cur) + len(sent) + 1 <= CHUNK_CHARS:
            cur = (cur + " " + sent).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = sent
    if cur:
        chunks.append(cur)
    return chunks


async def _synth_chunk(edge_tts, text, voice, rate):
    # Honor a proxy from the environment when one is configured (some
    # sandboxes route egress through one); on Render none is set and the
    # connection is direct. edge-tts/aiohttp ignores env proxies by default.
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy"))
    kwargs = {"proxy": proxy} if proxy else {}
    # edge-tts pins certifi's CA bundle for its websocket; point it at the
    # system trust store instead, so TLS-intercepting egress proxies (whose
    # CA is installed system-wide) verify too. On Render the system store
    # is the standard root set, so behavior there is unchanged.
    import ssl
    import edge_tts.communicate as _ec
    _ec._SSL_CTX = ssl.create_default_context()
    kwargs = {"proxy": proxy} if proxy else {}
    comm = edge_tts.Communicate(text, voice, rate=rate, **kwargs)
    buf = bytearray()
    async for part in comm.stream():
        if part["type"] == "audio":
            buf.extend(part["data"])
    return bytes(buf)


def synthesize(text, voice, rate):
    try:
        import edge_tts
    except ImportError:
        return None, (503, {"error": "engine_not_configured",
                            "detail": "The speech engine package is not installed on this deployment."})
    chunks = chunk_text(text)
    audio = bytearray()
    try:
        for chunk in chunks:
            audio.extend(asyncio.run(_synth_chunk(edge_tts, chunk, voice, rate)))
    except Exception as exc:
        return None, (502, {"error": "synthesis_failed",
                            "detail": f"Speech synthesis failed: {type(exc).__name__}: {exc}"})
    if not audio:
        return None, (502, {"error": "synthesis_failed",
                            "detail": "Speech synthesis returned no audio."})
    return (bytes(audio), {"chunks": len(chunks), "characters": len(text),
                           "voice": voice, "rate": rate}), None


def _validate_voice_rate(body):
    voice = body.get("voice") or DEFAULT_VOICE
    if voice not in _VOICE_IDS:
        return None, None, (422, {"error": "invalid_parameter",
                                  "detail": f"voice must be one of: {', '.join(sorted(_VOICE_IDS))}. See GET /voices."})
    rate = normalize_rate(body.get("rate"))
    if rate is None:
        return None, None, (422, {"error": "invalid_parameter",
                                  "detail": "rate must be a multiplier between 0.5 and 2.0 or a percent string like '-15%' (clamped to -50%..+100%)."})
    return voice, rate, None


def _cap_check(text):
    if len(text) > MAX_CHARS:
        return 422, {"error": "text_too_long",
                     "detail": f"Text is {len(text)} characters; the per-request maximum is {MAX_CHARS}. Split longer articles into parts."}
    return None


def speak(body):
    text = (body.get("text") or "").strip()
    if not text:
        return None, (422, {"error": "missing_parameter",
                            "detail": "Provide text= with the text to read aloud."})
    err = _cap_check(text)
    if err:
        return None, err
    voice, rate, err = _validate_voice_rate(body)
    if err:
        return None, err
    return synthesize(text, voice, rate)


def read_url(body):
    url = (body.get("url") or "").strip()
    if not url:
        return None, (422, {"error": "missing_parameter",
                            "detail": "Provide url=https://... for the article to read aloud."})
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
    err = _cap_check(article["content"])
    if err:
        return None, err
    voice, rate, err = _validate_voice_rate(body)
    if err:
        return None, err
    result = synthesize(article["content"], voice, rate)
    if result[1] is not None:
        return result
    audio, meta = result
    meta.update({"title": article["title"], "url": url, "final_url": final_url,
                 "source_word_count": article["word_count"]})
    return (audio, meta), None


def voices(params):
    return 200, {"voices": VOICES, "default": DEFAULT_VOICE,
                 "note": "Natural neural voices from the Microsoft Edge read-aloud set. Pass the id as voice= in /speak or /read-url."}


def health(params):
    try:
        import edge_tts  # noqa: F401
        engine = "edge-tts (Microsoft Edge neural voices)"
    except ImportError:
        engine = "NOT INSTALLED on this deployment"
    return 200, {"status": "ok", "service": SERVICE,
                 "uptime_target": "99.9%",
                 "engine": engine,
                 "limits": {"max_characters_per_request": MAX_CHARS},
                 "endpoints": ["POST /read-url", "POST /speak", "GET /voices", "GET /health"],
                 "note": "Successful calls return audio/mpeg directly. Every failure is a structured JSON error, never a bare 503."}


# --------------------------------------------------------------------------
# Server: scaffold conventions (gate + structured errors), extended with
# POST JSON bodies and binary audio responses.
# --------------------------------------------------------------------------
def run_server(port):
    proxy_secret = os.environ.get("RAPIDAPI_PROXY_SECRET")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _gate_ok(self, path):
            if not proxy_secret or path == "/health":
                return True
            if self.headers.get("X-RapidAPI-Proxy-Secret") != proxy_secret:
                self._json(401, {"error": "unauthorized",
                                 "detail": "Missing or invalid RapidAPI proxy secret."})
                return False
            return True

        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            if not self._gate_ok(path):
                return
            if path == "/health":
                status, payload = health({})
            elif path == "/voices":
                status, payload = voices({})
            else:
                return self._json(404, {"error": "not_found",
                                        "detail": f"No endpoint at {path}. See /health for service info."})
            self._json(status, payload)

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            if not self._gate_ok(path):
                return
            if path not in ("/speak", "/read-url"):
                return self._json(404, {"error": "not_found",
                                        "detail": f"No endpoint at {path}. See /health for service info."})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY:
                return self._json(422, {"error": "invalid_body",
                                        "detail": f"Send a JSON body of at most {MAX_BODY} bytes."})
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
            except Exception:
                return self._json(422, {"error": "invalid_body",
                                        "detail": "Request body must be a JSON object."})
            result, err = (speak(body) if path == "/speak" else read_url(body))
            if err:
                status, payload = err
                return self._json(status, payload)
            audio, meta = result
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("X-SwiftRead-Voice", meta["voice"])
            self.send_header("X-SwiftRead-Characters", str(meta["characters"]))
            self.send_header("X-SwiftRead-Chunks", str(meta["chunks"]))
            if meta.get("title"):
                safe_title = meta["title"].encode("ascii", "ignore").decode().strip()[:120]
                if safe_title:
                    self.send_header("X-SwiftRead-Title", safe_title)
            self.end_headers()
            self.wfile.write(audio)

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    run_server(int(os.environ.get("PORT", "8112")))
