"""Eurostat: Einzelhandelsumsaetze (sts_trtu_m), u.a. NACE G47.7 Textilien/Bekleidung/Schuhe.

Kostenlose REST-API (JSON-stat 2.0), Weiterverwendung mit Quellenangabe gestattet.
"""
from common import add_point, http_get_json, upsert_series

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}"
SOURCE = "Eurostat, Dataset sts_trtu_m"

NACE_LABELS = {
    "G47": "Einzelhandel gesamt",
    "G4771": "EH mit Bekleidung",
    "G4772": "EH mit Schuhen/Lederwaren",
    "G477": "EH Textilien/Bekleidung/Schuhe (G47.7)",
}
GEO_LABELS = {"DE": "Deutschland", "EU27_2020": "EU-27"}


def _jsonstat_points(j):
    """JSON-stat 2.0 -> Liste ((dim_kombination), wert). Liefert dims + values."""
    dims = j["id"]
    sizes = j["size"]
    cat_index = {}
    for d in dims:
        idx = j["dimension"][d]["category"]["index"]
        if isinstance(idx, list):
            idx = {k: i for i, k in enumerate(idx)}
        cat_index[d] = {v: k for k, v in idx.items()}  # position -> code
    values = j.get("value", {})
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values)}
    for flat, val in values.items():
        if val is None:
            continue
        pos = int(flat)
        combo = {}
        for d, size in zip(reversed(dims), reversed(sizes)):
            combo[d] = cat_index[d][pos % size]
            pos //= size
        yield combo, val


def fetch(data, config, errors):
    cfg = config.get("eurostat", {})
    ds = cfg.get("dataset", "sts_trtu_m")
    geos = cfg.get("geo", ["DE"])
    for nace in cfg.get("nace_codes", ["G47"]):
        try:
            params = [
                ("format", "JSON"), ("lang", "de"),
                ("nace_r2", nace), ("s_adj", "SCA"), ("unit", "I21"),
                ("indic_bt", "VOL_SLS"), ("sinceTimePeriod", "2019-01"),
            ] + [("geo", g) for g in geos]
            j = http_get_json(API.format(ds=ds), params=params)
            n = 0
            for combo, val in _jsonstat_points(j):
                geo = combo.get("geo", "?")
                t = combo.get("time", "")
                if len(t) == 7 and "-" in t:  # 2025-05
                    dstr = t + "-01"
                elif "M" in t:  # 2025M05
                    dstr = t.replace("M", "-") + "-01"
                else:
                    continue
                sid = f"eurostat_{nace.lower()}_{geo.lower()}"
                s = upsert_series(
                    data, sid,
                    label=f"Umsatzvolumen {NACE_LABELS.get(nace, nace)} – {GEO_LABELS.get(geo, geo)}",
                    frequency="monthly", unit="Index (2021=100), saisonbereinigt",
                    scope="branche", source=SOURCE,
                    source_url=f"https://ec.europa.eu/eurostat/databrowser/view/{ds}/default/table",
                )
                add_point(s, dstr, val, "monthly")
                n += 1
            if n == 0:
                raise RuntimeError("keine Werte in Antwort")
        except Exception as e:  # noqa: BLE001
            errors.append(("eurostat", f"{nace}: {e}"))
