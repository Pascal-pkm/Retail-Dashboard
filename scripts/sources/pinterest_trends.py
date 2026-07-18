"""Pinterest Trends (Best-Effort, EXPERIMENTELL).

Es gibt keine oeffentliche Pinterest-Trends-API. Dieses Modul versucht den
internen Endpunkt von trends.pinterest.com anzuzapfen. Das kann jederzeit
brechen (dann nur Eintrag im Fehlerprotokoll, kein Abbruch des Laufs).
"""
from datetime import date

from common import add_point, http_get, upsert_series

SOURCE = "Pinterest Trends (inoffiziell, experimentell)"
BASE = "https://trends.pinterest.com"


def _try_endpoints(term, region):
    candidates = [
        (f"{BASE}/api/v1/trends/keyword/timeseries/",
         {"keyword": term, "country": region}),
        (f"{BASE}/api/v1/keyword/timeseries/",
         {"keyword": term, "country": region}),
    ]
    headers = {"Accept": "application/json", "Referer": f"{BASE}/"}
    last = None
    for url, params in candidates:
        try:
            r = http_get(url, params=params, headers=headers, retries=1)
            if "json" in r.headers.get("Content-Type", ""):
                return r.json()
            last = RuntimeError(f"kein JSON von {url}")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last or RuntimeError("kein Endpunkt erreichbar")


def _extract_points(j):
    """Zeitreihe aus unbekannter JSON-Struktur ziehen (tolerant)."""
    def walk(o):
        if isinstance(o, dict):
            for k in ("timeseries", "data", "counts", "normalizedCount"):
                if k in o:
                    yield o[k]
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    for cand in walk(j):
        if isinstance(cand, list) and cand and isinstance(cand[0], (list, dict)):
            pts = []
            for item in cand:
                if isinstance(item, dict):
                    d = item.get("date") or item.get("week") or item.get("x")
                    v = item.get("count") or item.get("value") or item.get("y")
                elif len(item) >= 2:
                    d, v = item[0], item[1]
                else:
                    continue
                if d and v is not None:
                    pts.append((str(d)[:10], v))
            if len(pts) >= 3:
                return pts
    return []


def fetch(data, config, errors):
    cfg = config.get("pinterest_trends", {})
    if not cfg.get("enabled"):
        print("pinterest_trends: deaktiviert - uebersprungen")
        return
    region = cfg.get("region", "DE")
    for term in cfg.get("terms", []):
        try:
            j = _try_endpoints(term, region)
            pts = _extract_points(j)
            if not pts:
                raise RuntimeError("Antwort ohne erkennbare Zeitreihe")
            sid = "pinterest_" + "".join(c if c.isalnum() else "_" for c in term.lower())
            s = upsert_series(
                data, sid,
                label=f"Pinterest-Suchtrend „{term}“ ({region})", frequency="weekly",
                unit="Index (normalisiert)", scope="branche",
                source=SOURCE, source_url="https://trends.pinterest.com",
            )
            for d, v in pts[-60:]:
                add_point(s, d, float(v), "weekly")
        except Exception as e:  # noqa: BLE001
            errors.append(("pinterest_trends", f"„{term}“: {e}"))
