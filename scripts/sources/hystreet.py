"""Hystreet-Passantenfrequenzen (Standortebene).

WICHTIG (COMPLIANCE.md): Die AGB des kostenlosen FREE-Tarifs verbieten
automatisierte Abfragen und jede Veroeffentlichung. Dieses Modul laeuft daher
NUR, wenn (a) config.hystreet.enabled = true UND (b) Secret HYSTREET_API_KEY
gesetzt ist - also erst nach schriftlicher Freigabe durch hystreet bzw. mit
einem dafuer lizenzierten Zugang. Quellenangabe "hystreet.com" ist Pflicht.

API-Referenz (verifiziert 07/2026 ueber https://hystreet.com/openapi/v2/openapi.yaml):
  Base URL: https://api.hystreet.com/v2   (NICHT hystreet.com/api!)
  Endpunkt: GET /locations/{id}/measurements
  Header:   X-API-TOKEN: <token>
  Query:    from, to (RFC3339-Zeitstempel, z.B. 2026-07-10T00:00:00Z),
            resolution (hour|day|week|month), optional with_object_type=PERSON
            (filtert Fahrzeuge/Fahrraeder aus total_count heraus)
  Response: 200 mit {location_id, name, city, measurements: [{measured_at,
            total_count, counts: [...]}]}, ODER 204 (kein Content), wenn im
            angefragten Zeitraum keine Messdaten vorliegen - das ist KEIN Fehler.
  Maximale Zeitspanne pro Anfrage laut Doku: 366 Tage -> laengere Zeitraeume
  (Backfill) werden deshalb in Jahres-Chunks aufgeteilt.
  Es gibt in der oeffentlichen v2-API keinen Endpunkt zum Auflisten aller
  Standorte; die IDs stammen aus der eingeloggten Standort-Uebersicht auf
  hystreet.com/locations (siehe config.json -> hystreet._location_ids_map).

Zwei Modi:
  - Normal (Default): laedt nur die letzten 8 Tage nach (inkrementelles Update).
  - Backfill: wenn die Umgebungsvariable HYSTREET_BACKFILL_FROM gesetzt ist
    (Format YYYY-MM-DD), werden alle Messdaten ab diesem Datum bis gestern
    nachgeladen - z.B. "2024-01-01", um mehrjaehrige Vorjahresvergleiche zu
    ermoeglichen. Macht deutlich mehr Anfragen als der Normalbetrieb (Anzahl
    Standorte x Anzahl 366-Tage-Chunks) - bewusst nur manuell/einmalig nutzen.
"""
import os
import time
from datetime import date, timedelta

from common import add_point, http_get, upsert_series

API_BASE = "https://api.hystreet.com/v2"
SOURCE = "hystreet.com"

REQUEST_TIMEOUT = 15
REQUEST_RETRIES = 2
REQUEST_DELAY = 0.3          # kleine Pause zwischen Anfragen, schont die API beim Backfill
MAX_RANGE_DAYS = 366         # API-Limit pro Anfrage


def _headers(token):
    return {"X-API-TOKEN": token, "Accept": "application/json"}


def _iso_z(d: date, end_of_day: bool = False) -> str:
    t = "23:59:59" if end_of_day else "00:00:00"
    return f"{d.isoformat()}T{t}Z"


def _date_chunks(start: date, end: date, max_days: int = MAX_RANGE_DAYS):
    """Zeitraum in <= max_days lange Abschnitte zerlegen (API-Limit)."""
    chunks = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _fetch_range(lid, token, frm_date, to_date):
    """Eine Anfrage fuer einen Standort/Zeitraum. Gibt (name, points) zurueck,
    points = Liste von (datum_str, wert). Wirft bei echten Fehlern."""
    r = http_get(
        f"{API_BASE}/locations/{lid}/measurements",
        headers=_headers(token),
        params={
            "from": _iso_z(frm_date), "to": _iso_z(to_date, end_of_day=True),
            "resolution": "day", "with_object_type": "PERSON",
        },
        timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES,
    )
    if r.status_code == 204:
        return None, []
    j = r.json()
    name = f"{j.get('city', '')} {j.get('name', lid)}".strip()
    points = []
    for m in j.get("measurements", []):
        ts = str(m.get("measured_at") or m.get("measured_at_local_time", ""))[:10]
        cnt = m.get("total_count")
        if ts and cnt is not None:
            points.append((ts, cnt))
    return name, points


def fetch(data, config, errors):
    cfg = config.get("hystreet", {})
    token = os.environ.get("HYSTREET_API_KEY", "").strip()
    if not cfg.get("enabled"):
        print("hystreet: deaktiviert (Compliance-Gate, siehe COMPLIANCE.md) - uebersprungen")
        return
    if not token:
        raise RuntimeError("hystreet aktiviert, aber Secret HYSTREET_API_KEY fehlt")

    loc_ids = cfg.get("location_ids") or []
    if not loc_ids:
        raise RuntimeError(
            "Keine location_ids konfiguriert. Die oeffentliche API bietet keinen "
            "Listing-Endpunkt - IDs manuell auf hystreet.com/locations (eingeloggt) "
            "ermitteln und in config.json -> hystreet.location_ids eintragen."
        )

    backfill_from = os.environ.get("HYSTREET_BACKFILL_FROM", "").strip()
    yesterday = date.today() - timedelta(days=1)
    if backfill_from:
        try:
            start = date.fromisoformat(backfill_from)
        except ValueError:
            raise RuntimeError(f"HYSTREET_BACKFILL_FROM='{backfill_from}' ist kein gueltiges Datum (Format: YYYY-MM-DD)")
        mode = f"BACKFILL ab {start.isoformat()}"
    else:
        start = date.today() - timedelta(days=8)
        mode = "normal (letzte 8 Tage)"
    chunks = _date_chunks(start, yesterday)

    n_loc = len(loc_ids)
    total_req = n_loc * len(chunks)
    ok, empty, failed, req_i = 0, 0, 0, 0
    print(f"hystreet: Modus {mode} - {n_loc} Standorte x {len(chunks)} Zeit-Chunk(s) = {total_req} Anfragen "
          f"(Timeout {REQUEST_TIMEOUT}s, {REQUEST_RETRIES} Versuche je Anfrage)", flush=True)

    for lid in loc_ids:
        loc_points = 0
        loc_name = None
        loc_failed = False
        for c_frm, c_to in chunks:
            req_i += 1
            t0 = time.time()
            try:
                name, pts = _fetch_range(lid, token, c_frm, c_to)
                if name:
                    loc_name = name
                if not pts:
                    empty += 1
                    print(f"  [{req_i}/{total_req}] LEER Standort {lid} {c_frm}..{c_to} - keine Messdaten ({time.time()-t0:.1f}s)", flush=True)
                else:
                    s = upsert_series(
                        data, f"hystreet_{lid}",
                        label=f"Passantenfrequenz {loc_name or lid}", frequency="daily",
                        unit="Passanten/Tag", scope="standort",
                        source=SOURCE, source_url="https://hystreet.com",
                    )
                    for ts, cnt in pts:
                        add_point(s, ts, cnt, "daily")
                    loc_points += len(pts)
                    print(f"  [{req_i}/{total_req}] OK  Standort {lid} ({loc_name or '?'}) {c_frm}..{c_to} - {len(pts)} Punkte, {time.time()-t0:.1f}s", flush=True)
            except Exception as e:  # noqa: BLE001
                loc_failed = True
                errors.append(("hystreet", f"Standort {lid} ({c_frm}..{c_to}): {e}"))
                print(f"  [{req_i}/{total_req}] FEHLER Standort {lid} {c_frm}..{c_to}: {e} ({time.time()-t0:.1f}s)", flush=True)
            time.sleep(REQUEST_DELAY)
        if loc_failed:
            failed += 1
        elif loc_points:
            ok += 1

    print(f"hystreet: fertig - {ok} Standorte mit neuen Daten, {failed} mit mind. 1 Fehler, "
          f"{empty} Chunks ohne Messdaten, {total_req} Anfragen gesamt", flush=True)
