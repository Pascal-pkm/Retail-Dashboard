# Retail-KPI-Dashboard (Mode & Einzelhandel)

Sammelt öffentliche Retail-/Mode-Branchen-KPIs in vier Frequenzen (täglich, wöchentlich, monatlich, quartalsweise), zeigt sie auf einer GitHub-Pages-Website und versendet kommentierte Newsletter.

## Architektur

- **Kein Backend**: statische Website (`docs/`), Datenbasis ist `docs/data.json`.
- **GitHub Actions** (`.github/workflows/`) mit vier Cron-Schedules (täglich/wöchentlich/monatlich/quartalsweise) aktualisieren `data.json` und committen es.
- **Hystreet läuft separat, ausschließlich manuell**: eigener Workflow `hystreet-manual.yml` **ohne** Cron-Trigger — nur per „Run workflow"-Knopf im Actions-Tab oder lokal via `python scripts/run_hystreet.py`. Grund: die hystreet-AGB stehen einem automatisierten Dauerbetrieb entgegen, siehe COMPLIANCE.md.
- **GitHub Pages** hostet `docs/` (Settings → Pages → Branch `main`, Ordner `/docs`).
- **Newsletter** über Gmail SMTP (App-Passwort) — rein privat an die in `NEWSLETTER_TO` hinterlegte(n) eigene(n) Adresse(n); nur wenn Repo-Variable `NEWSLETTER_ENABLED=true`. Design (`scripts/newsletter.py`, seit 07/2026): Farbschema der Website, Spark-Card-Stil angelehnt an Apollos "Daily Spark", Inhalt je Frequenz gescoped (täglich/wöchentlich: Google-Trends + Frequenzen; monatlich zusätzlich ifo-Indizes; quartalsweise zusätzlich Zalando-IR-Kennzahlen).
- **Newsletter-Versand ist vom Daten-Fetch entkoppelt** (seit 07/2026, Nutzerwunsch "immer 10 Uhr morgens"): eigener Workflow `newsletter.yml` verschickt unabhängig davon, wann die Daten zuletzt aktualisiert wurden, immer um **10:00 Uhr Berliner Zeit** (Sommer- und Winterzeit gleichermaßen, über zwei UTC-Cron-Trigger + eine Zeitzonen-Prüfung im ersten Schritt) die an diesem Kalendertag fällige(n) Frequenz(en) – täglich immer, wöchentlich montags, monatlich am 5., quartalsweise am 20.02./20.05./20.08./20.11. Der optionale Newsletter-Versand beim manuellen Hystreet-Lauf (`hystreet-manual.yml`, Checkbox) bleibt unverändert ad-hoc beim Klick auf "Run workflow".
- **Kommentierung**: regelbasiert in `scripts/commentary.py` (Schwellenwerte in `config/config.json`).
- **Perioden-Cache** (`data_cache/`, seit 07/2026, Nutzerwunsch "nur offene Zeiträume ziehen"): Quellen mit Jahres-/Monats-Historie (Köln, Düsseldorf, Oldenburg, Moers, Dortmund-Fußgänger, Berlin-Telraam) überspringen abgeschlossene, bereits erfolgreich eingelesene Zeiträume komplett (kein Netzwerk-Call mehr) – nur die laufende, noch "offene" Periode wird bei jedem Lauf neu abgefragt. Jede erfolgreich gelesene Rohdatei wird zusätzlich unter `data_cache/<quelle>/<periode>/` archiviert und mit committet (schützt vor Datenverlust durch die `MAX_POINTS`-Kappung in `data.json` und macht den Datenstand reproduzierbar). Siehe `common.is_period_done()`/`mark_period_done()`/`cache_write()`.
- **Veraltete-Daten-Kennzeichnung**: Jede Karte/jeder KPI im Dashboard bekommt ein Warn-Badge ("⚠ Daten seit &lt;Jahr&gt; nicht aktualisiert"), wenn der neueste verfügbare Datenpunkt aus 2025 oder früher stammt (Kartenmarker werden zusätzlich grau/blass dargestellt) – so fallen eingestellte oder inaktive Quellen (z. B. Köln, das seit 2022 keine neuen Daten liefert) sofort auf. Schwelle in `docs/index.html` → `STALE_YEAR_CUTOFF`.

## Datenquellen je Frequenz

| Frequenz | Quelle | Ebene | Hinweis |
|---|---|---|---|
| täglich | Hystreet-Passantenfrequenzen | Standort | **deaktiviert per Default; nur manuell startbar, siehe COMPLIANCE.md** |
| täglich | Google Trends (pytrends) | Branche | inoffiziell, Index 0–100 |
| täglich | Radverkehr-Dauerzählstellen (BW, Hamburg, Leipzig, München, Rostock/Ostseeküste, Münster/Dortmund/Düsseldorf/Köln – NRW) | Region + Standort (Karte) | Näherungswert für Wegefrequenzen, **keine Fußgängerzahlen** – siehe COMPLIANCE.md Abschnitt 5 |
| täglich | Passantenfrequenzen – 8 Regionen (Oldenburg, Würzburg, Dortmund, Neuss, Bamberg, Augsburg, Moers, Berlin) | Region + Standort (eigener Tab) | echte Fußgängerzahlen; 6 Regionen lizenzrechtlich unkritisch, Bamberg/Augsburg mit dokumentiertem Restrisiko – siehe COMPLIANCE.md Abschnitt 6 |
| wöchentlich | Destatis Dashboard Deutschland (Tile-API) | Branche | dl-de/by-2-0 |
| wöchentlich | Pinterest Trends | Branche | **deaktiviert seit 07/2026** – Pinterest verlangt inzwischen ein Login für die Keyword-Suche, der inoffizielle Endpunkt liefert nur noch 404 |
| monatlich | GENESIS 45212-0001 (inkl. Versand-/Internethandel) | Branche | Secrets nötig |
| monatlich | Eurostat sts_trtu_m (G47, G47.71) | Branche | frei |
| monatlich | ifo-Geschäftsklima/-lage/-erwartungen (+ HDE/GfK-Konsum) | Branche | volle Historie seit 01/2005 direkt von ifo – **Nutzungsbedingungen-Restrisiko akzeptiert, siehe COMPLIANCE.md Abschnitt 7**; HDE/GfK weiterhin via Destatis-Dashboard-Tiles |
| quartalsweise | IR-Berichte (Zalando inkl. About You, Inditex, H&M) | **Konzern** | Zalando: ~30 KPIs inkl. Historie seit 2020 aus strukturierter XLSX (siehe unten); Inditex/H&M: einzelne KPIs per PDF-Regex, Inditex meist nur Link (JS-Seite) |

**Wichtig:** Bon-KPIs (Bonanzahl, Teile/Bon, Ø-Bonwert) je Standort/Outlet sind **nicht öffentlich verfügbar** (nur GfK/NIQ, EHI, BTE als Bezahl-Panels). Die Quartals-KPIs aus IR-Berichten sind Konzernwerte und werden im Dashboard/Newsletter entsprechend gekennzeichnet.

**Google-Trends-Tab:** Eigener Dashboard-Tab mit Frequenz-Umschalter (täglich/wöchentlich/monatlich/quartalsweise – aggregiert im Browser aus den täglichen Rohdaten), einem Gesamt-Index über alle ausgewählten Suchbegriffe (neu berechnet beim Ab-/Anwählen einzelner Begriffe) und Einzelkarten je Begriff. Suchbegriffe sind in `config.json → google_trends.keyword_groups` in drei Gruppen organisiert: Online-Handel (Zalando, Zara, H&M), Modemarken Midprice (camel active, PME Legend, Marco Polo, Strellson, Windsor, Gerry Weber, s.Oliver, Tom Tailor) und Artikel-Oberkategorien (Jacke, Hose, T-Shirt, Kleid, Pullover, Mantel, Rock, Sneaker, Abendkleid) – frei erweiterbar, pytrends batcht automatisch in 5er-Gruppen.

**Zalando-IR-Extraktion (XLSX statt PDF-Regex):** Zalando veröffentlicht pro Quartal eine strukturierte Excel-Datei („Financials XLS") mit der kompletten Kennzahlenhistorie seit Q1/2020 – deutlich zuverlässiger als Text aus dem PDF zu regexen. `scripts/sources/ir_reports.py` findet den aktuellen Download-Link über das stabile `title`-Attribut auf der IR-Seite (z. B. „Q1 2026 Financials XLS"), liest die Sheets „1_Group key figures" und „4_Segment performance" (B2C/B2B/Reconciliation) und legt daraus ca. 34 Serien an – u. a. GMV, aktive Kunden, Ø-Bestellungen/Ø-Warenkorb je aktivem Kunden, Adjusted-EBIT(-Marge), EBIT(-Marge) je Segment, Cashflows, Mitarbeiterzahl, EPS. Margin-Zeilen werden automatisch in Prozentpunkte umgerechnet. Inditex und H&M liefern keine vergleichbare strukturierte Datei; für sie bleibt der bisherige PDF-Regex-Fallback (`kpi_patterns` in `config.json`) aktiv, meist nur der aktuelle Quartalswert. Konfiguration je Unternehmen in `config.json → ir_reports.companies`: `financials_xlsx_title`/`xlsx_sheets` aktivieren den XLSX-Weg, sonst greift automatisch der PDF-Weg.

**Radverkehr als Frequenz-Proxy:** Nachdem Hystreet pausiert ist (siehe unten) und Destatis' Passantenfrequenz-Erhebung zum 31.12.2025 eingestellt wurde, nutzt das Dashboard ersatzweise offene Fahrrad-Dauerzählstellen aus 9 Regionen (Baden-Württemberg, Hamburg, Leipzig, München, Rostock/Ostseeküste, sowie Münster, Dortmund, Düsseldorf und Köln in NRW) als groben, deutschlandweiten Tendenz-Indikator für Wegefrequenzen – **ausdrücklich keine Fußgängerzahlen**. Der Dashboard-Tab „Karte (Radverkehr)" bündelt alles Radverkehr-Bezogene an einer Stelle: ganz oben ein Gesamt-Index mit Vorjahresvergleich (umschaltbar wöchentlich/monatlich/quartalsweise), darunter die Deutschlandkarte (Leaflet/OpenStreetMap), darunter alle Einzelstandorte mit eigenem Wert + Vorjahresvergleich. In den normalen Frequenz-Reitern (täglich/wöchentlich/monatlich/quartalsweise) tauchen die Radverkehr-Regionswerte bewusst nicht mehr auf. Weitere Regionen lassen sich in `config.json → radverkehr.regions` + einer neuen `_fetch_<region>()`-Funktion in `scripts/sources/radverkehr.py` ergänzen; Details zur Quellenprüfung in COMPLIANCE.md Abschnitt 5.

**NRW-Vollrecherche (07/2026):** Nach einer Anfrage, ob weitere NRW-Frequenzzähler (open.nrw listet sehr viele) bereits erfasst sind, wurden alle auffindbaren NRW-Portale einzeln auf Lizenz und tatsächliche Messwert-Verfügbarkeit geprüft. Neu aufgenommen: **Dortmund** (Zählstelle Schnettkerbrücke, DL-DE-Zero-2.0, Live-Daten seit 2018 über die open-data.dortmund.de-API), **Düsseldorf** (23 Zählstellen, DL-DE-BY-2.0, stündliche wetterannotierte Jahresarchive, aktuell + Vorjahr werden geladen) und **Köln** (17 Zählstellen, DL-DE-Zero-2.0, Monatssummen – **Datenstand seit 2022 nicht mehr aktualisiert**, aber offen lizenziert und daher trotzdem aufgenommen). **Bochum** bleibt bewusst ausgeschlossen: die Stadt lizenziert ihre Eco-Counter-Daten explizit als "andere/geschlossene Lizenz" mit einer Klausel gegen Weiterverbreitung. Wuppertal, Kreis Viersen, Rhein-Kreis-Neuss und das GEOportal.NRW wurden ebenfalls geprüft, bieten aber keine eigenen offen lizenzierten Messwert-Datensätze (nur Infrastruktur-/Planungsdaten oder Standort-Metadaten ohne Zählwerte) und wurden daher nicht aufgenommen.

**Norddeutschland/Küsten-Recherche (07/2026):** Auf Hinweis, dass Norddeutschland/die Küste in der Karte unterrepräsentiert ist, wurden Schleswig-Holstein, Niedersachsen, Mecklenburg-Vorpommern, Bremen und diverse Küstenstädte geprüft. Neu aufgenommen: **Rostock** (11 Zählstellen an der Ostseeküste, u.a. Warnemünde, Graal-Müritz, Markgrafenheide; CC0-1.0). Technischer Sonderfall: Die Rostocker Datenquelle ist eine einzelne, seit 2013 wachsende CSV (aktuell 150+ MB), daher lädt `_fetch_rostock()` nur die letzten ~30 MB per HTTP-Range-Request statt die komplette Datei. Bremen wurde geprüft, aber ohne erkennbare offizielle Open-Data-Lizenz nicht aufgenommen; für Kiel, Lübeck, Flensburg, Sylt, Wilhelmshaven und Cuxhaven wurden keine eigenen offenen Messwert-Datensätze gefunden.

**Echte Fußgängerdaten – Passantenfrequenzen aus 6 Städten:** Bei der Küsten-Recherche zusätzlich gefunden: Die Stadt Oldenburg veröffentlicht ihre eigenen Hystreet-Sensordaten (4 Innenstadt-Zählstellen, tagesgenau seit 2020) offen unter dl-de/by-2-0 auf ihrem eigenen Open-Data-Portal – eine andere rechtliche Situation als der direkte Hystreet-Zugriff (siehe COMPLIANCE.md Abschnitt 6). Auf Nutzerwunsch ("Ich brauche noch mehr Frequenzdaten") folgte 07/2026 eine bundesweite Nachrecherche über govdata.de/Mobilithek/open.bydata.de, die fünf weitere Städte mit eigener, unabhängiger Zählsensorik ergab: **Würzburg** (3 Standorte, Laserscanner, dl-de/by-2.0), **Dortmund** (3 Standorte "Westenhellweg", dl-de/zero-2.0, hier ab 2024 geladen), **Neuss** (11 BLE-Sensoren "Puls der Stadt", CC-BY-4.0, erst seit 06/2026), sowie **Bamberg** (26 Standorte, Ariadne-Maps-Sensorik seit 10/2024) und **Augsburg** (Annastraße, seit 12/2020) – letztere zwei ohne explizite Standard-Open-Data-Lizenz im Metadatensatz, auf Nutzerentscheidung trotzdem eingebunden mit dokumentiertem Restrisiko (siehe COMPLIANCE.md Abschnitt 6.2). Geprüft und ausgeschlossen: Bonn/Münster/Berlin (deren "Open Data"-Einträge verweisen nur auf die registrierungspflichtige hystreet.com-Plattform, keine echte Weiterveröffentlichung durch die Stadt) sowie Braunschweig (Messung seit Ende 2022 eingestellt).

Der Dashboard-Tab „Fußgänger" ist analog zu „Karte (Radverkehr)" als Multi-Regionen-Ansicht aufgebaut: Gesamt-Kettenindex über alle 6 Städte (Basis 100, geometrisches Mittel wie beim Radverkehr-Index, siehe unten), Deutschlandkarte mit Städte-Farbcodierung, darunter alle Einzelstandorte mit Regions-Badge, eigenem Wert und Vorjahresvergleich. Modul `scripts/sources/fussgaenger.py` mit `REGION_FETCHERS`-Struktur (ein Fetcher je Stadt, gleiches Muster wie `radverkehr.py`), Konfiguration in `config.json → fussgaenger.regions`.

## Einrichtung

1. Repo auf GitHub anlegen (öffentlich), diesen Ordner pushen.
2. **Pages aktivieren**: Settings → Pages → Deploy from branch → `main` + `/docs`.
3. `config/config.json` → `dashboard_url` auf die Pages-URL setzen.
4. **Secrets** (Settings → Secrets and variables → Actions → Secrets):
   - `GENESIS_USER` / `GENESIS_PASS` – kostenloser GENESIS-Account (destatis.de)
   - `GMAIL_ADDRESS` – deine Gmail-Adresse (Absender)
   - `GMAIL_APP_PASSWORD` – App-Passwort aus den Google-Konto-Sicherheitseinstellungen (myaccount.google.com/apppasswords; benötigt aktive 2-Faktor-Authentifizierung, **nicht** dein normales Gmail-Passwort)
   - `NEWSLETTER_TO` – Empfänger, kommagetrennt (i.d.R. deine eigene Adresse)
   - `HYSTREET_API_KEY` – **erst nach Compliance-Freigabe** (siehe COMPLIANCE.md)
5. **Variablen** (… → Variables):
   - `NEWSLETTER_ENABLED` = `true` (erst nach Freigabe-Checkliste in COMPLIANCE.md)
6. Erster Testlauf: Actions → „Täglicher KPI-Lauf" → *Run workflow*.
7. Hystreet (optional, nur nach Prüfung von COMPLIANCE.md): `config.json → hystreet.enabled=true` + `location_ids` eintragen, Secret `HYSTREET_API_KEY` hinterlegen. Danach startest du Aktualisierungen ausschließlich manuell über Actions → „Hystreet manuell (Passantenfrequenzen)" → *Run workflow* (optional mit Newsletter-Versand) oder lokal.
8. **Hystreet-Historie nachladen (einmaliger Backfill):** Beim manuellen Start über Actions kannst du im Feld „backfill_from" ein Startdatum eintragen (z. B. `2024-01-01`), um mehrjährige Vorjahresvergleiche zu ermöglichen. Das Script lädt dann die komplette Historie ab diesem Datum in 366-Tage-Blöcken pro Standort nach (bei 49 Standorten und `2024-01-01` sind das rund 150 Anfragen – dauert einige Minuten, läuft aber in einem Durchgang). Ohne Angabe werden wie gewohnt nur die letzten 8 Tage aktualisiert. Lokal äquivalent: `HYSTREET_BACKFILL_FROM=2024-01-01 python scripts/run_hystreet.py`.
9. **Google-Trends-Historie nachladen (einmaliger Backfill):** Normalbetrieb holt bei Google Trends nur die letzten 30 Tage (aus einem 3-Monats-Fenster) – die Serie wächst sonst erst ab jetzt Tag für Tag. Für Vorjahresvergleiche beim manuellen Start des „Täglicher KPI-Lauf"-Workflows das Feld „gtrends_backfill_timeframe" (z. B. `today 5-y` – jeder von pytrends akzeptierte Wert) füllen. Lokal äquivalent: `GTRENDS_BACKFILL_TIMEFRAME="today 5-y" python scripts/run_update.py daily`. Hinweis zu Google Trends: Für Zeiträume über ca. 9 Monate liefert Google automatisch wöchentliche statt tägliche Werte (der 0-100-Index ist nur innerhalb einer einzelnen Anfrage vergleichbar, deshalb wird bewusst nicht in Tages-Chunks aufgeteilt).

## Lokal testen

```bash
pip install -r requirements.txt
python scripts/run_update.py daily      # bzw. weekly / monthly / quarterly
python scripts/run_hystreet.py          # nur Hystreet, manuell, siehe COMPLIANCE.md
python scripts/newsletter.py daily      # schreibt newsletter_daily_preview.html; versendet nur mit GMAIL_ADDRESS + GMAIL_APP_PASSWORD
```

## Struktur

```
config/config.json          Keywords, Ticker, Tabellen, Schwellen, Feature-Gates
scripts/run_update.py       Einstiegspunkt je Frequenz (ohne Hystreet)
scripts/run_hystreet.py     separater, nur manuell gestarteter Hystreet-Lauf
scripts/sources/            ein Modul pro Datenquelle, je einzeln abgesichert (inkl. radverkehr.py, 5 Regionen)
scripts/commentary.py       regelbasierte Kommentierung
scripts/newsletter.py       HTML-Newsletter + Gmail-SMTP-Versand (privat)
docs/index.html             Dashboard (Chart.js + Leaflet-Kartenansicht), liest docs/data.json
docs/data.json               Datenbasis (von Actions committet)
.github/workflows/          daily / weekly / monthly / quarterly / hystreet-manual (kein Cron)
COMPLIANCE.md                Lizenz-/AGB-Zusammenfassung + Freigabe-Checkliste
```

## Fehlerbehandlung

Jede Quelle ist einzeln gekapselt: Fällt eine aus, läuft der Rest weiter. Fehler landen in `data.json → errors.<frequenz>` und werden auf der Website als Hinweisbox angezeigt.
