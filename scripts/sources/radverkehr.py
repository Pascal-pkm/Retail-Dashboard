"""Radverkehr-Dauerzaehlstellen (Fahrrad) als bundesweiter Naeherungswert fuer
Innenstadt-/Wegefrequenzen.

WICHTIG: Das sind Fahrrad-, KEINE Fussgaenger-Zaehlungen. Nutzerentscheidung
2026-07: als Tendenz-Proxy fuer eine deutschlandweite Frequenz-Karte
akzeptiert, nachdem hystreet (Standort-Fussgaengerdaten) pausiert wurde und
Destatis' eigene Passantenfrequenz-Erhebung zum 31.12.2025 eingestellt wurde.

Deckt 8 einzeln verifizierte, frei zugaengliche Regionen ab (config.json ->
radverkehr.regions). Jede Region hat eine eigene _fetch_<region>()-Funktion,
weil Format/API pro Bundesland/Stadt komplett unterschiedlich sind. Weitere
Regionen lassen sich spaeter ergaenzen, ohne die bestehenden anzufassen.

NRW-Vollrecherche 2026-07 (siehe COMPLIANCE.md): von allen gepruefeten NRW-
Portalen sind nrw_muenster (bereits vorhanden), nrw_dortmund, nrw_duesseldorf
und nrw_koeln offen lizenziert und liefern tatsaechliche Messwerte (nicht nur
Standort-Metadaten). Bochum ist explizit "andere/geschlossene Lizenz" (Eco-
Counter-Klausel, keine Weiterverbreitung) und bleibt ausgeschlossen. Wuppertal,
Kreis Viersen, Rhein-Kreis-Neuss und GEOportal.NRW haben keine eigenen offen
lizenzierten Messwert-Datensaetze (nur Infrastruktur-/Planungsdaten bzw.
Standort-Metadaten ohne Zaehlwerte) und wurden daher nicht aufgenommen.

Norddeutschland/Kueste-Recherche 2026-07 (Nutzeranfrage: "Gibt es noch mehr
Frequenzen? Die Kueste ist interessant"): Rostock (Ostseekueste, u.a. Warne-
muende, Graal-Mueritz) neu aufgenommen - CC0-1.0, siehe COMPLIANCE.md. Bremen
gepueft, aber keine offizielle offene Lizenz gefunden (nur inoffiziell doku-
mentierter Scrape-Zugang) - nicht aufgenommen. Kiel/Luebeck/Flensburg/Sylt/
Wilhelmshaven/Cuxhaven/Nordfriesland: keine eigenen offenen Messwert-Daten-
saetze gefunden.

Zwei Arten von Output in data.json:
  1. data["series"]["radverkehr_region_<region>"] - EINE Summen-Serie pro
     Region (scope="region", frequency="daily"/"weekly"/"monthly" je nach
     Quellgranularitaet), landet NICHT mehr im normalen Frequenz-Grid (dort nur
     verwirrend neben Aktienkursen etc.), sondern ausschliesslich im Karte-Tab
     als Gesamt-Index (siehe docs/index.html).
  2. data["radverkehr_stations"][...] - Einzelstandorte mit lat/lon; werden im
     Karte-Tab sowohl auf der Karte als auch als eigene Liste mit Vorjahres-
     vergleich gerendert (STATION_MAX_POINTS haelt dafuer ausreichend Historie).
"""
import csv
import io
import math
import re
from datetime import date, datetime, timedelta, timezone

import requests

from common import USER_AGENT, add_point, http_get, upsert_series

SOURCE_MODULE = "radverkehr"
STATION_MAX_POINTS = 600  # ~20 Monate taegliche Werte pro Standort - genug fuer einen
# Vorjahresvergleich (Monat/Quartal ggue. Vorjahresmonat/-quartal) im Karte-Tab; vorher
# 120 (~4 Monate), das reichte fuer die Kartenansicht, aber nicht fuer einen YoY-Vergleich.
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

MUC_REFERER = {"Referer": "https://opendata.muenchen.de/", "Accept": "application/json"}

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower().translate(_UMLAUT_MAP)).strip("_")


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


_PERIOD_LABEL = {"daily": "Tagessumme", "weekly": "Wochensumme", "monthly": "Monatssumme"}
_PERIOD_UNIT = {
    "daily": "Fahrräder/Tag (Summe)", "weekly": "Fahrräder/Woche (Summe)",
    "monthly": "Fahrräder/Monat (Summe)",
}


def _push_region_series(data, region_key, region_cfg, sums, frequency="daily"):
    if not sums:
        return 0
    s = upsert_series(
        data, f"radverkehr_region_{region_key}",
        label=f"Radverkehr-Index {region_cfg['name']} "
              f"({_PERIOD_LABEL.get(frequency, 'Summe')} aller Zählstellen)",
        frequency=frequency, unit=_PERIOD_UNIT.get(frequency, "Fahrräder (Summe)"), scope="region",
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


# ------------------------------------------------------------ Dortmund ----

def _fetch_dortmund(data, stations, region_cfg, errors):
    """OpenDataSoft-API von open-data.dortmund.de (Zaehlstelle Schnettkerbruecke,
    DL-DE-Zero-2.0). Serverseitige Tagessumme per group_by=datum statt der
    15-Minuten-Rohdaten - ein einziger HTTP-Call liefert die komplette
    Historie seit 2018, kein eigenes Aufsummieren noetig."""
    params = {
        "select": "datum,sum(radfahrer) as total",
        "group_by": "datum",
        "order_by": "datum desc",
        "limit": region_cfg.get("backfill_days", 1600),
    }
    j = http_get(region_cfg["records_url"], params=params, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES).json()
    key = "dortmund_schnettkerbruecke"
    st = _station(
        stations, key, name="Dortmund – Schnettkerbrücke",
        lat=region_cfg.get("lat"), lon=region_cfg.get("lon"),
        bundesland=region_cfg["bundesland"], region="nrw_dortmund",
        source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
    )
    fresh = []
    for rec in j.get("records", []):
        f = rec.get("record", {}).get("fields", {})
        ms, total = f.get("datum"), f.get("total")
        if ms is None or total is None:
            continue
        d_iso = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
        val = float(total)
        _add_station_point(st, d_iso, val)
        fresh.append((d_iso, val))
    return {key: fresh}


# --------------------------------------------------------- Düsseldorf -----

def _duess_station_locations(region_cfg, errors):
    """WGS84-GeoJSON der Standorte; 'standort'-Namen darin sind ASCII-
    transliteriert (kleingeschrieben, ae/oe/ue/ss) und werden per
    Praefixvergleich (nach Normalisierung) auf die CSV-Stationsnamen gemappt."""
    locs = []
    try:
        geo = http_get(region_cfg["locations_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES).json()
        for feat in geo.get("features", []):
            props = feat.get("properties", {})
            coords = (feat.get("geometry") or {}).get("coordinates", [None, None])
            norm = _slugify(props.get("standort", "")).replace("_", " ")
            if norm:
                locs.append((norm, coords[1], coords[0]))
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"duesseldorf: Standorte - {e}"))
    return locs


def _duess_match_location(locs, station_name):
    norm = _slugify(station_name).replace("_", " ")
    best = None
    for loc_norm, lat, lon in locs:
        if norm.startswith(loc_norm) or loc_norm.startswith(norm):
            if best is None or len(loc_norm) > len(best[0]):
                best = (loc_norm, lat, lon)
    return (best[1], best[2]) if best else (None, None)


def _duess_year_resources(region_cfg, year, errors):
    """CSV-Ressourcen eines Jahrgangs ueber die govdata.de-CKAN-API (deren
    DCAT-Harvester spiegelt opendata.duesseldorf.de inkl. Ressourcen-URLs;
    das Duesseldorfer Portal selbst hat keine oeffentlich erreichbare
    package_show-API)."""
    package_id = f"{region_cfg['package_id_prefix']}{year}"
    try:
        r = http_get(
            region_cfg["package_show_url"], params={"id": package_id},
            timeout=REQUEST_TIMEOUT, retries=1,
        )
        pkg = r.json()["result"]
    except Exception:  # noqa: BLE001
        return []  # Jahrgang (noch) nicht veroeffentlicht
    out = []
    for res in pkg.get("resources", []):
        url = res.get("url", "")
        if not url.lower().endswith(".csv"):
            continue
        name = res.get("name", "")
        station_name = re.split(r"\s*-\s*Wetterabh", name)[0].strip() or name
        # Manche Ressourcennamen tragen das Jahr zusaetzlich VOR dem Bindestrich
        # (z.B. "... IN OUT 2025 - Wetterabhaengige Jahresuebersicht ... 2025"),
        # was doppelte Stationsschluessel je Jahrgang erzeugen wuerde.
        station_name = re.sub(r"\s+\d{4}$", "", station_name).strip()
        out.append((station_name, url))
    return out


def _fetch_duesseldorf(data, stations, region_cfg, errors):
    """Wetterabhaengige Jahresuebersicht Dauerzaehlstellen Radverkehr
    (opendata.duesseldorf.de, DL-DE-BY-2.0). Jahresarchive erscheinen erst
    Monate nach Jahresende, daher aktuelles + Vorjahr abfragen; stuendliche
    Werte (Zeit;<Station[ IN;<Station> OUT];Symbol Wetter;Temperatur;Regen)
    werden pro Tag aufsummiert."""
    locs = _duess_station_locations(region_cfg, errors)
    today = date.today()
    years = sorted({today.year, today.year - 1})
    fresh = {}
    for year in years:
        for station_name, url in _duess_year_resources(region_cfg, year, errors):
            try:
                r = http_get(url, timeout=REQUEST_TIMEOUT, retries=1)
                rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
            except Exception as e:  # noqa: BLE001
                errors.append((SOURCE_MODULE, f"duesseldorf {year} {station_name}: {e}"))
                continue
            if len(rows) < 2:
                continue
            header = rows[0]
            weather_idx = next((i for i, c in enumerate(header) if "wetter" in c.lower()), len(header))
            count_cols = list(range(1, weather_idx))
            if not count_cols:
                continue

            key = f"duesseldorf_{_slugify(station_name)}"
            lat, lon = _duess_match_location(locs, station_name)
            st = _station(
                stations, key, name=f"Düsseldorf – {station_name}",
                lat=lat, lon=lon,
                bundesland=region_cfg["bundesland"], region="nrw_duesseldorf",
                source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
            )

            daily_totals = {}
            for row in rows[1:]:
                if not row or not row[0].strip():
                    continue
                try:
                    dt = datetime.strptime(row[0].strip(), "%d-%m-%Y %H:%M:%S")
                except ValueError:
                    continue
                total, has_val = 0.0, False
                for ci in count_cols:
                    if ci >= len(row) or not row[ci].strip():
                        continue
                    try:
                        total += float(row[ci].strip())
                        has_val = True
                    except ValueError:
                        continue
                if has_val:
                    d_iso = dt.date().isoformat()
                    daily_totals[d_iso] = daily_totals.get(d_iso, 0.0) + total
            for d_iso, val in daily_totals.items():
                _add_station_point(st, d_iso, val)
            fresh.setdefault(key, []).extend(daily_totals.items())
    return fresh


# -------------------------------------------------------------- Köln ------

_KOELN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}


def _koeln_year_csv_url(region_cfg, year, errors):
    """Ressourcen-URL ueber govdata.de-CKAN-API; Dateiname/-schema wechselt
    zwischen Jahrgaengen (mal 'Radverkehr fuer Offene Daten Koeln <Jahr>.csv',
    mal 'Fahrrad_Zaehlstellen_Koeln_<Jahr>.csv'), deshalb keine URL-Vorlage."""
    try:
        r = http_get(
            region_cfg["package_show_url"], params={"id": f"{region_cfg['package_id_prefix']}{year}"},
            timeout=REQUEST_TIMEOUT, retries=1,
        )
        pkg = r.json()["result"]
    except Exception:  # noqa: BLE001
        return None  # Jahrgang nicht vorhanden (Datenstand seit 2022 nicht aktualisiert)
    for res in pkg.get("resources", []):
        url = res.get("url", "")
        if url.lower().endswith(".csv"):
            # WICHTIG: NICHT dekodieren. Die govdata.de-Ressourcen-URL enthaelt
            # "%2520" etc. (aussieht wie doppelt-urlencodiert), aber die Datei
            # auf offenedaten-koeln.de liegt tatsaechlich unter einem Dateinamen
            # mit woertlichen "%xx"-Zeichen (Drupal-Upload-Artefakt) - verifiziert
            # per Vergleichstest 2026-07: die rohe URL liefert HTTP 200, eine
            # einfach dekodierte Variante (echte Leerzeichen/Umlaute) HTTP 404.
            return url
    return None


def _fetch_koeln(data, stations, region_cfg, errors):
    """Fahrrad Verkehrsdaten Koeln (offenedaten-koeln.de, DL-DE-Zero-2.0):
    ein CSV pro Jahr mit Monatssummen je Zaehlstelle, Semikolon-getrennt,
    deutsches Tausenderpunkt-Zahlenformat. Kodierung wechselt zwischen
    Jahrgaengen (mal UTF-8, mal ISO-8859-1/CP1252) - erst UTF-8 versuchen,
    sonst faellt "ü" sonst als Mojibake ("Ã¼") an und erzeugt doppelte
    Stationsschluessel je nach Jahr."""
    fresh = {}
    current_year = date.today().year
    for year in range(region_cfg.get("first_year", 2010), current_year + 1):
        url = _koeln_year_csv_url(region_cfg, year, errors)
        if not url:
            continue
        try:
            raw = http_get(url, timeout=REQUEST_TIMEOUT, retries=1).content
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("iso-8859-1")
            rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"koeln {year}: {e}"))
            continue
        if len(rows) < 2:
            continue
        header = rows[0]
        for row in rows[1:]:
            if not row or not row[0].strip():
                continue
            month = _KOELN_MONTHS.get(row[0].strip().lower())
            if not month:
                continue
            d_iso = date(year, month, 1).isoformat()
            for ci in range(1, len(header)):
                name = header[ci].strip()
                if not name or ci >= len(row) or not row[ci].strip():
                    continue
                try:
                    val = float(row[ci].strip().replace(".", "").replace(",", "."))
                except ValueError:
                    continue
                key = f"koeln_{_slugify(name)}"
                st = _station(
                    stations, key, name=f"Köln – {name}", lat=None, lon=None,
                    bundesland=region_cfg["bundesland"], region="nrw_koeln",
                    source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
                    unit="Fahrräder/Monat",
                )
                _add_station_point(st, d_iso, val, max_points=region_cfg.get("station_max_points", 200))
                fresh.setdefault(key, []).append((d_iso, val))
    return fresh


# ------------------------------------------------------------- Rostock ----

ROSTOCK_TAIL_BYTES = 30_000_000  # ~30 MB vom Dateiende statt der kompletten,
# taeglich wachsenden Datei (Stand 07/2026: 154 MB, seit 11/2013 15-Minuten-
# Werte). Die neuesten Zeilen stehen immer ganz am Ende (taeglich angehaengte
# Bloecke je Station), 30 MB decken so weit mehr als STATION_MAX_POINTS Tage
# fuer alle 11 Stationen ab. Server unterstuetzt HTTP-Range (verifiziert
# 07/2026: "Accept-Ranges: bytes", 206 Partial Content).


def _rostock_tail_lines(url, errors):
    # Echtes HTTP HEAD (nicht GET mit Range:bytes=0-0!) fuer die Dateigroesse -
    # sonst wuerde bei einem Netzwerkpfad, der Range-Requests ignoriert (siehe
    # Fallback unten), bereits die Groessen-Abfrage die komplette 150+MB-Datei
    # unnoetig ein zweites Mal uebertragen.
    total = 0
    try:
        head = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        total = int(head.headers.get("Content-Length", 0) or 0)
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"rostock: Dateigroesse nicht ermittelbar - {e}"))

    range_start = max(0, total - ROSTOCK_TAIL_BYTES) if total > ROSTOCK_TAIL_BYTES else 0
    r = http_get(url, headers={"Range": f"bytes={range_start}-"} if range_start else None,
                 timeout=180, retries=REQUEST_RETRIES)
    content = r.content

    # Sicherheitsnetz UNABHAENGIG davon, ob range_start oben berechnet werden
    # konnte: manche Proxies/Server ignorieren den Range-Header und liefern
    # trotzdem die komplette Datei (200 statt 206), und falls schon die HEAD-
    # Anfrage fehlschlug (total=0) wurde oben gar kein Range-Header gesendet.
    # In beiden Faellen hier clientseitig auf die letzten ROSTOCK_TAIL_BYTES
    # zuschneiden, sonst wuerde die taeglich wachsende Datei jeden Tag mehr
    # Verarbeitungszeit kosten (verifiziert 07/2026: curl bekam 206, requests
    # in diesem Netzwerkpfad teils 200 mit voller Datei).
    sliced = False
    if len(content) > ROSTOCK_TAIL_BYTES * 1.2:
        content = content[-ROSTOCK_TAIL_BYTES:]
        sliced = True

    lines = content.decode("utf-8", errors="replace").split("\n")
    if range_start or sliced:
        lines = lines[1:]  # erste Zeile ist durch den Schnitt evtl. unvollstaendig
    return lines


def _fetch_rostock(data, stations, region_cfg, errors):
    """Radmonitore Rostock (geo.sv.rostock.de, CC0-1.0): 15-Minuten-Zaehlwerte
    je Standort in einer einzigen, fortlaufend wachsenden CSV - siehe
    ROSTOCK_TAIL_BYTES fuer die inkrementelle Abhol-Strategie. Werte werden
    hier zu Tagessummen je Standort aggregiert."""
    locs = {}
    try:
        geo = http_get(region_cfg["locations_url"], timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES).json()
        for feat in geo.get("features", []):
            props = feat.get("properties", {})
            coords = (feat.get("geometry") or {}).get("coordinates", [None, None])
            locs[str(props.get("id"))] = {"name": props.get("bezeichnung"), "lat": coords[1], "lon": coords[0]}
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"rostock: Standorte - {e}"))

    lines = _rostock_tail_lines(region_cfg["data_url"], errors)
    daily = {}  # station_id -> {date_iso: summe}
    # Bewusst KEIN csv.reader pro Zeile (bei 700-800k Zeilen im 30-MB-Tail spuerbar
    # langsam) - das Format hat keine eingebetteten Kommas/Anfuehrungszeichen in den
    # Feldern selbst, ein einfacher Split reicht und ist um ein Vielfaches schneller.
    for line in lines:
        line = line.strip()
        if not line or line.startswith("standort_id"):
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue
        sid = parts[0].strip().strip('"')
        ts, val = parts[1], parts[2]
        if len(ts) < 10:
            continue
        d_iso = ts[:10].replace("/", "-")
        try:
            v = float(val)
        except ValueError:
            continue
        daily.setdefault(sid, {})
        daily[sid][d_iso] = daily[sid].get(d_iso, 0.0) + v

    fresh = {}
    for sid, day_sums in daily.items():
        loc = locs.get(sid, {"name": sid, "lat": None, "lon": None})
        key = f"rostock_{sid}"
        st = _station(
            stations, key, name=f"Rostock – {loc['name'] or sid}",
            lat=loc["lat"], lon=loc["lon"],
            bundesland=region_cfg["bundesland"], region="rostock",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, val in day_sums.items():
            _add_station_point(st, d_iso, val)
            pts.append((d_iso, val))
        fresh[key] = pts
    return fresh


# --------------------------------------------------------------- Main -----

REGION_FETCHERS = {
    "bw": _fetch_bw,
    "leipzig": _fetch_leipzig,
    "muenchen": _fetch_muenchen,
    "nrw_muenster": _fetch_nrw_muenster,
    "nrw_dortmund": _fetch_dortmund,
    "nrw_duesseldorf": _fetch_duesseldorf,
    "rostock": _fetch_rostock,
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
            elif region_key == "nrw_koeln":
                fresh = _fetch_koeln(data, stations, region_cfg, errors)
                n = _push_region_series(data, region_key, region_cfg, _region_daily_sums(fresh), "monthly")
                print(f"radverkehr[{region_key}]: {len(fresh)} Zählstellen, {n} Monats-Summenpunkte "
                      f"(Jahresarchiv, seit 2022 nicht aktualisiert)", flush=True)
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
