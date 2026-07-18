"""Manueller Hystreet-Lauf: python scripts/run_hystreet.py

Bewusst GETRENNT vom automatisierten Tageslauf (run_update.py) und ohne eigenen
Cron-Schedule - du startest ihn nur, wenn du willst (lokal oder ueber den
GitHub-Actions-Workflow "Hystreet manuell", per Hand ausgeloest).

Hintergrund/Restrisiko (siehe COMPLIANCE.md): Die hystreet-AGB (FREE-Tarif)
untersagen "automatisierte Abfrage ... durch Roboter bzw. Softwaretools"
unabhaengig davon, ob der Lauf per Cron oder per Knopfdruck gestartet wird,
und verbieten Veroeffentlichung ohne Zustimmung - auch ein manueller Lauf,
dessen Ergebnis in diesem OEFFENTLICHEN Repo/Dashboard landet, faellt darunter.
Das Modul bleibt daher per Config-Gate (hystreet.enabled) + fehlendem Secret
standardmaessig inaktiv; die Aktivierung ist eine bewusste Entscheidung/
Risikoabwaegung, die nur du triffst - z.B. nach Ruecksprache mit hystreet.
"""
import commentary
from common import load_config, load_data, merge_errors, now_iso, save_data
from sources import hystreet


def main():
    config = load_config()
    data = load_data()
    error_log = []

    try:
        hystreet.fetch(data, config, error_log)
        print("OK: hystreet")
    except Exception as e:  # noqa: BLE001
        error_log.append(("hystreet", str(e)))

    # Nur den hystreet-Anteil der "daily"-Fehlerliste ersetzen, Google-Trends/
    # Aktien-Fehler des automatisierten Laufs bleiben unangetastet.
    formatted_errors = merge_errors(data, "daily", {"hystreet"}, error_log)
    data["meta"]["updated"]["hystreet_manual"] = now_iso()

    commentary.generate(data, "daily", config)
    save_data(data)

    n_hystreet = sum(1 for sid in data["series"] if sid.startswith("hystreet_"))
    print(f"Fertig: hystreet manuell - {n_hystreet} Standort-Serien, {len(formatted_errors)} Fehler (daily gesamt)")


if __name__ == "__main__":
    main()
