"""Passantenfrequenzen (Fussgaenger-Zaehlung) - von der Stadt Oldenburg selbst
oeffentlich re-publizierte Sensordaten, DL-DE-BY-2.0.

WICHTIG - rechtliche Einordnung ggue. Hystreet (siehe COMPLIANCE.md Abschnitt 1):
Die eigentlichen Hystreet-AGB erlauben nur "private Information", eine
Vertragsstrafe droht bei Veroeffentlichung ohne gesonderte Genehmigung. Hier
handelt es sich TECHNISCH um dieselbe Art Sensordaten (Laserscanner-Zaehler),
aber die Stadt Oldenburg hat als Hystreet-Kundin/Auftraggeberin ihre eigenen
Messwerte unter der offenen Datenlizenz Deutschland - Namensnennung - 2.0 auf
ihrem eigenen Open-Data-Portal veroeffentlicht. Das ist eine andere rechtliche
Situation als ein direkter Zugriff auf hystreet.com/die Hystreet-API: die
Stadt selbst entscheidet ueber die Veroeffentlichung ihrer eigenen Daten,
unabhaengig von Hystreets eigenen Nutzungsbedingungen fuer den API-Zugriff.
Siehe COMPLIANCE.md Abschnitt 6 fuer die vollstaendige Abwaegung.

Jahresarchiv (DCAT-Metadaten: frequency=ANNUAL), ein neuer Jahrgang erscheint
erst nach Jahresende - daher werden bei jedem Lauf aktuelles + Vorjahr neu
geladen (analog zu Duesseldorf in radverkehr.py).
"""
import csv
import io
from datetime import date

from common import add_point, http_get, upsert_series

SOURCE_MODULE = "fussgaenger"
STATION_MAX_POINTS = 600
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 1

# Standort-Koordinaten sind nicht in der CSV enthalten - per Nominatim/
# OpenStreetMap ermittelt (07/2026), da alle vier Zaehlstellen bekannte,
# eindeutig auffindbare Innenstadt-Straßen sind.
KNOWN_LOCATIONS = {
    "Achternstraße, Oldenburg": (53.1406213, 8.2149035),
    "Haarenstraße, Oldenburg": (53.1405163, 8.2110604),
    "Haarenstraße (Ost), Oldenburg": (53.1405163, 8.2110604),
    "Lange Straße, Oldenburg": (53.1396605, 8.2131876),
}


def _slugify(name):
    return name.split(",")[0].strip().lower().replace(" ", "_").replace("(", "").replace(")", "").replace("ß", "ss").replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")


def _station(stations, key, *, name, lat, lon, source, source_url):
    st = stations.setdefault(key, {"points": []})
    st.update({
        "name": name, "lat": lat, "lon": lon, "bundesland": "Niedersachsen",
        "region": "oldenburg", "source": source, "source_url": source_url,
        "unit": "Fußgänger/Tag",
    })
    return st


def _add_station_point(station, date_str, value, max_points=STATION_MAX_POINTS):
    if value is None:
        return
    pts = {p[0]: p[1] for p in station["points"]}
    pts[str(date_str)] = round(float(value), 2)
    station["points"] = sorted([[k, v] for k, v in pts.items()])[-max_points:]


def fetch(data, config, errors):
    region_cfg = config.get("fussgaenger", {}).get("oldenburg")
    if not region_cfg:
        print("fussgaenger: keine Konfiguration - uebersprungen")
        return

    stations = data.setdefault("fussgaenger_stations", {})
    today = date.today()
    years = sorted({today.year, today.year - 1})

    daily_by_loc = {}  # location -> {date_iso: wert}
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
        lat, lon = KNOWN_LOCATIONS.get(loc, (None, None))
        key = f"oldenburg_{_slugify(loc)}"
        st = _station(
            stations, key, name=f"{loc.split(',')[0].strip()} (Oldenburg)",
            lat=lat, lon=lon, source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        pts = []
        for d_iso, v in day_vals.items():
            _add_station_point(st, d_iso, v)
            pts.append((d_iso, v))
        fresh[key] = pts

    sums = {}
    for pts in fresh.values():
        for d, v in pts:
            sums[d] = sums.get(d, 0) + v

    if sums:
        s = upsert_series(
            data, "fussgaenger_region_oldenburg",
            label="Passantenfrequenz-Index Oldenburg (Tagessumme aller Zählstellen)",
            frequency="daily", unit="Fußgänger/Tag (Summe)", scope="region",
            source=region_cfg["source"], source_url=region_cfg.get("source_url", ""),
        )
        for d, v in sums.items():
            add_point(s, d, v, "daily")

    print(f"fussgaenger: {len(fresh)} Zählstellen (Oldenburg), {len(sums)} Tages-Summenpunkte", flush=True)
