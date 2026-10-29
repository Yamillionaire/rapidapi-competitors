"""SwiftTranslate - competitor to Google Translate by Hark Translate.

Incumbent verified 2026-10-28: 5,975 subscribers, rated 4/5 (41 votes),
service level 84%, pricing $9/$19/$39 on the paid tiers, and a fresh
unanswered "API unreachable" complaint in its Discussions.
This service: Gemini 3.6 Flash translation behind the same v2 surface
and response envelope as the incumbent (translate / detect / languages),
so incumbent code migrates by changing host and key. Reliability is the
product: explicit JSON errors always, one automatic engine retry, and a
24h cache that serves stale-on-error flagged as such instead of failing.
No key configured: translate/detect answer an explicit 503 JSON error
naming the problem; nothing is ever faked. Honest engine label on every
response ("gemini"). Zero dependencies beyond the shared scaffold.
Run: python3 app.py (PORT env, default 8108).
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import cache_get, cache_set, run

MAX_CHARS = 5000
CACHE_TTL = 24 * 3600
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# The languages this service supports (ISO codes, Google Translate set).
LANGUAGES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian",
    "bn": "Bengali", "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan",
    "ceb": "Cebuano", "ny": "Chichewa", "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)", "co": "Corsican", "hr": "Croatian",
    "cs": "Czech", "da": "Danish", "nl": "Dutch", "en": "English",
    "eo": "Esperanto", "et": "Estonian", "tl": "Filipino", "fi": "Finnish",
    "fr": "French", "fy": "Frisian", "gl": "Galician", "ka": "Georgian",
    "de": "German", "el": "Greek", "gu": "Gujarati", "ht": "Haitian Creole",
    "ha": "Hausa", "haw": "Hawaiian", "iw": "Hebrew", "he": "Hebrew",
    "hi": "Hindi", "hmn": "Hmong", "hu": "Hungarian", "is": "Icelandic",
    "ig": "Igbo", "id": "Indonesian", "ga": "Irish", "it": "Italian",
    "ja": "Japanese", "jw": "Javanese", "kn": "Kannada", "kk": "Kazakh",
    "km": "Khmer", "ko": "Korean", "ku": "Kurdish (Kurmanji)",
    "ky": "Kyrgyz", "lo": "Lao", "la": "Latin", "lv": "Latvian",
    "lt": "Lithuanian", "lb": "Luxembourgish", "mk": "Macedonian",
    "mg": "Malagasy", "ms": "Malay", "ml": "Malayalam", "mt": "Maltese",
    "mi": "Maori", "mr": "Marathi", "mn": "Mongolian", "my": "Myanmar (Burmese)",
    "ne": "Nepali", "no": "Norwegian", "or": "Odia (Oriya)", "ps": "Pashto",
    "fa": "Persian", "pl": "Polish", "pt": "Portuguese", "pa": "Punjabi",
    "ro": "Romanian", "ru": "Russian", "sm": "Samoan", "gd": "Scots Gaelic",
    "sr": "Serbian", "st": "Sesotho", "sn": "Shona", "sd": "Sindhi",
    "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian", "so": "Somali",
    "es": "Spanish", "su": "Sundanese", "sw": "Swahili", "sv": "Swedish",
    "tg": "Tajik", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "ug": "Uyghur",
    "uz": "Uzbek", "vi": "Vietnamese", "cy": "Welsh", "xh": "Xhosa",
    "yi": "Yiddish", "yo": "Yoruba", "zu": "Zulu",
}


def _normalize(code):
    """Map a user-supplied language code to our canonical form, or None."""
    if not code:
        return None
    c = code.strip()
    if c in LANGUAGES:
        return c
    low = c.lower()
    for known in LANGUAGES:
        if known.lower() == low:
            return known
    if low in ("zh", "zh-hans", "chinese"):
        return "zh-CN"
    return None


def _parse_json_loose(text):
    """Best-effort JSON object extraction from a model reply."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except Exception:
            return None
    return None


def _gemini(prompt, max_tokens, temperature=0.2):
    """One generateContent call, retried once on transient 5xx/timeout.

    Two transient Google 503s were observed in pre-launch testing; the
    retry (plus the caller's stale cache) is the reliability fix for the
    incumbent's 'API unreachable' complaint.
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": temperature,
                                    "maxOutputTokens": max_tokens,
                                    "responseMimeType": "application/json"}}
    last_exc = None
    for attempt in range(2):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code < 500 and exc.code != 429:
                raise
        except Exception as exc:
            last_exc = exc
        if attempt == 0:
            time.sleep(1.5)
    raise last_exc


def _engine_unconfigured():
    return 503, {"error": "engine_not_configured",
                 "detail": "The translation engine is not configured on this deployment yet "
                           "(no API key). /languages and /health work; translate and detect "
                           "will answer as soon as the key is set."}


def _check_text(params):
    text = params.get("q", params.get("text", ""))
    if not text:
        return None, (422, {"error": "missing_parameter",
                            "detail": "Parameter 'q' (the text) is required and was empty or missing."})
    n = len(text)
    if n > MAX_CHARS:
        return None, (422, {"error": "text_too_long",
                            "detail": f"Text is {n} characters; the maximum per request is {MAX_CHARS}. "
                                      "Split longer text into chunks."})
    return text, None


def translate(params):
    text, err = _check_text(params)
    if err:
        return err
    target_raw = params.get("target", params.get("to", ""))
    target = _normalize(target_raw)
    if target is None:
        return 422, {"error": "unsupported_language",
                     "detail": f"Target language '{target_raw}' is missing or not supported. "
                               "See /language/translate/v2/languages for the supported codes."}
    source = None
    source_raw = params.get("source", params.get("from", ""))
    if source_raw and source_raw.lower() != "auto":
        source = _normalize(source_raw)
        if source is None:
            return 422, {"error": "unsupported_language",
                         "detail": f"Source language '{source_raw}' is not supported. "
                                   "See /language/translate/v2/languages, or omit source for auto-detection."}
    cache_key = "tr:" + hashlib.sha256(
        f"{source or 'auto'}|{target}|{text}".encode()).hexdigest()
    cached, stale = cache_get(cache_key)
    if cached and not stale:
        out = dict(cached)
        out["cached"] = True
        return 200, out
    if not GEMINI_KEY:
        return _engine_unconfigured()
    if source:
        from_part = f"from {LANGUAGES[source]} ({source})"
    else:
        from_part = "from its detected source language"
    prompt = (f"You are a translation engine. Translate the text below {from_part} "
              f"to {LANGUAGES[target]} ({target}). Return ONLY a JSON object with keys "
              "\"translatedText\" (the translation) and \"detectedSourceLanguage\" "
              "(the ISO 639-1 code of the source text). Preserve formatting, line "
              "breaks, numbers and proper names exactly. Do not add commentary.\n\n"
              f"TEXT:\n{text}")
    try:
        raw = _gemini(prompt, min(8192, 2048 + len(text)))
    except Exception as exc:
        if cached:  # stale-on-error: answer with the last good value, flagged
            out = dict(cached)
            out["cached"] = True
            out["stale"] = True
            out["engine_note"] = f"Engine unavailable ({type(exc).__name__}); served the last cached translation."
            return 200, out
        return 502, {"error": "engine_error",
                     "detail": f"The translation engine did not answer after a retry "
                               f"({type(exc).__name__}). Nothing was fabricated; please retry."}
    parsed = _parse_json_loose(raw)
    if parsed and parsed.get("translatedText"):
        translated = parsed["translatedText"]
        detected = source or parsed.get("detectedSourceLanguage") or "und"
    else:
        translated = raw
        detected = source or "und"
    payload = {"data": {"translations": [{"translatedText": translated,
                                          "detectedSourceLanguage": detected}]},
               "engine": "gemini", "model": GEMINI_MODEL,
               "source_language": detected, "target_language": target,
               "characters": len(text)}
    cache_set(cache_key, payload, CACHE_TTL)
    return 200, payload


def detect(params):
    text, err = _check_text(params)
    if err:
        return err
    if not GEMINI_KEY:
        return _engine_unconfigured()
    prompt = ("You are a language detection engine. Identify the language of the "
              "text below. Return ONLY a JSON object with keys \"language\" (the "
              "ISO 639-1 code) and \"confidence\" (a number from 0 to 1).\n\n"
              f"TEXT:\n{text}")
    try:
        raw = _gemini(prompt, 1024, temperature=0.0)
    except Exception as exc:
        return 502, {"error": "engine_error",
                     "detail": f"The detection engine did not answer after a retry "
                               f"({type(exc).__name__}). Please retry."}
    parsed = _parse_json_loose(raw)
    if not parsed or not parsed.get("language"):
        return 502, {"error": "engine_error",
                     "detail": "The detection engine returned an unreadable answer. Please retry."}
    language = str(parsed["language"])
    try:
        confidence = float(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return 200, {"data": {"detections": [[{"language": language,
                                            "confidence": confidence,
                                            "isReliable": confidence >= 0.5}]]},
                 "engine": "gemini", "model": GEMINI_MODEL,
                 "characters": len(text)}


def languages(params):
    langs = [{"language": code, "name": name}
             for code, name in sorted(LANGUAGES.items())]
    return 200, {"data": {"languages": langs},
                 "count": len(langs),
                 "note": "Codes are ISO 639-1 (plus zh-CN / zh-TW). Pass one as 'target' "
                         "or 'source' to /language/translate/v2; omit source for auto-detection."}


def health(params):
    return 200, {"status": "ok", "service": "swifttranslate",
                 "uptime_target": "99.9%",
                 "engine": "gemini" if GEMINI_KEY else "awaiting key (not configured)",
                 "model": GEMINI_MODEL,
                 "languages": len(LANGUAGES),
                 "limits": {"max_chars_per_request": MAX_CHARS},
                 "note": "Explicit JSON errors always; translations are cached 24h and "
                         "served stale (flagged) rather than failing when the engine hiccups."}


if __name__ == "__main__":
    run({"/language/translate/v2": translate,
         "/language/translate/v2/detect": detect,
         "/language/translate/v2/languages": languages,
         "/health": health},
        int(os.environ.get("PORT", "8108")), "swifttranslate")
