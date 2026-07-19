"""Destatis GENESIS-Online: Einzelhandelsumsatz (Tabelle 45212-0001, inkl. WZ 47.91 Versand-/Internethandel).

Benoetigt kostenlose GENESIS-Registrierung -> Secrets GENESIS_USER / GENESIS_PASS.
Lizenz: Datenlizenz Deutschland 2.0 (Namensnennung), siehe COMPLIANCE.md.
"""
import csv
import io
import os

from common import add_point, http_get, upsert_series

API = "https://www-genesis.destatis.de/genesisWS/rest/2020/data/tablefile"
SOURCE = "Statistisches Bundesamt (Destatis), GENESIS-Online, Tabelle 45212-0001, dl-de/by-2-0"

# In der ffcsv-Ausgabe interessante Wirtschaftszweige
WZ_FILTER = {
    "WZ08-47": "Einzelhandel gesamt",
    "WZ08-4771": "EH mit Bekleidung",
    "WZ08-4772": "EH mit Schuhen/Lederwaren",
    "WZ08-4791": "Versand-/Interneteinzelhandel",
}


def fetch(data, config, errors):
    user = os.environ.get("GENESIS_USER", "").strip()
    pw = os.environ.get("GENESIS_PASS", "").strip()
    if not user:
        errors.append(("genesis", "Secrets GENESIS_USER/GENESIS_PASS nicht gesetzt - uebersprungen"))
        return
    table = config.get("genesis", {}).get("table", "45212-0001")

    r = http_get(API, params={
        "username": user, "password": pw, "name": table,
        "area": "all", "format": "ffcsv", "language": "de", "compress": "false",
    }, timeout=120)
    # r.text verlaesst sich auf requests' Encoding-Erkennung, die ohne charset im
    # Content-Type-Header oft danebenliegt (siehe muenchen-BOM-Bug in radverkehr.py).
    # Ausserdem faengt die Antwort manchmal mit einer BOM oder leeren Fuehrungszeile(n)
    # an, wodurch csv.DictReader die erste (leere) Zeile faelschlich als Header mit
    # nur einer leeren Spalte "" einliest. Beides hier robust abfangen.
    text = r.content.decode("utf-8-sig", errors="replace")
    text = text.lstrip("﻿\r\n \t")
    if text.lstrip().startswith("{"):
        # Fehlerobjekt statt CSV
        raise RuntimeError(f"GENESIS-Antwort: {text[:300]}")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = list(reader)
    if not rows:
        raise RuntimeError(f"Leere ffcsv-Antwort (erste 200 Zeichen: {text[:200]!r})")

    cols = rows[0].keys()
    def col(*cands):
        for c in cands:
            for k in cols:
                if c.lower() in k.lower():
                    return k
        return None

    c_year = col("Zeit", "time")
    c_month = col("1_Auspraegung_Code", "1_variable_attribute_code")
    c_wz = col("2_Auspraegung_Code", "2_variable_attribute_code")
    c_valcode = col("Wertkennziffer", "value_variable_code", "Merkmal_Code")
    c_val = col("Wert", "value")
    if not all([c_year, c_val]):
        raise RuntimeError(
            f"Unerwartetes ffcsv-Format, Spalten: {list(cols)[:12]} "
            f"(erste 200 Zeichen der Antwort: {text[:200]!r})"
        )

    month_map = {f"MONAT{str(i).zfill(2)}": i for i in range(1, 13)}

    n = 0
    for row in rows:
        wz = (row.get(c_wz) or "").strip()
        if wz not in WZ_FILTER:
            continue
        valcode = (row.get(c_valcode) or "").strip()
        # UMS002: Umsatz real (Messzahl), UMS001: nominal - wir nehmen real, sonst alles
        if valcode and valcode not in ("UMS002", "UMS102"):
            continue
        mcode = (row.get(c_month) or "").strip().upper()
        month = month_map.get(mcode)
        year = (row.get(c_year) or "").strip()
        raw = (row.get(c_val) or "").strip().replace(",", ".")
        if not (month and year) or raw in ("", "...", ".", "-", "x"):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        sid = f"genesis_{wz.lower().replace('-', '_')}"
        s = upsert_series(
            data, sid,
            label=f"Einzelhandelsumsatz real – {WZ_FILTER[wz]}",
            frequency="monthly", unit="Index (2021=100)", scope="branche",
            source=SOURCE,
            source_url="https://www-genesis.destatis.de/datenbank/online/table/45212-0001",
        )
        add_point(s, f"{year}-{month:02d}-01", value, "monthly")
        n += 1
    if n == 0:
        raise RuntimeError("Keine passenden Zeilen (WZ-Filter/Wertkennziffer pruefen)")
