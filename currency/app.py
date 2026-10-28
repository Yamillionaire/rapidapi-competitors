"""StableFX Currency Rates - competitor to fyhao Currency Exchange on RapidAPI.

Incumbent verified 2026-10-28: 22,987 subscribers, service level 22%,
latency 23,769ms, repeated 503s in its own Discussions.
This service: daily reference rates (ECB via Frankfurter, Fawaz API as fallback),
cached aggressively, last-good rates served flagged stale instead of a 503.
Honest labeling: these are daily reference rates, not real-time trading quotes.
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8101).
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run, fetch_json, cache_get, cache_set

FRANK = "https://api.frankfurter.dev/v1"
FAWAZ = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base}.json"


def get_rates(base, date="latest"):
    key = f"rates:{base}:{date}"
    cached, stale = cache_get(key)
    if cached and not stale:
        return cached, True, False
    try:
        if date == "latest":
            data = fetch_json(f"{FRANK}/latest?base={base}")
        else:
            data = fetch_json(f"{FRANK}/{date}?base={base}")
        payload = {"base": data["base"], "date": data["date"], "rates": data["rates"],
                   "source": "Frankfurter (ECB reference rates)", "rate_type": "daily_reference"}
        cache_set(key, payload, 3600)
        return payload, False, False
    except Exception:
        if cached:  # never 503 when we have a last-good answer
            return cached, True, True
        # fallback feed (different source, may differ slightly; flagged in response)
        data = fetch_json(FAWAZ.format(base=base.lower()))
        rates = {k.upper(): v for k, v in data[base.lower()].items()}
        payload = {"base": base, "date": data.get("date"), "rates": rates,
                   "source": "Fawaz Currency API (fallback)", "rate_type": "daily_reference"}
        cache_set(key, payload, 3600)
        return payload, False, False


def latest(params):
    base = params.get("base", "USD").upper()
    payload, from_cache, stale = get_rates(base)
    out = dict(payload)
    symbols = params.get("symbols")
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",")}
        out["rates"] = {k: v for k, v in payload["rates"].items() if k in wanted}
    out["cached"] = from_cache
    out["stale"] = stale
    return 200, out


def convert(params):
    frm = params.get("from", "USD").upper()
    to = params.get("to", "EUR").upper()
    amount = float(params.get("amount", "1"))
    payload, from_cache, stale = get_rates(frm)
    rate = payload["rates"].get(to)
    if rate is None:
        return 422, {"error": "unsupported_currency",
                     "detail": f"No daily reference rate for {frm}->{to} on {payload['date']}."}
    return 200, {"from": frm, "to": to, "amount": amount, "rate": rate,
                 "result": round(amount * rate, 6), "date": payload["date"],
                 "source": payload["source"], "rate_type": payload["rate_type"],
                 "cached": from_cache, "stale": stale}


def historical(params):
    date = params.get("date")
    if not date:
        return 422, {"error": "missing_parameter",
                     "detail": "Provide date=YYYY-MM-DD, for example date=2024-01-15."}
    base = params.get("base", "USD").upper()
    payload, from_cache, stale = get_rates(base, date)
    out = dict(payload)
    out["cached"] = from_cache
    out["stale"] = stale
    return 200, out


def currencies(params):
    cached, stale = cache_get("currencies")
    if cached and not stale:
        return 200, {"currencies": cached, "cached": True}
    data = fetch_json(f"{FRANK}/currencies")
    cache_set("currencies", data, 86400)
    return 200, {"currencies": data, "cached": False}


def health(params):
    return 200, {"status": "ok", "service": "stablefx-currency-rates",
                 "uptime_target": "99.9%", "note": "Daily reference rates, cached; stale data is flagged, never a bare 503."}


if __name__ == "__main__":
    run({"/latest": latest, "/convert": convert, "/historical": historical,
         "/currencies": currencies, "/health": health},
        int(os.environ.get("PORT", "8101")), "stablefx-currency-rates")
