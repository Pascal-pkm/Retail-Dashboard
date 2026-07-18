"""Radverkehr-Dauerzaehlstellen (Fahrrad) als bundesweiter Naeherungswert fuer
Innenstadt-/Wegefrequenzen.

WICHTIG: Das sind Fahrrad-, KEINE Fussgaenger-Zaehlungen. Nutzerentscheidung
2026-07: als Tendenz-Proxy fuer eine deutschlandweite Frequenz-Karte
akzeptiert, nachdem hystreet (Standort-Fussgaengerdaten) pausiert wurde und
Destatis' eigene Passantenfrequenz-Erhebung zum 31.12.2025 eingestellt wurde.

Deckt 5 einzeln verifizierte, frei zugaengliche Regionen ab (config.json ->
radverkehr.regions). Jede Region hat eine eigene _fetch_<region>()-Funktion,
weil Format/API pro Bundesland/Stadt komplett unterschiedlich sind. Weitere
Regionen lassen sich spaeter ergaenzen, ohne die bestehenden anzufassen.

Zwei Arten von Output in data.json:
  1. data["series"]["radverkehr_region_<region>"] - EINE Tagessumme-Serie pro
     Region (scope="region", frequency="daily"/"weekly"), landet im normalen
     Frequenz-Grid + in der automatischen Kommentierung wie jede andere Serie.
  2. data["radverkehr_stations"][...] - Einzelstandorte mit lat/lon fuer die
     Kartenansicht (Task 11). Wird NICHT im normalen Card-Grid gerendert
     (sonst wuerden 150+ Karten die Seite sprengen); History pro Standort ist
     bewusst kurz gehalten (STATION_MAX_POINTS), um data.json klein zu halten -
     die lange Historie steckt in der Region-Summenserie.
"""
import csv
import io
import math
import re
from datetime import date, datetime, timedelta

from common import add_point, http_get, upsert_series

SOURCE_MODULE = "radverkehr"
STATION_MAX_POINTS = 120  # ~4 Monate taegliche Werte pro Standort (Kartenansicht braucht keine Jahre)
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

MUC_REFERER = {"Referer": "https://opendata.muenchen.de/", "Accept": "application/json"}


# ---------------------------------------------------------------- Helfer ---

def _add_station_point(station, date_str, value, max_points=STATION_MAX_POINTS):
    if value is None:
        return
    pts = {p[0]: p[1] for p in station["points"]}
    pts[str(date_str)] = round(float(value), 2)
    station["points"] = sorted([[k, v] for k, v in pts.items()])[-max_points:]


def _station(stations, key, *, name, lat, lon, bundesland, region, source, source_url, unit="Fahrräder/Tag"):
    st = stations.setdefault(key, {"points": []})
    st.update({
        "name": name, "lat": lat, "lon": lon, "bundesland": bundesland,
        "region": region, "source": source, "source_url": source_url, "unit": unit,
    })
    return st


def _utm_to_wgs84(easting, northing, zone):
    """Self-contained ETRS89/UTM (Zone N) -> WGS84 lat/lon, kein pyproj noetig."""
    a = 6378137.0
    f = 1 / 298.257223563
    k0 = 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x = easting - 500000.0
    y = northing
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = ep2 * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720
    )
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6
           + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(phi1)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    lon = lon0 + lon
    return round(math.degrees(lat), 6), round(math.degrees(lon), 6)


def _parse_csv(text):
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def _fetch_csv_rows(url, **kwargs):
    """GET + CSV-Parse mit erzwungenem utf-8-sig-Decoding: einige Portale (z.B.
    opendata.muenchen.de) senden Content-Type ohne charset, wodurch requests
    per HTTP-Default auf ISO-8859-1 zurueckfaellt und ein UTF-8-BOM als
    Mojibake ("ï»¿") in den ersten Spaltennamen landet."""
    r = http_get(url, **kwargs)
    return _parse_csv(r.content.decode("utf-8-sig"))


def _region_daily_sums(fresh_points_by_station):
    """fresh_points_by_station: {station_key: [(date_str, value), ...]} -> {date_str: sum}"""
    sums = {}
    for pts in fresh_points_by_station.values():
        for d, v in pts:
            sums[d] = sums.get(d, 0) + v
    return sums


def _push_region_series(data, region_key, region_cfg, sums, frequency="daily"):
    if not sums:
        return 0
    s = upsert_series(
        data, f"radverkehr_region_{region_key}",
        label=f"Radverkehr-Index {region_cfg['name']} (Tagessumme aller Zählstellen)",
        frequency=frequency, unit="Fahrräder/Tag (Summe)", scope="region",
        source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
    )
    for d, v in sums.items():
        add_point(s, d, v, frequency)
    return len(sums)


# ------------------------------------------------------------ BW-Region ---

def _fetch_bw(data, stations, region_cfg, errors):
    rows = _fetch_csv_rows(region_cfg["csv_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
    fresh = {}
    for row in rows:
        sid = row.get("counter_site_id")
        val = row.get("channels_all")
        ts = (row.get("iso_timestamp") or "")[:10]
        if not sid or not ts or val in (None, "", "na"):
            continue
        try:
            val = float(val)
        except ValueError:
            continue
        key = f"bw_{sid}"
        st = _station(
            stations, key,
            name=f"{row.get('domain_name', '').strip()} – {row.get('counter_site', sid)}".strip(" –"),
            lat=float(row["latitude"]) if row.get("latitude") else None,
            lon=float(row["longitude"]) if row.get("longitude") else None,
            bundesland=region_cfg["bundesland"], region="bw",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        _add_station_point(st, ts, val)
        fresh.setdefault(key, []).append((ts, val))
    return fresh


# ------------------------------------------------------------ Hamburg -----

def _fetch_hamburg(data, stations, region_cfg, errors):
    j = http_get(region_cfg["items_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES).json()
    fresh_daily, fresh_weekly = {}, {}
    for feat in j.get("features", []):
        props = feat.get("properties", {})
        coords = (feat.get("geometry") or {}).get("coordinates", [None, None])
        key = f"hamburg_{feat.get('id')}"
        st = _station(
            stations, key, name=f"Hamburg – {props.get('name', feat.get('id'))}",
            lat=coords[1], lon=coords[0],
            bundesland=region_cfg["bundesland"], region="hamburg",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        # "wochenlinie" ist trotz des Namens eine taegliche Reihe der letzten 7 Tage:
        # "KW,DD.MM.YYYY,Wert|KW,DD.MM.YYYY,Wert|..."
        pts = []
        for chunk in (props.get("wochenlinie") or "").split("|"):
            parts = chunk.split(",")
            if len(parts) != 3:
                continue
            _kw, dmy, val = parts
            try:
                d_iso = datetime.strptime(dmy.strip(), "%d.%m.%Y").date().isoformat()
                v = float(val)
            except ValueError:
                continue
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh_daily[key] = pts

        # "jahrgangslinie" liefert echte Wochensummen des laufenden Jahres: "JJJJ,KW,Wert|..."
        wk_pts = []
        for chunk in (props.get("jahrgangslinie") or "").split("|"):
            parts = chunk.split(",")
            if len(parts) != 3:
                continue
            yr, kw, val = parts
            try:
                d_iso = date.fromisocalendar(int(yr), int(kw), 1).isoformat()  # Montag der ISO-Woche
                v = float(val)
            except (ValueError, TypeError):
                continue
            wk_pts.append((d_iso, v))
        fresh_weekly[key] = wk_pts
    return fresh_daily, fresh_weekly


# ------------------------------------------------------------- Leipzig ----

def _fetch_leipzig(data, stations, region_cfg, errors):
    loc_rows = _fetch_csv_rows(region_cfg["locations_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
    locs = {}
    for row in loc_rows:
        sid = row.get("stationid")
        geom = row.get("geom", "")
        if not sid or "POINT" not in geom:
            continue
        try:
            x, y = geom.replace("POINT (", "").replace(")", "").split()
            lat, lon = _utm_to_wgs84(float(x), float(y), region_cfg.get("utm_zone", 33))
        except (ValueError, IndexError):
            lat = lon = None
        locs[sid] = {"name": row.get("stationname", sid), "lat": lat, "lon": lon}

    cutoff = (date.today() - timedelta(days=STATION_MAX_POINTS)).isoformat()
    data_rows = _fetch_csv_rows(region_cfg["data_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
    fresh = {}
    for row in data_rows:
        sid = row.get("stationid")
        ts = row.get("phenomenontime")
        val = row.get("count")
        if not sid or not ts or ts < cutoff or val in (None, ""):
            continue
        try:
            val = float(val)
        except ValueError:
            continue
        loc = locs.get(sid, {"name": sid, "lat": None, "lon": None})
        key = f"leipzig_{sid}"
        st = _station(
            stations, key, name=f"Leipzig – {loc['name']}",
            lat=loc["lat"], lon=loc["lon"],
            bundesland=region_cfg["bundesland"], region="leipzig",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        _add_station_point(st, ts, val)
        fresh.setdefault(key, []).append((ts, val))
    return fresh


# ------------------------------------------------------------ München -----

_MUC_MONTH_RE = re.compile(r"rad_(\d{4})_(\d{2})_tage\.csv$")


def _muc_month_resources(region_cfg, errors):
    """Ressourcen-URLs der Tageswerte-CSVs fuer den aktuellen + vorherigen Monat
    ueber die CKAN-API ermitteln (Dateinamen sind nicht vorhersagbar, da jede
    Ressource eine eigene UUID hat; die UUID im Pfad darf NICHT zum Sortieren
    verwendet werden, deshalb wird Jahr/Monat aus dem Dateinamen geparst)."""
    today = date.today()
    prev_month = today.replace(day=1) - timedelta(days=1)
    wanted = {(today.year, today.month), (prev_month.year, prev_month.month)}
    years = {y for y, _m in wanted}
    urls = []
    for year in years:
        try:
            r = http_get(
                region_cfg["ckan_api"], params={"id": f"daten-der-raddauerzaehlstellen-muenchen-{year}"},
                headers=MUC_REFERER, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES,
            )
            res = r.json()["result"]
            pkg = res[0] if isinstance(res, list) else res
            for resource in pkg.get("resources", []):
                url = resource.get("url", "")
                m = _MUC_MONTH_RE.search(url)
                if m and (int(m.group(1)), int(m.group(2))) in wanted:
                    urls.append(url)
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"muenchen: Ressourcenliste {year} - {e}"))
    return urls


def _fetch_muenchen(data, stations, region_cfg, errors):
    loc_rows = _fetch_csv_rows(region_cfg["locations_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
    locs = {}
    for row in loc_rows:
        code = row.get("zaehlstelle")
        if not code:
            continue
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (ValueError, KeyError):
            lat = lon = None
        locs[code] = {"name": row.get("zaehlstelle_lang", code), "lat": lat, "lon": lon}

    fresh = {}
    for url in _muc_month_resources(region_cfg, errors):
        try:
            rows = _fetch_csv_rows(url, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"muenchen: {url} - {e}"))
            continue
        for row in rows:
            code = row.get("zaehlstelle")
            datum = row.get("datum")
            gesamt = row.get("gesamt")
            if not code or not datum or gesamt in (None, ""):
                continue
            try:
                d_iso = datetime.strptime(datum.strip(), "%Y.%m.%d").date().isoformat()
                val = float(gesamt)
            except ValueError:
                continue
            loc = locs.get(code, {"name": code, "lat": None, "lon": None})
            key = f"muenchen_{code}"
            st = _station(
                stations, key, name=f"München – {loc['name']}",
                lat=loc["lat"], lon=loc["lon"],
                bundesland=region_cfg["bundesland"], region="muenchen",
                source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
            )
            _add_station_point(st, d_iso, val)
            fresh.setdefault(key, []).append((d_iso, val))
    return fresh


# ------------------------------------------------------- NRW / Münster ----

def _fetch_nrw_muenster(data, stations, region_cfg, errors):
    locs = {}
    try:
        geo = http_get(region_cfg["locations_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES).json()
        for feat in geo.get("features", []):
            props = feat.get("properties", {})
            coords = (feat.get("geometry") or {}).get("coordinates", [None, None])
            locs[str(props.get("id"))] = {"name": props.get("name"), "lat": coords[1], "lon": coords[0]}
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"nrw_muenster: Standorte - {e}"))

    site_index = http_get(region_cfg["site_index_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES).json()

    today = date.today()
    months = sorted({(today.year, today.month), (today.replace(day=1) - timedelta(days=1)).timetuple()[:2]})

    fresh = {}
    for entry in site_index:
        directory = entry.get("directory")
        name = entry.get("name", directory)
        if not directory:
            continue
        loc = locs.get(directory, {"name": name, "lat": None, "lon": None})
        key = f"nrw_muenster_{directory}"
        st = _station(
            stations, key, name=f"Münster – {loc['name'] or name}",
            lat=loc["lat"], lon=loc["lon"],
            bundesland=region_cfg["bundesland"], region="nrw_muenster",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        daily_totals = {}
        for year, month in months:
            url = f"{region_cfg['csv_base']}/{directory}/{year:04d}-{month:02d}.csv"
            try:
                r = http_get(url, timeout=REQUEST_TIMEOUT, retries=1)
            except Exception:  # noqa: BLE001
                continue  # Monat existiert evtl. noch nicht / Zaehlstelle juenger
            rows = _parse_csv(r.text)
            if not rows:
                continue
            total_col = next((c for c in rows[0].keys() if c.strip().startswith(directory)), None)
            if not total_col:
                continue
            for row in rows:
                dt_raw = row.get("Datetime", "")
                d_iso = dt_raw[:10]
                val = row.get(total_col)
                if not d_iso or val in (None, ""):
                    continue
                try:
                    val = float(val)
                except ValueError:
                    continue
                daily_totals[d_iso] = daily_totals.get(d_iso, 0) + val
        for d_iso, val in daily_totals.items():
            _add_station_point(st, d_iso, val)
        fresh[key] = list(daily_totals.items())
    return fresh


# --------------------------------------------------------------- Main -----

REGION_FETCHERS = {
    "bw": _fetch_bw,
    "leipzig": _fetch_leipzig,
    "muenchen": _fetch_muenchen,
    "nrw_muenster": _fetch_nrw_muenster,
}


def fetch(data, config, errors):
    cfg = config.get("radverkehr", {})
    regions = cfg.get("regions", {})
    if not regions:
        print("radverkehr: keine Regionen konfiguriert - uebersprungen")
        return

    stations = data.setdefault("radverkehr_stations", {})
    n_regions_ok = 0

    for region_key, region_cfg in regions.items():
        try:
            if region_key == "hamburg":
                fresh_daily, fresh_weekly = _fetch_hamburg(data, stations, region_cfg, errors)
                n_d = _push_region_series(data, region_key, region_cfg, _region_daily_sums(fresh_daily), "daily")
                n_w = _push_region_series(data, region_key, region_cfg, _region_daily_sums(fresh_weekly), "weekly")
                print(f"radverkehr[{region_key}]: {n_d} Tageswerte, {n_w} Wochenwerte", flush=True)
            else:
                fetcher = REGION_FETCHERS.get(region_key)
                if not fetcher:
                    errors.append((SOURCE_MODULE, f"{region_key}: keine Fetch-Funktion implementiert"))
                    continue
                fresh = fetcher(data, stations, region_cfg, errors)
                sums = _region_daily_sums(fresh)
                n = _push_region_series(data, region_key, region_cfg, sums, "daily")
                print(f"radverkehr[{region_key}]: {len(fresh)} Zählstellen, {n} Tages-Summenpunkte", flush=True)
            n_regions_ok += 1
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"{region_key}: {e}"))
            print(f"radverkehr[{region_key}]: FEHLER - {e}", flush=True)

    print(f"radverkehr: fertig - {n_regions_ok}/{len(regions)} Regionen ok, "
          f"{len(stations)} Zählstellen insgesamt gespeichert", flush=True)
