"""Gemeinsame Helfer: data.json-Verwaltung, HTTP mit Retry, Fehlerprotokoll."""
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "docs" / "data.json"
CONFIG_PATH = ROOT / "config" / "config.json"

MAX_POINTS = {"daily": 1600, "weekly": 260, "monthly": 300, "quarterly": 40}
# daily=1600 (~4,4 Jahre) statt frueher 730, damit ein Hystreet-Backfill ab 2024
# nicht durch die Historienbegrenzung wieder abgeschnitten wird.
# monthly=300 (25 Jahre) statt frueher 120 (10 Jahre), damit die ifo-Geschaeftsklima-
# Zeitreihe (komplette Historie seit 01/2005, siehe ifo_hde.py) nicht abgeschnitten wird.

USER_AGENT = "retail-kpi-dashboard (github.com; nicht-kommerzielles Branchen-Monitoring)"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_data() -> dict:
    if DATA_PATH.exists():
        with open(DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data.setdefault("meta", {"project": "Retail KPI Dashboard", "updated": {}})
    data.setdefault("series", {})
    data.setdefault("commentary", {})
    data.setdefault("errors", {})
    return data


def save_data(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"data.json gespeichert ({DATA_PATH})")


def http_get(url, *, headers=None, params=None, retries=3, timeout=40, backoff=5):
    """GET mit Retry und User-Agent. Wirft nach letztem Versuch."""
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=h, params=params, timeout=timeout)
            if r.status_code == 429 and attempt < retries:
                time.sleep(backoff * attempt * 2)
                continue
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last


def http_get_json(url, **kw):
    return http_get(url, **kw).json()


def upsert_series(data, sid, *, label, frequency, unit, scope, source, source_url=""):
    """Serie anlegen/aktualisieren. scope: 'standort' | 'konzern' | 'branche'."""
    s = data["series"].setdefault(sid, {"points": []})
    s.update({
        "label": label,
        "frequency": frequency,
        "unit": unit,
        "scope": scope,
        "source": source,
        "source_url": source_url,
    })
    return s


def add_point(series, date_str, value, frequency="daily"):
    """Punkt einfuegen/ersetzen (dedupliziert nach Datum), sortiert, Historie begrenzt."""
    if value is None:
        return
    pts = {p[0]: p[1] for p in series["points"]}
    pts[str(date_str)] = round(float(value), 4)
    series["points"] = sorted([[k, v] for k, v in pts.items()])[-MAX_POINTS.get(frequency, 500):]


def record_error(errors: list, source: str, exc_or_msg):
    msg = f"{source}: {exc_or_msg}"
    print(f"WARNUNG - {msg}")
    errors.append({"time": now_iso(), "source": source, "message": str(exc_or_msg)[:400]})


def merge_errors(data, freq, ran_sources, error_log):
    """Fehlerliste fuer `freq` aktualisieren, ohne Eintraege anderer (nicht in diesem
    Lauf enthaltener) Quellen zu verlieren - wichtig, weil hystreet separat/manuell
    laeuft und sonst vom automatisierten Tageslauf ueberschrieben wuerde."""
    kept = [e for e in data["errors"].get(freq, []) if e.get("source") not in ran_sources]
    for src, msg in error_log:
        record_error(kept, src, msg)
    data["errors"][freq] = kept
    return kept


def pct_change(new, old):
    if old in (None, 0):
        return None
    return (new - old) / abs(old) * 100.0


def fmt_de(x, digits=1):
    """Zahl im deutschen Format."""
    s = f"{x:,.{digits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# --- Bucket-Aggregation (Python-Portierung der gleichnamigen JS-Funktionen aus
# docs/index.html: gtBucketKey/rvAggregateSum/rvBucketKeyLastYear/rvYoY/gtAggregate).
# Damit rechnet der Newsletter fuer weekly/monthly/quarterly exakt dieselben
# Buckets/YoY-Vergleiche wie der Karte-/Fussgaenger-/Google-Trends-Tab auf der
# Website - keine zweite, potenziell abweichende Aggregationslogik.

def bucket_key(date_str: str, freq: str) -> str:
    if freq == "daily":
        return date_str
    d = date.fromisoformat(date_str)
    if freq == "weekly":
        monday = d - timedelta(days=d.weekday())  # weekday(): 0=Montag, passt zur JS-Logik
        return monday.isoformat()
    if freq == "monthly":
        return date_str[:7] + "-01"
    if freq == "quarterly":
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"
    return date_str


def bucket_key_last_year(bkey: str, freq: str) -> str:
    if freq == "monthly":
        y, m, _ = bkey.split("-")
        return f"{int(y) - 1}-{m}-01"
    if freq == "quarterly":
        y, q = bkey.split("-Q")
        return f"{int(y) - 1}-Q{q}"
    # woechentlich: 364 Tage (52 Wochen) zurueck trifft dieselbe Kalenderwoche im
    # Vorjahr fast immer exakt (Abweichung nur in 53-Wochen-Jahren moeglich).
    d = date.fromisoformat(bkey) - timedelta(days=364)
    return d.isoformat()


def aggregate_sum(points, freq):
    """Punkte je Bucket aufsummieren (fuer Radverkehr/Fussgaenger-Zaehlwerte)."""
    buckets = {}
    for d, v in points:
        k = bucket_key(d, freq)
        buckets[k] = buckets.get(k, 0) + v
    return sorted(buckets.items())


def aggregate_avg(points, freq):
    """Punkte je Bucket mitteln (fuer 0-100-Indizes wie Google Trends)."""
    if freq == "daily":
        return sorted(points)
    buckets = {}
    for d, v in points:
        k = bucket_key(d, freq)
        s, c = buckets.get(k, (0.0, 0))
        buckets[k] = (s + v, c + 1)
    return sorted((k, s / c) for k, (s, c) in buckets.items())


def yoy_from_points(agg_points, freq):
    """Letzter Bucket-Wert + Veraenderung ggue. demselben Bucket im Vorjahr.
    Rueckgabe: (value, chg_pct_or_None, bucket_date) oder (None, None, None)."""
    if not agg_points:
        return None, None, None
    d, v = agg_points[-1]
    m = dict(agg_points)
    prev = m.get(bucket_key_last_year(d, freq))
    chg = pct_change(v, prev) if prev not in (None, 0) else None
    return v, chg, d
