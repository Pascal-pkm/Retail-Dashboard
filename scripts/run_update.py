"""Einstiegspunkt der Cron-Jobs: python scripts/run_update.py <daily|weekly|monthly|quarterly>

Fragt alle Quellen der jeweiligen Frequenz ab (jede Quelle einzeln abgesichert),
erzeugt die Kommentierung und schreibt docs/data.json.
Exit-Code ist auch bei Teilfehlern 0 - Fehler stehen in data.json unter "errors".

Hinweis: Hystreet laeuft NICHT hier, sondern separat und nur manuell ueber
scripts/run_hystreet.py bzw. den Workflow "Hystreet manuell" - siehe COMPLIANCE.md.
"""
import sys

import commentary
from common import load_config, load_data, merge_errors, now_iso, save_data

from sources import (destatis_dashboard, eurostat_retail, fussgaenger,
                     genesis_retail, google_trends, ifo_hde, ir_reports,
                     pinterest_trends, radverkehr, stocks)

FETCHERS = {
    "daily": [("google_trends", google_trends.fetch),
              ("stocks", stocks.fetch),
              ("radverkehr", radverkehr.fetch),
              ("fussgaenger", fussgaenger.fetch)],
    "weekly": [("destatis_dashboard", destatis_dashboard.fetch),
               ("pinterest_trends", pinterest_trends.fetch)],
    "monthly": [("genesis", genesis_retail.fetch),
                ("eurostat", eurostat_retail.fetch),
                ("ifo", ifo_hde.fetch)],
    "quarterly": [("ir_reports", ir_reports.fetch)],
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in FETCHERS:
        sys.exit(f"Aufruf: python scripts/run_update.py <{'|'.join(FETCHERS)}>")
    freq = sys.argv[1]

    config = load_config()
    data = load_data()
    error_log = []          # gesammelte (quelle, meldung)-Tupel

    ran_sources = {name for name, _ in FETCHERS[freq]}
    for name, fn in FETCHERS[freq]:
        try:
            fn(data, config, error_log)
            print(f"OK: {name}")
        except Exception as e:  # noqa: BLE001
            error_log.append((name, str(e)))

    formatted_errors = merge_errors(data, freq, ran_sources, error_log)
    data["meta"]["updated"][freq] = now_iso()

    commentary.generate(data, freq, config)
    save_data(data)

    n_series = sum(1 for s in data["series"].values() if s.get("frequency") == freq)
    print(f"Fertig: {freq} - {n_series} Serien, {len(formatted_errors)} Fehler")


if __name__ == "__main__":
    main()
