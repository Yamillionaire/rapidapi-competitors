"""GeoBase Cities - competitor to GeoDB Cities (wirefreethought) on RapidAPI.

Incumbent verified 2026-10-28: 50,222 subscribers, rated 3/5 (60 votes),
pricing $0/$20/$40/$80 with per-day quotas. Complaints in its Discussions:
recurring outages; cities wrong, missing or deleted (Rome deleted, Surrey BC
missing, Cluj-Napoca deleted, Sao Paulo findable only by ID, Sevastopol
placed in Buryatia); provider silence.
This service: same public upstream (GeoNames, CC BY 4.0) served on the
scaffold behind our other three APIs, with the complained-about places in
the launch test set and correct in the shipped snapshot.
Dataset v1: GeoNames cities15000 - 34,191 populated places (population
15,000+ or capitals) + admin1 regions + country info. Places under 15,000
population are the documented v2 expansion (cities500).
Zero dependencies beyond the shared scaffold. Run: python3 app.py (PORT env, default 8104).
"""
import bisect
import io
import math
import os
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from rapidapi_server import run

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
GEONAMES = "https://download.geonames.org/export/dump/"
SNAPSHOT = "boot"  # replaced by the dataset's own vintage after load


def ensure_data():
    """Load from local files when present; otherwise pull the GeoNames dump.

    The cities file is 8.5MB of text, too large for the repo snapshot route,
    so the service fetches it at boot (same pattern as CleanList's list).
    """
    wanted = ["cities15000.txt", "admin1CodesASCII.txt", "countryInfo.txt", "timeZones.txt"]
    if all(os.path.exists(os.path.join(DATA_DIR, f)) for f in wanted):
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(GEONAMES + "cities15000.zip", timeout=60) as resp:
                blob = resp.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                data = zf.read("cities15000.txt")
            with open(os.path.join(DATA_DIR, "cities15000.txt"), "wb") as fh:
                fh.write(data)
            for name in wanted[1:]:
                with urllib.request.urlopen(GEONAMES + name, timeout=60) as resp:
                    payload = resp.read()
                with open(os.path.join(DATA_DIR, name), "wb") as fh:
                    fh.write(payload)
            return
        except Exception as exc:  # retry a few times, then fail loudly at boot
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"GeoNames download failed: {last_error}")


ensure_data()

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


def fold(text):
    """Diacritic-insensitive lowercase fold: 'São Paulo' -> 'sao paulo'."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().strip()


# ---------------------------------------------------------------- load data
COUNTRIES = {}   # code -> dict
REGIONS = {}     # (country_code, admin1) -> dict
REGIONS_BY_COUNTRY = {}
CITIES = []      # list of dicts
CITY_BY_ID = {}
TZ_FALLBACK = {}  # tz name -> gmt offset hours (standard time)

with open(os.path.join(DATA_DIR, "countryInfo.txt"), encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            continue
        f = line.rstrip("\n").split("\t")
        if len(f) < 11 or not f[0]:
            continue
        COUNTRIES[f[0]] = {"code": f[0], "name": f[4], "capital": f[5],
                           "currencyCodes": [f[10]] if f[10] else [],
                           "continent": f[8], "population": int(f[7] or 0)}

with open(os.path.join(DATA_DIR, "admin1CodesASCII.txt"), encoding="utf-8") as fh:
    for line in fh:
        f = line.rstrip("\n").split("\t")
        if len(f) < 2 or "." not in f[0]:
            continue
        cc, adm1 = f[0].split(".", 1)
        region = {"code": adm1, "name": f[1], "countryCode": cc}
        REGIONS[(cc, adm1)] = region
        REGIONS_BY_COUNTRY.setdefault(cc, []).append(region)

with open(os.path.join(DATA_DIR, "timeZones.txt"), encoding="utf-8") as fh:
    header = fh.readline()
    for line in fh:
        f = line.rstrip("\n").split("\t")
        if len(f) >= 4:
            try:
                TZ_FALLBACK[f[1]] = float(f[2])
            except ValueError:
                pass

_vintage = ""
with open(os.path.join(DATA_DIR, "cities15000.txt"), encoding="utf-8") as fh:
    for line in fh:
        f = line.rstrip("\n").split("\t")
        if len(f) < 18:
            continue
        if len(f) > 18 and f[18] > _vintage:
            _vintage = f[18]
        cc = f[8]
        region = REGIONS.get((cc, f[10]), {})
        city = {"id": int(f[0]), "type": "CITY", "name": f[1], "asciiName": f[2],
                "country": COUNTRIES.get(cc, {}).get("name", cc), "countryCode": cc,
                "region": region.get("name", ""), "regionCode": f[10],
                "latitude": float(f[4]), "longitude": float(f[5]),
                "population": int(f[14] or 0), "timezone": f[17],
                "featureCode": f[7], "_alternates": f[3]}
        CITIES.append(city)
        CITY_BY_ID[city["id"]] = city
SNAPSHOT = _vintage or SNAPSHOT

for region_list in REGIONS_BY_COUNTRY.values():
    region_list.sort(key=lambda r: r["name"])

CITY_COUNT_BY_COUNTRY = {}
CITY_COUNT_BY_REGION = {}
for c in CITIES:
    CITY_COUNT_BY_COUNTRY[c["countryCode"]] = CITY_COUNT_BY_COUNTRY.get(c["countryCode"], 0) + 1
    key = (c["countryCode"], c["regionCode"])
    CITY_COUNT_BY_REGION[key] = CITY_COUNT_BY_REGION.get(key, 0) + 1

# prefix index over folded name + ascii name + alternate names
_name_index = []
for c in CITIES:
    variants = {fold(c["name"]), fold(c["asciiName"])}
    for alt in c["_alternates"].split(",")[:6]:
        if alt:
            variants.add(fold(alt))
    for v in variants:
        if v:
            _name_index.append((v, c["id"]))
_name_index.sort()
_index_keys = [k for k, _ in _name_index]


def prefix_ids(prefix):
    folded = fold(prefix)
    lo = bisect.bisect_left(_index_keys, folded)
    hi = bisect.bisect_left(_index_keys, folded[:-1] + chr(ord(folded[-1]) + 1)) if folded else len(_index_keys)
    return {_name_index[i][1] for i in range(lo, hi)}


# ---------------------------------------------------------------- shapes
def city_out(c):
    return {"id": c["id"], "type": "CITY", "name": c["name"], "country": c["country"],
            "countryCode": c["countryCode"], "region": c["region"],
            "regionCode": c["regionCode"], "latitude": c["latitude"],
            "longitude": c["longitude"], "population": c["population"],
            "timezone": c["timezone"],
            "source": "GeoNames (CC BY 4.0), snapshot " + SNAPSHOT}


def country_out(code):
    base = COUNTRIES[code]
    return {"code": base["code"], "name": base["name"], "capital": base["capital"],
            "currencyCodes": base["currencyCodes"], "continent": base["continent"],
            "population": base["population"],
            "numCities": CITY_COUNT_BY_COUNTRY.get(code, 0)}


def region_out(region):
    return {"code": region["code"], "name": region["name"],
            "countryCode": region["countryCode"],
            "numCities": CITY_COUNT_BY_REGION.get((region["countryCode"], region["code"]), 0)}


def paginate(items, params, shape):
    try:
        limit = min(max(int(params.get("limit", "10")), 1), 100)
        offset = max(int(params.get("offset", "0")), 0)
    except ValueError:
        return 422, {"error": "invalid_parameter", "detail": "limit and offset must be integers."}
    page = items[offset:offset + limit]
    return 200, {"data": [shape(x) for x in page],
                 "metadata": {"currentOffset": offset, "totalCount": len(items)}}


def sort_cities(items, params):
    sort = params.get("sort", "-population")
    if sort == "name":
        return sorted(items, key=lambda c: c["name"].lower())
    if sort == "-name":
        return sorted(items, key=lambda c: c["name"].lower(), reverse=True)
    if sort == "population":
        return sorted(items, key=lambda c: c["population"])
    if sort == "countryCode":
        return sorted(items, key=lambda c: (c["countryCode"], c["name"].lower()))
    return sorted(items, key=lambda c: c["population"], reverse=True)


def filter_cities(params, base=None):
    items = list(CITIES if base is None else base)
    if params.get("namePrefix"):
        ids = prefix_ids(params["namePrefix"])
        items = [c for c in items if c["id"] in ids]
    if params.get("countryIds"):
        wanted = {x.strip().upper() for x in params["countryIds"].split(",") if x.strip()}
        items = [c for c in items if c["countryCode"] in wanted]
    if params.get("minPopulation"):
        try:
            floor = int(params["minPopulation"])
        except ValueError:
            return None, (422, {"error": "invalid_parameter", "detail": "minPopulation must be an integer."})
        items = [c for c in items if c["population"] >= floor]
    return items, None


# ---------------------------------------------------------------- handlers
def list_countries(params):
    items = [COUNTRIES[k] for k in sorted(COUNTRIES)]
    if params.get("namePrefix"):
        folded = fold(params["namePrefix"])
        items = [c for c in items if fold(c["name"]).startswith(folded)]
    return paginate(items, params, lambda c: country_out(c["code"]))


def get_country(params):
    code = params["countryId"].upper()
    if code not in COUNTRIES:
        return 404, {"error": "not_found", "detail": f"No country with code {code}."}
    return 200, {"data": country_out(code)}


def list_regions(params):
    code = params["countryId"].upper()
    if code not in COUNTRIES:
        return 404, {"error": "not_found", "detail": f"No country with code {code}."}
    return paginate(REGIONS_BY_COUNTRY.get(code, []), params, region_out)


def get_region(params):
    code = params["countryId"].upper()
    region = REGIONS.get((code, params["regionCode"]))
    if region is None:
        return 404, {"error": "not_found",
                     "detail": f"No region {params['regionCode']} in country {code}."}
    return 200, {"data": region_out(region)}


def region_cities(params):
    code = params["countryId"].upper()
    if (code, params["regionCode"]) not in REGIONS:
        return 404, {"error": "not_found",
                     "detail": f"No region {params['regionCode']} in country {code}."}
    base = [c for c in CITIES if c["countryCode"] == code and c["regionCode"] == params["regionCode"]]
    items, err = filter_cities(params, base)
    if err:
        return err
    return paginate(sort_cities(items, params), params, city_out)


def list_cities(params):
    items, err = filter_cities(params)
    if err:
        return err
    return paginate(sort_cities(items, params), params, city_out)


def _city_or_404(raw_id):
    try:
        city = CITY_BY_ID.get(int(raw_id))
    except (TypeError, ValueError):
        city = None
    if city is None:
        return None, (404, {"error": "not_found", "detail": f"No city with id {raw_id}."})
    return city, None


def get_city(params):
    city, err = _city_or_404(params["cityId"])
    if err:
        return err
    return 200, {"data": city_out(city)}


def _local_now(city):
    tz_name = city["timezone"]
    if ZoneInfo is not None and tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)), "zoneinfo"
        except Exception:
            pass
    offset = TZ_FALLBACK.get(tz_name, 0.0)
    from datetime import timedelta
    return datetime.now(timezone.utc) + timedelta(hours=offset), "standard-offset-fallback"


def city_datetime(params):
    city, err = _city_or_404(params["cityId"])
    if err:
        return err
    now, mode = _local_now(city)
    return 200, {"data": {"cityId": city["id"], "timezone": city["timezone"],
                          "dateTime": now.strftime("%Y-%m-%dT%H:%M:%S"),
                          "basis": mode}}


def city_time(params):
    city, err = _city_or_404(params["cityId"])
    if err:
        return err
    now, mode = _local_now(city)
    return 200, {"data": {"cityId": city["id"], "timezone": city["timezone"],
                          "time": now.strftime("%H:%M"), "basis": mode}}


def _haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a["latitude"], a["longitude"],
                                                b["latitude"], b["longitude"]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def city_distance(params):
    city, err = _city_or_404(params["cityId"])
    if err:
        return err
    other, err = _city_or_404(params.get("toCityId", ""))
    if err:
        return 422, {"error": "invalid_parameter", "detail": "Provide a valid toCityId."}
    km = _haversine_km(city, other)
    unit = params.get("distanceUnit", "KM").upper()
    value = km * 0.621371 if unit == "MI" else km
    return 200, {"data": {"fromCityId": city["id"], "toCityId": other["id"],
                          "distance": round(value, 2), "distanceUnit": unit}}


_LOC_RE = re.compile(r"^(-?\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)$")


def nearby_cities(params):
    m = _LOC_RE.match(params["location"].strip())
    if not m:
        return 422, {"error": "invalid_parameter",
                     "detail": "location must look like 41.89193+12.51133 (latitude+longitude)."}
    origin = {"latitude": float(m.group(1)), "longitude": float(m.group(2))}
    try:
        radius = float(params.get("radius", "100"))
    except ValueError:
        return 422, {"error": "invalid_parameter", "detail": "radius must be a number."}
    unit = params.get("distanceUnit", "KM").upper()
    radius_km = radius / 0.621371 if unit == "MI" else radius
    found = []
    for c in CITIES:
        d = _haversine_km(origin, c)
        if d <= radius_km:
            found.append((d, c))
    found.sort(key=lambda x: x[0])
    shaped = []
    for d, c in found:
        out = city_out(c)
        out["distance"] = round(d * 0.621371 if unit == "MI" else d, 2)
        out["distanceUnit"] = unit
        shaped.append(out)
    try:
        limit = min(max(int(params.get("limit", "10")), 1), 100)
        offset = max(int(params.get("offset", "0")), 0)
    except ValueError:
        return 422, {"error": "invalid_parameter", "detail": "limit and offset must be integers."}
    return 200, {"data": shaped[offset:offset + limit],
                 "metadata": {"currentOffset": offset, "totalCount": len(shaped)}}


def health(params):
    return 200, {"status": "ok", "service": "geobase-cities",
                 "uptime_target": "99.9%",
                 "dataset": {"places": len(CITIES), "regions": len(REGIONS),
                             "countries": len(COUNTRIES),
                             "source": "GeoNames (CC BY 4.0)", "snapshot": SNAPSHOT,
                             "coverage": "populated places with population 15,000+ and capitals; smaller places land in v2"},
                 "note": "Structured errors, always. If a place looks wrong, the correction pipeline reviews it against Wikidata."}


if __name__ == "__main__":
    run({"/v1/geo/countries": list_countries,
         "/v1/geo/countries/{countryId}": get_country,
         "/v1/geo/countries/{countryId}/regions": list_regions,
         "/v1/geo/countries/{countryId}/regions/{regionCode}": get_region,
         "/v1/geo/countries/{countryId}/regions/{regionCode}/cities": region_cities,
         "/v1/geo/cities": list_cities,
         "/v1/geo/cities/{cityId}": get_city,
         "/v1/geo/cities/{cityId}/dateTime": city_datetime,
         "/v1/geo/cities/{cityId}/time": city_time,
         "/v1/geo/cities/{cityId}/distance": city_distance,
         "/v1/geo/locations/{location}/nearbyCities": nearby_cities,
         "/health": health},
        int(os.environ.get("PORT", "8104")), "geobase-cities")
