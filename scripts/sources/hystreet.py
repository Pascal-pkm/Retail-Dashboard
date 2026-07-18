"""Hystreet-Passantenfrequenzen (Standortebene).

WICHTIG (COMPLIANCE.md): Die AGB des kostenlosen FREE-Tarifs verbieten
automatisierte Abfragen und jede Veroeffentlichung. Dieses Modul laeuft daher
NUR, wenn (a) config.hystreet.enabled = true UND (b) Secret HYSTREET_API_KEY
gesetzt ist - also erst nach schriftlicher Freigabe durch hystreet bzw. mit
einem dafuer lizenzierten Zugang. Quellenangabe "hystreet.com" ist Pflicht.
"""
import os
import time
from datetime import date, timedelta

from common import add_point, http_get_json, upsert_series

API_BASE = "https://hystreet.com/api"
SOURCE = "hystreet.com"

# Bewusst kurz gehalten: die Hystreet-API antwortet ueblicherweise in < 5s.
# Bei 40s-Timeout x 3 Versuchen koennte ein einzelner haengender Standort ueber
# 2 Minuten blockieren und bei 49 Standorten den ganzen Lauf > 1h dauern lassen,
# ohne dass in den Actions-Logs sichtbar ist, was gerade passiert.
REQUEST_TIMEOUT = 15
REQUEST_RETRIES = 2


def _headers(token):
    return {
        "X-API-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/vnd.hystreet.v2",
    }


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
        # Standorte auflisten, damit IDs in config.json eingetragen werden koennen
        locs = http_get_json(f"{API_BASE}/locations", headers=_headers(token))
        sample = [f"{l.get('id')}: {l.get('city')} {l.get('name')}" for l in locs[:20]]
        raise RuntimeError("Keine location_ids konfiguriert. Beispiele: " + "; ".join(sample))

    frm = (date.today() - timedelta(days=8)).isoformat()
    to = (date.today() - timedelta(days=1)).isoformat()
    n = len(loc_ids)
    ok, failed = 0, 0
    print(f"hystreet: starte Abruf von {n} Standorten (Timeout {REQUEST_TIMEOUT}s, {REQUEST_RETRIES} Versuche je Standort)", flush=True)

    for i, lid in enumerate(loc_ids, start=1):
        t0 = time.time()
        try:
            j = http_get_json(
                f"{API_BASE}/locations/{lid}",
                headers=_headers(token),
                params={"from": frm, "to": to, "resolution": "day"},
                timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES,
            )
            name = f"{j.get('city', '')} {j.get('name', lid)}".strip()
            s = upsert_series(
                data, f"hystreet_{lid}",
                label=f"Passantenfrequenz {name}", frequency="daily",
                unit="Passanten/Tag", scope="standort",
                source=SOURCE, source_url="https://hystreet.com",
            )
            n_points = 0
            for m in j.get("measurements", []):
                ts = str(m.get("timestamp", ""))[:10]
                cnt = m.get("pedestrians_count")
                if isinstance(cnt, dict):
                    cnt = cnt.get("adult", 0) + cnt.get("child", 0)
                add_point(s, ts, cnt, "daily")
                n_points += 1
            ok += 1
            print(f"  [{i}/{n}] OK  Standort {lid} ({name or '?'}) – {n_points} Punkte, {time.time()-t0:.1f}s", flush=True)
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append(("hystreet", f"Standort {lid}: {e}"))
            print(f"  [{i}/{n}] FEHLER Standort {lid}: {e} ({time.time()-t0:.1f}s)", flush=True)

    print(f"hystreet: fertig – {ok} OK, {failed} fehlgeschlagen von {n} Standorten", flush=True)
