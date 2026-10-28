"""Shared zero-dependency server scaffold for the RapidAPI competitor services.

One template, three services (currency, emailcheck, financials):
- stdlib http.server only, so it runs anywhere Python 3 runs, including Render's free tier.
- JSON in/out, explicit error objects (never a silent 204 or a bare 500).
- Optional RapidAPI proxy-secret check: when RAPIDAPI_PROXY_SECRET is set in the
  environment, requests (except /health) must carry X-RapidAPI-Proxy-Secret.
- Tiny in-memory TTL cache with stale-on-error serving: if an upstream fails,
  serve the last good value flagged stale instead of erroring.
"""
import json
import os
import threading
import time
import urllib.request
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

_cache = {}
_cache_lock = threading.Lock()


def cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
    if item and item["expires"] > time.time():
        return item["value"], False
    if item:
        return item["value"], True  # expired but present: usable as stale fallback
    return None, False


def cache_set(key, value, ttl_seconds):
    with _cache_lock:
        _cache[key] = {"value": value, "expires": time.time() + ttl_seconds}


def fetch_json(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def run(routes, port, name):
    """routes: dict path -> handler(params: dict[str,str]) -> (status:int, payload:dict)

    A route path may contain {param} segments (e.g. /v1/geo/cities/{cityId});
    matched values are merged into params. Exact paths win over patterns.
    """
    proxy_secret = os.environ.get("RAPIDAPI_PROXY_SECRET")
    patterns = []
    for route_path, route_handler in routes.items():
        if "{" in route_path:
            segments = [s for s in route_path.strip("/").split("/") if s]
            patterns.append((segments, route_handler))

    def match(path):
        if path in routes:
            return routes[path], {}
        parts = [s for s in path.strip("/").split("/") if s]
        for segments, route_handler in patterns:
            if len(segments) != len(parts):
                continue
            captured = {}
            ok = True
            for seg, part in zip(segments, parts):
                if seg.startswith("{") and seg.endswith("}"):
                    captured[seg[1:-1]] = part
                elif seg != part:
                    ok = False
                    break
            if ok:
                return route_handler, captured
        return None, {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            started = time.time()
            if proxy_secret and path != "/health":
                if self.headers.get("X-RapidAPI-Proxy-Secret") != proxy_secret:
                    return self._send(401, {"error": "unauthorized",
                                            "detail": "Missing or invalid RapidAPI proxy secret."})
            handler, captured = match(path)
            if handler is None:
                return self._send(404, {"error": "not_found",
                                        "detail": f"No endpoint at {path}. See /health for service info."})
            params.update(captured)
            try:
                status, payload = handler(params)
            except Exception as exc:  # explicit error object, never a bare stack trace to the client
                status, payload = 502, {"error": "upstream_error",
                                        "detail": f"{type(exc).__name__}: {exc}"}
            if isinstance(payload, dict):
                payload.setdefault("_meta", {"service": name,
                                             "latency_ms": round((time.time() - started) * 1000)})
            self._send(status, payload)

        def _send(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
