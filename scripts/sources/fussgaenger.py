"""Passantenfrequenzen (Fussgaenger-Zaehlung, KEIN Radverkehr) - von den Staedten
selbst oeffentlich re-publizierte Sensordaten aus 8 Regionen (Stand 07/2026).

WICHTIG - rechtliche Einordnung ggue. Hystreet (siehe COMPLIANCE.md Abschnitt 6):
Hystreets eigene AGB erlauben im kostenfreien Tarif nur "private Nutzung" und
untersagen gewerbliche Weiterveroeffentlichung. Oldenburg und Wuerzburg haben
jedoch ihre eigenen (bzw. per Laserscanner selbst erhobenen) Messwerte unter
einer offenen Datenlizenz (dl-de/by-2.0) auf ihrem jeweils eigenen Open-Data-
Portal veroeffentlicht - das ist eine andere rechtliche Situation als ein
direkter Zugriff auf hystreet.com/die Hystreet-API: die Stadt selbst
entscheidet ueber die Veroeffentlichung ihrer eigenen Daten. Bei der
bundesweiten Recherche 2026-07 wurde geprueft, ob weitere Staedte denselben
Weg gegangen sind - Bonn, Muenster und Berlin taten das NICHT (deren
"Open Data"-Eintraege verweisen nur auf eine hystreet.com-Registrierung mit
Nutzungsbeschraenkung, siehe COMPLIANCE.md), Dortmund/Neuss/Bamberg/Augsburg
hingegen haben unabhaengige eigene Sensorik (nicht Hystreet) und stellen ihre
Rohdaten direkt als Datei bereit.

8 Regionen:
  - oldenburg  (dl-de/by-2.0, Hystreet-Sensoren, seit 2020)
  - wuerzburg  (dl-de/by-2.0, eigene Laserscanner, seit 2020)
  - dortmund   (dl-de/zero-2.0, eigene Sensorik "Westenhellweg", seit 2018,
                hier ab 2024 geladen)
  - neuss      (cc-by-4.0, BLE-Sensoren "Puls der Stadt", erst seit 06/2026)
  - bamberg    (KEINE explizite Lizenz gefunden - Restrisiko, siehe
                COMPLIANCE.md Abschnitt 6 und config.json._risiko)
  - augsburg   (KEINE explizite Lizenz gefunden - Restrisiko, siehe
                COMPLIANCE.md Abschnitt 6 und config.json._risiko)
  - moers      (dl-de/zero-2.0, eigener 4-fach-Laser seit 05/2022, neu 07/2026)
  - berlin     (CC BY 4.0, Telraam-Buergerwissenschaft "Berlin zaehlt
                Mobilitaet", neu 07/2026 - siehe COMPLIANCE.md Abschnitt 6.4)
"""
import csv
import gzip
import io
from datetime import date

from common import add_point, http_get, upsert_series

SOURCE_MODULE = "fussgaenger"
STATION_MAX_POINTS = 600
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 2

# Standort-Koordinaten, die nicht in der jeweiligen CSV enthalten sind - per
# Nominatim/OpenStreetMap ermittelt (07/2026).
KNOWN_LOCATIONS_OLDENBURG = {
    "Achternstraße, Oldenburg": (53.1406213, 8.2149035),
    "Haarenstraße, Oldenburg": (53.1405163, 8.2110604),
    "Haarenstraße (Ost), Oldenburg": (53.1405163, 8.2110604),
    "Lange Straße, Oldenburg": (53.1396605, 8.2131876),
}


def _slugify(name):
    return (name.split(",")[0].strip().lower().replace(" ", "_")
            .replace("(", "").replace(")", "")
            .replace("ß", "ss").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae"))


def _station(stations, key, *, name, lat, lon, region, bundesland, source, source_url, unit="Fußgänger/Tag"):
    st = stations.setdefault(key, {"points": []})
    st.update({
        "name": name, "lat": lat, "lon": lon, "bundesland": bundesland,
        "region": region, "source": source, "source_url": source_url,
        "unit": unit,
    })
    return st


def _add_station_point(station, date_str, value, max_points=STATION_MAX_POINTS):
    if value is None:
        return
    pts = {p[0]: p[1] for p in station["points"]}
    pts[str(date_str)] = round(float(value), 2)
    station["points"] = sorted([[k, v] for k, v in pts.items()])[-max_points:]


# --- Oldenburg (Hystreet-Sensoren, von der Stadt selbst re-publiziert) ----

def _fetch_oldenburg(region_cfg, stations, errors):
    today = date.today()
    years = sorted({today.year, today.year - 1})
    daily_by_loc = {}
    for year in years:
        url = region_cfg["csv_url_template"].format(year=year)
        try:
            r = http_get(url, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
        except Exception:  # noqa: BLE001
            continue  # Jahrgang (noch) nicht veroeffentlicht
        try:
            rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"oldenburg {year}: {e}"))
            continue
        for row in rows:
            loc = (row.get("location") or "").strip()
            ts = row.get("time of measurement") or ""
            val = row.get("pedestrians count")
            if not loc or len(ts) < 10 or val in (None, ""):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            daily_by_loc.setdefault(loc, {})[ts[:10]] = v

    fresh = {}
    for loc, day_vals in daily_by_loc.items():
        lat, lon = KNOWN_LOCATIONS_OLDENBURG.get(loc, (None, None))
        key = f"oldenburg_{_slugify(loc)}"
        st = _station(
            stations, key, name=f"{loc.split(',')[0].strip()} (Oldenburg)", lat=lat, lon=lon,
            region="oldenburg", bundesland="Niedersachsen",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


# --- Wuerzburg (eigene Laserscanner, dl-de/by-2.0) -------------------------

def _fetch_wuerzburg(region_cfg, stations, errors):
    try:
        r = http_get(region_cfg["csv_url"], timeout=90, retries=REQUEST_RETRIES)
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"wuerzburg: {e}"))
        return {}
    try:
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"wuerzburg: {e}"))
        return {}

    daily_by_loc, locs = {}, {}
    for row in rows:
        loc = (row.get("location_name") or "").strip()
        ts = row.get("timestamp") or ""
        val = row.get("pedestrians_count")
        if not loc or len(ts) < 10 or val in (None, ""):
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        daily_by_loc.setdefault(loc, {})[ts[:10]] = v
        if loc not in locs:
            gp = row.get("geo_point_2d") or ""
            if "," in gp:
                lat_s, lon_s = gp.split(",", 1)
                try:
                    locs[loc] = (float(lat_s.strip()), float(lon_s.strip()))
                except ValueError:
                    locs[loc] = (None, None)

    fresh = {}
    for loc, day_vals in daily_by_loc.items():
        lat, lon = locs.get(loc, (None, None))
        key = f"wuerzburg_{_slugify(loc)}"
        st = _station(
            stations, key, name=f"{loc} (Würzburg)", lat=lat, lon=lon,
            region="wuerzburg", bundesland="Bayern",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


# --- Dortmund (eigene Sensorik "Westenhellweg", dl-de/zero-2.0) -----------
# Jahres-Datensaetze wie Duesseldorf/Rostock in radverkehr.py. Jede Zeile
# wiederholt "Passantenaufkommen pro Standort" fuer jede Richtung/Passantentyp-
# Kombination derselben Stunde - wir dedupen ueber (Standort, Stunde), da der
# Wert dort garantiert identisch ist (live verifiziert 07/2026).

def _fetch_dortmund_fg(region_cfg, stations, errors):
    years = region_cfg.get("years") or [date.today().year]
    hourly = {}
    for year in years:
        url = region_cfg["csv_url_template"].format(year=year)
        try:
            r = http_get(url, timeout=90, retries=REQUEST_RETRIES)
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"dortmund {year}: {e}"))
            continue
        try:
            rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"dortmund {year}: {e}"))
            continue
        for row in rows:
            standort = (row.get("Standort") or "").strip()
            ts = row.get("Messzeitpunkt") or ""
            val = row.get("Passantenaufkommen pro Standort")
            if not standort or len(ts) < 13 or val in (None, ""):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            hourly[(standort, ts[:13])] = v

    daily_by_loc = {}
    for (standort, hour_key), v in hourly.items():
        d_iso = hour_key[:10]
        daily_by_loc.setdefault(standort, {})
        daily_by_loc[standort][d_iso] = daily_by_loc[standort].get(d_iso, 0.0) + v

    fresh = {}
    for standort, day_vals in daily_by_loc.items():
        key = f"dortmund_fg_{_slugify(standort)}"
        st = _station(
            stations, key, name=f"{standort} (Dortmund)",
            lat=region_cfg.get("lat"), lon=region_cfg.get("lon"),
            region="dortmund", bundesland="Nordrhein-Westfalen",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


# --- Neuss ("Puls der Stadt", BLE-Sensoren, cc-by-4.0) ---------------------

def _fetch_neuss(region_cfg, stations, errors):
    try:
        r = http_get(region_cfg["csv_url"], timeout=60, retries=REQUEST_RETRIES)
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"neuss: {e}"))
        return {}
    try:
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"neuss: {e}"))
        return {}

    daily_by_loc, locs = {}, {}
    for row in rows:
        loc = (row.get("scanner_id") or "").strip()
        d_iso = (row.get("hour_start") or "")[:10]
        val = row.get("observations")
        if not loc or len(d_iso) < 10 or val in (None, ""):
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        daily_by_loc.setdefault(loc, {})
        daily_by_loc[loc][d_iso] = daily_by_loc[loc].get(d_iso, 0.0) + v
        if loc not in locs:
            gp = row.get("geopunkt") or ""
            if "," in gp:
                lat_s, lon_s = gp.split(",", 1)
                try:
                    locs[loc] = (float(lat_s.strip()), float(lon_s.strip()))
                except ValueError:
                    locs[loc] = (None, None)

    fresh = {}
    for loc, day_vals in daily_by_loc.items():
        lat, lon = locs.get(loc, (None, None))
        key = f"neuss_{_slugify(loc)}"
        st = _station(
            stations, key, name=f"{loc} (Neuss)", lat=lat, lon=lon,
            region="neuss", bundesland="Nordrhein-Westfalen",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
            unit="BLE-Signale/Tag",
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


# --- Bamberg (26 Standorte, KEINE explizite Lizenz - Restrisiko) ----------

def _fetch_bamberg(region_cfg, stations, errors):
    encoding = region_cfg.get("csv_encoding", "cp1252")
    try:
        r = http_get(region_cfg["csv_url"], timeout=120, retries=REQUEST_RETRIES)
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"bamberg: {e}"))
        return {}
    try:
        text = r.content.decode(encoding, errors="replace")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"bamberg: {e}"))
        return {}

    daily_by_loc = {}
    for row in rows:
        bereich = (row.get("Bereich") or "").strip()
        zeit = row.get("Zeit") or ""  # "01.10.2024 06:00"
        val = row.get("Passantenanzahl")
        if not bereich or len(zeit) < 10 or val in (None, ""):
            continue
        try:
            dd, mm, rest = zeit.split(".", 2)
            yyyy = rest[:4]
            d_iso = f"{yyyy}-{mm}-{dd}"
        except ValueError:
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        daily_by_loc.setdefault(bereich, {})
        daily_by_loc[bereich][d_iso] = daily_by_loc[bereich].get(d_iso, 0.0) + v

    fresh = {}
    for bereich, day_vals in daily_by_loc.items():
        key = f"bamberg_{_slugify(bereich)}"
        st = _station(
            stations, key, name=f"{bereich} (Bamberg)", lat=None, lon=None,
            region="bamberg", bundesland="Bayern",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


# --- Augsburg (1 Standort, KEINE explizite Lizenz - Restrisiko) -----------

_AUG_MONTHS = None  # ungenutzt, Datum steckt schon numerisch in der Spalte


def _fetch_augsburg(region_cfg, stations, errors):
    try:
        r = http_get(region_cfg["csv_url"], timeout=60, retries=REQUEST_RETRIES)
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"augsburg: {e}"))
        return {}
    try:
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"augsburg: {e}"))
        return {}

    daily = {}
    for row in rows:
        standort = (row.get("Standort") or "Annastraße").strip()
        datum = row.get("Datum") or ""  # "Mi., 16.12.2020"
        val = row.get("Passanten")
        if len(datum) < 10 or val in (None, ""):
            continue
        try:
            datum_part = datum.split(",")[-1].strip()  # "16.12.2020"
            dd, mm, yyyy = datum_part.split(".")
            d_iso = f"{yyyy}-{mm}-{dd}"
        except ValueError:
            continue
        try:
            v = float(val)
        except ValueError:
            continue
        daily.setdefault(standort, {})
        daily[standort][d_iso] = daily[standort].get(d_iso, 0.0) + v

    fresh = {}
    for standort, day_vals in daily.items():
        key = f"augsburg_{_slugify(standort)}"
        st = _station(
            stations, key, name=f"{standort} (Augsburg)",
            lat=region_cfg.get("lat"), lon=region_cfg.get("lon"),
            region="augsburg", bundesland="Bayern",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


# --- Moers (eigener 4-fach-Laser Steinstrasse, dl-de/zero-2.0) ------------
# CKAN-Paket wechselt jaehrlich den Namen (im-jahr-{year}); wir laden das
# aktuelle + das vorherige Jahr, analog zu Oldenburg. Innerhalb des Pakets
# gibt es pro Monat eine Tages- ("nach Tagen") und eine Stunden-Datei - wir
# nutzen nur die Tagesdateien (passt zur Aufloesung der uebrigen Regionen).

def _fetch_moers(region_cfg, stations, errors):
    years = sorted({date.today().year, date.today().year - 1})
    daily = {}
    for year in years:
        package_id = region_cfg["package_id_template"].format(year=year)
        try:
            r = http_get(
                region_cfg["ckan_base"], params={"id": package_id},
                timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES,
            )
            pkg = r.json().get("result", {})
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"moers {year}: {e}"))
            continue
        for res in pkg.get("resources", []):
            name = (res.get("name") or "").lower()
            url = res.get("url") or ""
            if "nach tag" not in name and "-taglich" not in url:
                continue
            try:
                rr = http_get(url, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
                rows = list(csv.DictReader(io.StringIO(rr.content.decode("utf-8-sig")), delimiter=";"))
            except Exception as e:  # noqa: BLE001
                errors.append((SOURCE_MODULE, f"moers {year} ({res.get('name')}): {e}"))
                continue
            for row in rows:
                ts = row.get("time of measurement") or ""
                val = row.get("pedestrians count")
                if len(ts) < 10 or val in (None, ""):
                    continue
                try:
                    v = float(val)
                except ValueError:
                    continue
                daily[ts[:10]] = v

    if not daily:
        return {}
    key = "moers_steinstrasse"
    st = _station(
        stations, key, name="Steinstraße (Moers)",
        lat=region_cfg.get("lat"), lon=region_cfg.get("lon"),
        region="moers", bundesland="Nordrhein-Westfalen",
        source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
    )
    pts = []
    for d_iso, v in daily.items():
        _add_station_point(st, d_iso, v)
        pts.append((d_iso, v))
    return {key: pts}


# --- Berlin (Telraam-Buergerwissenschaft "Berlin zaehlt Mobilitaet", CC BY 4.0)
# Buergerwissenschaftliches Sensornetz (ADFC Berlin + DLR), stuendliche Werte
# je Segment in monatlichen gzip-CSVs. Viele Segmente zaehlen nur Rad/Kfz -
# wir behalten nur Segmente mit tatsaechlich gemessenen Fussgaengerwerten
# (Summe ped_total > 0 im geladenen Zeitraum), damit die Karte nicht mit
# reinen Rad-/Kfz-Punkten ohne Fussgaengersensor ueberladen wird.

def _fetch_berlin_telraam(region_cfg, stations, errors):
    try:
        r = http_get(region_cfg["segments_url"], timeout=60, retries=REQUEST_RETRIES)
        geo = r.json()
    except Exception as e:  # noqa: BLE001
        errors.append((SOURCE_MODULE, f"berlin segments: {e}"))
        return {}

    coords = {}
    for feat in geo.get("features", []):
        props = feat.get("properties", {})
        sid = props.get("segment_id")
        geom = (feat.get("geometry") or {}).get("coordinates")
        if sid is None or not geom:
            continue
        # MultiLineString: [[[lon,lat], ...]] - Mittelpunkt der ersten Linie nehmen.
        try:
            line = geom[0]
            lon = sum(p[0] for p in line) / len(line)
            lat = sum(p[1] for p in line) / len(line)
            coords[str(sid)] = (lat, lon)
        except (IndexError, TypeError, ZeroDivisionError):
            continue

    today = date.today()
    months = []
    n_months = region_cfg.get("min_lookback_months", 2)
    y, m = today.year, today.month
    for _ in range(n_months):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1

    daily_by_seg = {}
    for y, m in months:
        url = region_cfg["csv_url_template"].format(year=y, month=m)
        try:
            r = http_get(url, timeout=60, retries=REQUEST_RETRIES)
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"berlin {y}-{m:02d}: {e}"))
            continue
        try:
            raw = r.content
            # requests entpackt Content-Encoding:gzip meist schon automatisch;
            # nur falls der Server rohe gzip-Bytes ohne den Header ausliefert
            # (z.B. anderer Proxy/CDN-Verhalten), hier zusaetzlich absichern.
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8")
            rows = list(csv.DictReader(io.StringIO(text)))
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"berlin {y}-{m:02d}: {e}"))
            continue
        for row in rows:
            sid = row.get("segment_id")
            ts = row.get("date_local") or ""
            val = row.get("ped_total")
            if not sid or len(ts) < 10 or val in (None, ""):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            d_iso = ts[:10]
            daily_by_seg.setdefault(sid, {})
            daily_by_seg[sid][d_iso] = daily_by_seg[sid].get(d_iso, 0.0) + v

    fresh = {}
    for sid, day_vals in daily_by_seg.items():
        if sum(day_vals.values()) <= 0:
            continue  # reines Rad-/Kfz-Segment ohne Fussgaengersensor - ueberspringen
        lat, lon = coords.get(str(sid), (None, None))
        key = f"berlin_telraam_{sid}"
        st = _station(
            stations, key, name=f"Telraam-Segment {sid} (Berlin)", lat=lat, lon=lon,
            region="berlin", bundesland="Berlin",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts
    return fresh


REGION_FETCHERS = {
    "oldenburg": _fetch_oldenburg,
    "wuerzburg": _fetch_wuerzburg,
    "dortmund": _fetch_dortmund_fg,
    "neuss": _fetch_neuss,
    "bamberg": _fetch_bamberg,
    "augsburg": _fetch_augsburg,
    "moers": _fetch_moers,
    "berlin": _fetch_berlin_telraam,
}


def fetch(data, config, errors):
    regions = config.get("fussgaenger", {}).get("regions", {})
    if not regions:
        print("fussgaenger: keine Konfiguration - uebersprungen")
        return

    stations = data.setdefault("fussgaenger_stations", {})
    total_stations, total_points = 0, 0

    for region_key, region_cfg in regions.items():
        fetcher = REGION_FETCHERS.get(region_key)
        if not fetcher:
            continue
        try:
            fresh = fetcher(region_cfg, stations, errors)
        except Exception as e:  # noqa: BLE001
            errors.append((SOURCE_MODULE, f"{region_key}: {e}"))
            continue

        sums = {}
        for pts in fresh.values():
            for d, v in pts:
                sums[d] = sums.get(d, 0.0) + v
        if sums:
            s = upsert_series(
                data, f"fussgaenger_region_{region_key}",
                label=f"Passantenfrequenz-Index {region_cfg['name']} (Tagessumme aller Zählstellen)",
                frequency="daily", unit="Fußgänger/Tag (Summe)", scope="region",
                source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
            )
            for d, v in sums.items():
                add_point(s, d, v, "daily")

        total_stations += len(fresh)
        total_points += sum(len(p) for p in fresh.values())
        print(f"fussgaenger[{region_key}]: {len(fresh)} Zählstellen, {len(sums)} Tages-Summenpunkte", flush=True)

    print(f"fussgaenger: {total_stations} Zählstellen gesamt (8 Regionen), {total_points} Datenpunkte", flush=True)
