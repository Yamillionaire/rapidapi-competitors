"""Fundamentals competitor to ApiDojo Yahu Financials on RapidAPI (prototype).

Incumbent verified 2026-10-28: 58,328 subscribers, rated 2/5. Complaints:
annualTotalRevenues null except last period, pegRatio always null,
time-series capped at 5 series, related tickers missing, silent 204/500s.

This prototype serves the fundamentals core from SEC EDGAR company-facts:
free, public domain, no key. One call returns every reported period, so the
series is NOT capped and revenue values come straight from filings (no nulls
where the company reported). Endpoint paths mirror the incumbent's so a
switching user changes only host and key.

PEG note (honesty as product): EDGAR has actuals, not analyst estimates, so
pegRatio is returned as an explicit object explaining that, alongside a real
trailing earnings-growth figure computed from filings. Never a silent null.

Quotes are deliberately NOT in this prototype: they need a licensed feed whose
terms allow redistribution (Yahoo data is personal-use only). That feed is the
one cost decision left for launch.

Run: python3 app.py (PORT env, default 8103).
"""
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run, fetch_json, cache_get, cache_set

UA = {"User-Agent": "PowerForUsLLC admin@theelementsofhiphop.co"}
REVENUE_KEYS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "SalesRevenueNet", "SalesRevenueGoodsNet"]


def ticker_map():
    cached, stale = cache_get("edgar:tickers")
    if cached and not stale:
        return cached
    data = fetch_json("https://www.sec.gov/files/company_tickers.json", UA)
    mapping = {v["ticker"].upper(): v for v in data.values()}
    cache_set("edgar:tickers", mapping, 86400)
    return mapping


def company_facts(symbol):
    symbol = symbol.upper()
    cached, stale = cache_get(f"edgar:facts:{symbol}")
    if cached and not stale:
        return cached
    info = ticker_map().get(symbol)
    if not info:
        return None
    cik = str(info["cik_str"]).zfill(10)
    data = fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", UA)
    payload = {"symbol": symbol, "companyName": data.get("entityName") or info["title"],
               "cik": info["cik_str"], "facts": data["facts"].get("us-gaap", {})}
    cache_set(f"edgar:facts:{symbol}", payload, 86400)
    return payload


def _series(facts, keys, unit="USD"):
    """Merge across alias tags (EDGAR filers change tags over the years, for
    example Apple reported revenue under SalesRevenueNet before the current
    contract-revenue tag). First-listed tag wins per period end; later tags
    only fill gaps. Filings only, never null."""
    by_end = {}
    used = []
    for key in keys:
        node = facts.get(key)
        if not node:
            continue
        points = node.get("units", {}).get(unit, [])
        added = False
        for p in points:
            if p.get("form") in ("10-K", "10-Q") and p.get("val") is not None and p["end"] not in by_end:
                by_end[p["end"]] = {"end": p["end"], "start": p.get("start"),
                                    "value": p["val"], "form": p["form"], "tag": key}
                added = True
        if added:
            used.append(key)
    return "+".join(used) if used else None, sorted(by_end.values(), key=lambda x: x["end"])


def _annual(series):
    out = []
    for p in series:
        if p.get("start") and p.get("end"):
            days = (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days
            if 330 <= days <= 400:
                out.append(p)
    return out


def fundamentals(params):
    symbol = params.get("symbol", "").upper()
    if not symbol:
        return 422, {"error": "missing_parameter", "detail": "Provide symbol=, for example symbol=AAPL."}
    cf = company_facts(symbol)
    if cf is None:
        return 404, {"error": "unknown_symbol",
                     "detail": f"{symbol} is not in the SEC EDGAR ticker map (US-listed filers are covered in v1)."}
    rev_key, rev_all = _series(cf["facts"], REVENUE_KEYS)
    rev_annual = _annual(rev_all)
    _, ni_annual_raw = _series(cf["facts"], ["NetIncomeLoss"])
    ni_annual = _annual(ni_annual_raw)
    _, eps_all = _series(cf["facts"], ["EarningsPerShareDiluted"], unit="USD/shares")
    eps_annual = _annual(eps_all)
    growth = None
    if len(eps_annual) >= 5 and eps_annual[-5]["value"] not in (0, None) and eps_annual[-5]["value"] > 0:
        growth = round((((eps_annual[-1]["value"] / eps_annual[-5]["value"]) ** (1 / 4)) - 1) * 100, 2)
    return 200, {
        "symbol": symbol, "companyName": cf["companyName"],
        "source": "SEC EDGAR filings (public domain)",
        "fundamentals": {
            "annualTotalRevenues": {"tag": rev_key, "periods": len(rev_annual), "series": rev_annual},
            "totalRevenueAllPeriods": {"periods": len(rev_all)},
            "netIncomeAnnual": {"periods": len(ni_annual), "series": ni_annual},
            "epsDilutedAnnual": {"periods": len(eps_annual), "series": eps_annual},
            "pegRatio": {"value": None,
                         "reason": "PEG needs an analyst growth estimate plus a live price. EDGAR provides actuals only, and quotes require a licensed feed. We publish earningsGrowth instead of a silent null.",
                         "earningsGrowth5yrPct": growth},
        },
    }


def timeseries(params):
    symbol = params.get("symbol", "").upper()
    typ = params.get("type", "annualTotalRevenues")
    if not symbol:
        return 422, {"error": "missing_parameter", "detail": "Provide symbol=, for example symbol=TSLA."}
    cf = company_facts(symbol)
    if cf is None:
        return 404, {"error": "unknown_symbol", "detail": f"{symbol} is not in the SEC EDGAR ticker map."}
    if typ == "annualTotalRevenues":
        key, all_periods = _series(cf["facts"], REVENUE_KEYS)
        series = _annual(all_periods)
    elif typ == "trailingNetIncome":
        key, series = _series(cf["facts"], ["NetIncomeLoss"])
    elif typ == "trailingEpsDiluted":
        key, series = _series(cf["facts"], ["EarningsPerShareDiluted"], unit="USD/shares")
    else:
        return 422, {"error": "unsupported_type",
                     "detail": f"type={typ} is not supported in v1. Supported: annualTotalRevenues, trailingNetIncome, trailingEpsDiluted. The full EDGAR tag set is on the roadmap; tell us which tag you need and we will add it."}
    return 200, {"symbol": symbol, "type": typ, "sourceTag": key,
                 "periods": len(series), "note": "Every reported period, no 5-series cap.",
                 "series": series, "source": "SEC EDGAR filings (public domain)"}


def submissions(symbol):
    symbol = symbol.upper()
    cached, stale = cache_get(f"edgar:sub:{symbol}")
    if cached and not stale:
        return cached
    info = ticker_map().get(symbol)
    if not info:
        return None
    cik = str(info["cik_str"]).zfill(10)
    data = fetch_json(f"https://data.sec.gov/submissions/CIK{cik}.json", UA)
    cache_set(f"edgar:sub:{symbol}", data, 86400)
    return data


def summary(params):
    symbol = params.get("symbol", "").upper()
    if not symbol:
        return 422, {"error": "missing_parameter", "detail": "Provide symbol=, for example symbol=AAPL."}
    sub = submissions(symbol)
    if sub is None:
        return 404, {"error": "unknown_symbol", "detail": f"{symbol} is not in the SEC EDGAR ticker map."}
    addr = (sub.get("addresses") or {}).get("business") or {}
    return 200, {
        "symbol": symbol, "companyName": sub.get("name"),
        "tickers": sub.get("tickers"), "exchanges": sub.get("exchanges"),
        "sic": sub.get("sic"), "sicDescription": sub.get("sicDescription"),
        "category": sub.get("category"), "fiscalYearEnd": sub.get("fiscalYearEnd"),
        "stateOfIncorporation": sub.get("stateOfIncorporation"),
        "headquarters": {"city": addr.get("city"), "stateOrCountry": addr.get("stateOrCountry")},
        "source": "SEC EDGAR filings (public domain)",
        "note": "Company name and exchange are served from filings data, the fields users reported missing on the incumbent.",
    }


def recommendations(params):
    """Related tickers: industry peers sharing the company's SEC SIC code,
    resolved back to tickers through the EDGAR map. Explicit method label:
    this is a peer proxy, not a popularity feed."""
    import xml.etree.ElementTree as ET
    symbol = params.get("symbol", "").upper()
    if not symbol:
        return 422, {"error": "missing_parameter", "detail": "Provide symbol=, for example symbol=AAPL."}
    sub = submissions(symbol)
    if sub is None:
        return 404, {"error": "unknown_symbol", "detail": f"{symbol} is not in the SEC EDGAR ticker map."}
    sic = sub.get("sic")
    if not sic:
        return 200, {"symbol": symbol, "relatedTickers": [],
                     "note": "No SIC industry code on file for this filer, so no peer list is published rather than a guessed one."}
    url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC={sic}"
           f"&dateb=&owner=include&count=100&output=atom")
    import urllib.request as _u
    req = _u.Request(url, headers=UA)
    with _u.urlopen(req, timeout=25) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    by_cik = {str(v["cik_str"]): (k, v["title"]) for k, v in ticker_map().items()}
    peers = []
    seen = set()
    for entry in root.findall("atom:entry", ns):
        id_el = entry.find("atom:id", ns)
        cik = None
        if id_el is not None and id_el.text and "cik=" in id_el.text:
            try:
                cik = str(int(id_el.text.split("cik=")[1]))
            except Exception:
                cik = None
        hit = by_cik.get(cik) if cik else None
        if hit and hit[0] != symbol and hit[0] not in seen:
            seen.add(hit[0])
            peers.append({"symbol": hit[0], "companyName": hit[1]})
        if len(peers) >= 10:
            break
    return 200, {"symbol": symbol, "method": "industry peers by SEC SIC classification",
                 "sic": sic, "sicDescription": sub.get("sicDescription"),
                 "relatedTickers": peers, "source": "SEC EDGAR (public domain)"}


def health(params):
    return 200, {"status": "ok", "service": "fundamentals-edgar",
                 "coverage": "US-listed SEC filers, financials back to about 2009 depending on the filer's XBRL history",
                 "quotes": "Not in v1: pending a licensed feed whose terms allow redistribution."}


if __name__ == "__main__":
    run({"/stock/get-fundamentals": fundamentals, "/stock/v2/get-timeseries": timeseries,
         "/stock/v2/get-summary": summary, "/stock/v2/get-recommendations": recommendations,
         "/health": health},
        int(os.environ.get("PORT", "8103")), "fundamentals-edgar")
