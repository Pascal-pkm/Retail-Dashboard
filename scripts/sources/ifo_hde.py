"""ifo-Geschaeftsklimaindex (absolute Punktwerte) + HDE-Konsumbarometer-Hinweise.

Die ifo-Webseite ist JS-gerendert und nicht scrapbar. Stattdessen nutzen wir das
Destatis "Dashboard Deutschland": Die Tile-Definition (tile_1667288019608) enthaelt
im Textbaustein die aktuelle Pressemitteilungs-Passage mit absoluten Punktwerten
("... sank im Maerz auf 86,4 Punkte, nach 88,4 Punkten im Februar ...").
Lizenz: dl-de/by-2-0 (Destatis), inhaltlich ifo Institut - Quellenangabe erfolgt.
"""
import re
from datetime import date

from common import add_point, upsert_series
from sources.destatis_dashboard import get_tile, tile_widgets

TILE_IFO = "tile_1667288019608"
TILE_KONSUM = "tile_1667983271066"
SOURCE = "ifo Institut via Destatis Dashboard Deutschland, dl-de/by-2-0"

MONTHS = {"januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
          "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}


def _strip_html(t):
    return re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", " ", t or ""))


def _parse_version_date(s):
    """'März 2026' -> 2026-03-01."""
    m = re.match(r"(\w+)\s+(\d{4})", (s or "").strip())
    if m and m.group(1).lower() in MONTHS:
        return date(int(m.group(2)), MONTHS[m.group(1).lower()], 1).isoformat()
    return date.today().replace(day=1).isoformat()


def fetch(data, config, errors):
    widgets = []
    try:
        inner = get_tile(TILE_IFO)
        text = " ".join(_strip_html(c.get("text", "")) for c in inner.get("components", [])
                        if c.get("type") == "text")
        m = re.search(r"(?:stieg|sank|liegt|fiel|kletterte)\s+im\s+(\w+)\s+auf\s+(\d{2,3}[.,]\d)\s*Punkte", text)
        if not m:
            m = re.search(r"auf\s+(\d{2,3}[.,]\d)\s*Punkte", text)
            month_name = None
        else:
            month_name = m.group(1).lower()
        if not m:
            raise RuntimeError("kein Punktwert im Tile-Text gefunden (Struktur geaendert?)")
        value = float(m.group(m.lastindex).replace(",", "."))
        if not (50 <= value <= 130):
            raise RuntimeError(f"unplausibler Wert: {value}")

        when = _parse_version_date(inner.get("dataVersionDate", ""))
        if month_name in MONTHS:
            when = date(int(when[:4]), MONTHS[month_name], 1).isoformat()

        s = upsert_series(
            data, "ifo_geschaeftsklima",
            label="ifo-Geschäftsklimaindex", frequency="monthly",
            unit="Punkte (2015=100)", scope="branche",
            source=SOURCE, source_url="https://www.ifo.de/umfragen/ifo-geschaeftsklimaindex",
        )
        add_point(s, when, value, "monthly")
        widgets.extend(tile_widgets(inner))
    except Exception as e:  # noqa: BLE001
        errors.append(("ifo", str(e)))

    # HDE-Konsumbarometer / GfK-Konsumklima: fertige Aussagen aus dem Konsum-Tile
    try:
        widgets.extend(tile_widgets(get_tile(TILE_KONSUM)))
    except Exception as e:  # noqa: BLE001
        errors.append(("hde_konsum", str(e)))

    data.setdefault("dashboard_widgets", {})["monthly"] = widgets
