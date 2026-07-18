"""Gemeinsame Helfer: data.json-Verwaltung, HTTP mit Retry, Fehlerprotokoll."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "docs" / "data.json"
CONFIG_PATH = ROOT / "config" / "config.json"

MAX_POINTS = {"daily": 730, "weekly": 260, "monthly": 120, "quarterly": 40}

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
