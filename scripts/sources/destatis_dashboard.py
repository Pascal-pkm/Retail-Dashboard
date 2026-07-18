"""Destatis "Dashboard Deutschland" / "Dashboard Konjunktur" - hochfrequente Einzelhandels-/Konsumindikatoren.

Verifizierte Endpunkte (Stand 07/2026):
  GET https://www.dashboard-deutschland.de/api/tile/indicators?ids=<tile_id>   (eine ID pro Aufruf!)
      -> [{"id":..., "json": "<stringified Tile-Definition>"}]
      Tile-Definition: title, sources, components[] mit
        - type=compact: widgets[] = fertige Kennzahl-Aussagen ("1,9 % weniger Passanten ...")
        - type=highcharts: dataPlatformQueryParams[] = topicIds
  GET https://www.dashboard-konjunktur.de/api/highcharts?topicId=<id>&from=<epoch_ms>
      -> Highcharts-Config; series[].data = [[epoch_ms, wert], ...]
      ACHTUNG: Werte sind MIN-MAX-NORMALISIERT (0-1) ueber das Abfragefenster.
      Daher: Serie bei jedem Lauf KOMPLETT ersetzen (nicht anhaengen) und Einheit kennzeichnen.

Lizenz: Datenlizenz Deutschland 2.0; Passantenfrequenzindex basiert auf hystreet.com
(Quellenangabe im Dashboard/Newsletter enthalten).
"""
import json as _json
import re
from datetime import datetime, timezone

from common import http_get_json, upsert_series

API_TILES = "https://www.dashboard-deutschland.de/api/tile/indicators"
API_DATA = "https://www.dashboard-konjunktur.de/api/highcharts"
SOURCE = "Destatis, Dashboard Deutschland/Konjunktur, dl-de/by-2-0"

ICON_ARROW = {"ArrowDownRight": "▼", "ArrowUpRight": "▲", "ArrowRight": "→"}


def get_tile(tile_id):
    arr = http_get_json(API_TILES, params={"ids": tile_id})
    if not arr:
        raise RuntimeError(f"Tile {tile_id} nicht gefunden (leere Antwort)")
    return _json.loads(arr[0]["json"])


def tile_widgets(inner):
    """Fertige Kennzahl-Aussagen aus der 'compact'-Komponente."""
    out = []
    for c in inner.get("components", []):
        if c.get("type") == "compact":
            for w in c.get("widgets", []) or []:
                num, desc = (w.get("num") or "").strip(), (w.get("desc") or "").strip()
                if num and desc:
                    arrow = ICON_ARROW.get(w.get("icon", ""), "•")
                    out.append(f"{arrow} {num} {desc} (Quelle: Destatis Dashboard)")
    return out


def tile_topic_ids(inner):
    ids = []
    for c in inner.get("components", []):
        for q in c.get("dataPlatformQueryParams") or []:
            tid = q.get("topicId")
            if tid:
                ids.append(tid)
    return ids


def fetch_topic_points(topic_id, from_date="2022-01-01"):
    frm = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    j = http_get_json(API_DATA, params=[("topicId", topic_id), ("from", str(frm))])
    for ser in j.get("series", []):
        pts = [
            [datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc).date().isoformat(), round(float(p[1]), 4)]
            for p in ser.get("data", []) if p and p[1] is not None
        ]
        if pts:
            return pts
    return []


def fetch(data, config, errors):
    cfg = config.get("destatis_dashboard", {})
    tiles = cfg.get("tiles", {})
    topic_series = cfg.get("topic_series", {})
    from_date = cfg.get("from_date", "2022-01-01")

    widgets = []
    for tile_id, tile_name in tiles.items():
        try:
            inner = get_tile(tile_id)
            widgets.extend(tile_widgets(inner))
            for topic_id in tile_topic_ids(inner):
                label = topic_series.get(topic_id)
                if not label:
                    continue  # nur whitelisted Topics als Zeitreihe (45212BM003 hat >600 Unterreihen)
                try:
                    pts = fetch_topic_points(topic_id, from_date)
                    if not pts:
                        raise RuntimeError("keine Datenpunkte")
                    s = upsert_series(
                        data, f"dashboard_{re.sub(r'[^a-z0-9]+', '_', topic_id.lower())}",
                        label=label, frequency="weekly",
                        unit="Index 0–1 (min-max-normalisiert)", scope="branche",
                        source=SOURCE, source_url="https://www.dashboard-konjunktur.de",
                    )
                    s["points"] = pts[-260:]  # ersetzen statt anhaengen (Normalisierung!)
                except Exception as e:  # noqa: BLE001
                    errors.append(("destatis_dashboard", f"Topic {topic_id}: {e}"))
        except Exception as e:  # noqa: BLE001
            errors.append(("destatis_dashboard", f"{tile_name} ({tile_id}): {e}"))

    data.setdefault("dashboard_widgets", {})["weekly"] = widgets
