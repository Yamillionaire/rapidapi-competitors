"""SwiftRewrite - competitor to Paraphrasing and Rewriter API (NeuralWriter).

Incumbent verified 2026-10-28: 5,632 subscribers, rated 3/5 (21 votes),
latency 9,978ms under a "Very Fast" claim, paid tiers capped at 1 req/sec.
Complaints: 500s, unexplained "text is too long or too short" errors,
rewrites changing character names, unanswered support threads.
This service: Gemini Flash rewriting (1-3s) when GEMINI_API_KEY is set,
with a built-in rules engine as a labeled fallback so the endpoint never
hard-fails. Limits are documented and every rejection states the limit
and the length received. Capitalized names are verified in the output.
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8106).
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run

MIN_CHARS = 10
MAX_CHARS = 2000
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MODES = {"standard": 0.4, "fluency": 0.6, "creative": 0.9}

# Small built-in synonym map for the fallback engine (never the headline).
_SYNONYMS = {
    "good": "solid", "great": "excellent", "big": "large", "small": "compact",
    "fast": "quick", "quickly": "rapidly", "important": "key", "very": "highly",
    "many": "numerous", "often": "frequently", "use": "use", "used": "applied",
    "make": "create", "made": "created", "get": "receive", "got": "received",
    "show": "demonstrate", "shows": "demonstrates", "help": "assist",
    "helps": "assists", "start": "begin", "started": "began", "end": "finish",
    "buy": "purchase", "bought": "purchased", "cheap": "affordable",
    "expensive": "costly", "happy": "pleased", "sad": "unhappy",
    "hard": "difficult", "easy": "straightforward", "new": "fresh",
    "old": "established", "people": "individuals", "things": "items",
    "a lot of": "many", "lots of": "many", "in order to": "to",
    "due to the fact that": "because", "at this point in time": "now",
    "in the event that": "if", "has the ability to": "can",
    "is able to": "can", "a large number of": "many",
}


def builtin_rewrite(text):
    out = text
    for phrase, repl in sorted(_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(phrase)}\b", repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\ba (?=[aeiouAEIOU])", "an ", out)  # article agreement after swaps
    out = re.sub(r"\bA (?=[aeiouAEIOU])", "An ", out)
    return out


def extract_names(text):
    """Capitalized multi or single words that look like proper names."""
    names = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b", text)
    sentence_starts = set()
    for sent in re.split(r"(?<=[.!?])\s+", text):
        m = re.match(r"\s*([A-Z][a-z]+)", sent or "")
        if m:
            sentence_starts.add(m.group(1))
    return sorted({n for n in names if n not in sentence_starts or " " in n})


def gemini_rewrite(text, mode, names):
    name_rule = ""
    if names:
        name_rule = (" Keep these proper names exactly as written, character for character: "
                     + ", ".join(names) + ".")
    prompt = (f"Rewrite the following text in your own words, preserving its meaning, "
              f"facts, and tone. Mode: {mode}.{name_rule} Return only the rewritten text.\n\n{text}")
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": MODES[mode], "maxOutputTokens": 1024}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()


def _rewrite(params, strength):
    text = params.get("text", "")
    mode = params.get("mode", "standard").lower()
    if mode not in MODES:
        return 422, {"error": "invalid_parameter",
                     "detail": f"mode must be one of: {', '.join(MODES)}."}
    if strength == "strong":
        mode = "creative" if mode == "standard" else mode
    n = len(text)
    if n < MIN_CHARS:
        return 422, {"error": "text_too_short",
                     "detail": f"Text is {n} characters; the minimum is {MIN_CHARS}."}
    if n > MAX_CHARS:
        return 422, {"error": "text_too_long",
                     "detail": f"Text is {n} characters; the maximum is {MAX_CHARS}. Split longer text into chunks."}
    names = extract_names(text)
    engine = "gemini"
    note = None
    if GEMINI_KEY:
        try:
            out = gemini_rewrite(text, mode, names)
            if not out:
                raise ValueError("empty model response")
        except Exception as exc:
            out = builtin_rewrite(text)
            engine = "builtin-fallback"
            note = f"Model engine unavailable ({type(exc).__name__}); answered with the built-in engine."
    else:
        out = builtin_rewrite(text)
        engine = "builtin"
        note = "AI engine key not configured on this deployment yet; answered with the built-in engine."
    preserved = all(name in out for name in names) if names else True
    return 200, {"original": text, "rewritten": out, "mode": mode, "engine": engine,
                 "engine_note": note, "names_detected": names,
                 "names_preserved": preserved,
                 "characters": n}


def paraphrase(params):
    return _rewrite(params, "standard")


def rewrite(params):
    return _rewrite(params, "strong")


def health(params):
    return 200, {"status": "ok", "service": "swiftrewrite",
                 "uptime_target": "99.9%",
                 "ai_engine": "configured" if GEMINI_KEY else "awaiting key (built-in engine active)",
                 "limits": {"min_chars": MIN_CHARS, "max_chars": MAX_CHARS},
                 "note": "Every rejection states the limit and the length received. Names are verified in the output."}


if __name__ == "__main__":
    run({"/paraphrase": paraphrase, "/rewrite": rewrite, "/health": health},
        int(os.environ.get("PORT", "8106")), "swiftrewrite")
