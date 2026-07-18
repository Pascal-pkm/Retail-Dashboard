"""Hystreet-Passantenfrequenzen (Standortebene).

WICHTIG (COMPLIANCE.md): Die AGB des kostenlosen FREE-Tarifs verbieten
automatisierte Abfragen und jede Veroeffentlichung. Dieses Modul laeuft daher
NUR, wenn (a) config.hystreet.enabled = true UND (b) Secret HYSTREET_API_KEY
gesetzt ist - also erst nach schriftlicher Freigabe durch hystreet bzw. mit
einem dafuer lizenzierten Zugang. Quellenangabe "hystreet.com" ist Pflicht.
"""
import os
from datetime import date, timedelta

from common import add_point, http_get_json, upsert_series

API_BASE = "https://hystreet.com/api"
SOURCE = "hystreet.com"


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
    for lid in loc_ids:
        try:
            j = http_get_json(
                f"{API_BASE}/locations/{lid}",
                headers=_headers(token),
                params={"from": frm, "to": to, "resolution": "day"},
            )
            name = f"{j.get('city', '')} {j.get('name', lid)}".strip()
            s = upsert_series(
                data, f"hystreet_{lid}",
                label=f"Passantenfrequenz {name}", frequency="daily",
                unit="Passanten/Tag", scope="standort",
                source=SOURCE, source_url="https://hystreet.com",
            )
            for m in j.get("measurements", []):
                ts = str(m.get("timestamp", ""))[:10]
                cnt = m.get("pedestrians_count")
                if isinstance(cnt, dict):
                    cnt = cnt.get("adult", 0) + cnt.get("child", 0)
                add_point(s, ts, cnt, "daily")
        except Exception as e:  # noqa: BLE001
            errors.append(("hystreet", f"Standort {lid}: {e}"))
