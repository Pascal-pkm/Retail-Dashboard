# Retail-KPI-Dashboard (Mode & Einzelhandel)

Sammelt öffentliche Retail-/Mode-Branchen-KPIs in vier Frequenzen (täglich, wöchentlich, monatlich, quartalsweise), zeigt sie auf einer GitHub-Pages-Website und versendet kommentierte Newsletter.

## Architektur

- **Kein Backend**: statische Website (`docs/`), Datenbasis ist `docs/data.json`.
- **GitHub Actions** (`.github/workflows/`) mit vier Cron-Schedules (täglich/wöchentlich/monatlich/quartalsweise) aktualisieren `data.json` und committen es.
- **Hystreet läuft separat, ausschließlich manuell**: eigener Workflow `hystreet-manual.yml` **ohne** Cron-Trigger — nur per „Run workflow"-Knopf im Actions-Tab oder lokal via `python scripts/run_hystreet.py`. Grund: die hystreet-AGB stehen einem automatisierten Dauerbetrieb entgegen, siehe COMPLIANCE.md.
- **GitHub Pages** hostet `docs/` (Settings → Pages → Branch `main`, Ordner `/docs`).
- **Newsletter** über Gmail SMTP (App-Passwort) — rein privat an die in `NEWSLETTER_TO` hinterlegte(n) eigene(n) Adresse(n), ausgelöst am Ende jedes Cron-Laufs sowie optional beim manuellen Hystreet-Lauf; nur wenn Repo-Variable `NEWSLETTER_ENABLED=true`.
- **Kommentierung**: regelbasiert in `scripts/commentary.py` (Schwellenwerte in `config/config.json`).

## Datenquellen je Frequenz

| Frequenz | Quelle | Ebene | Hinweis |
|---|---|---|---|
| täglich | Hystreet-Passantenfrequenzen | Standort | **deaktiviert per Default; nur manuell startbar, siehe COMPLIANCE.md** |
| täglich | Google Trends (pytrends) | Branche | inoffiziell, Index 0–100 |
| täglich | Aktienkurse (yfinance/Stooq) | Konzern | Zalando, adidas, Puma, Inditex, H&M (About You seit 2025 Teil von Zalando, Ticker delisted) |
| täglich | Radverkehr-Dauerzählstellen (BW, Hamburg, Leipzig, München, Münster/NRW) | Region + Standort (Karte) | Näherungswert für Wegefrequenzen, **keine Fußgängerzahlen** – siehe COMPLIANCE.md Abschnitt 5 |
| wöchentlich | Destatis Dashboard Deutschland (Tile-API) | Branche | dl-de/by-2-0 |
| wöchentlich | Pinterest Trends | Branche | **deaktiviert seit 07/2026** – Pinterest verlangt inzwischen ein Login für die Keyword-Suche, der inoffizielle Endpunkt liefert nur noch 404 |
| monatlich | GENESIS 45212-0001 (inkl. Versand-/Internethandel) | Branche | Secrets nötig |
| monatlich | Eurostat sts_trtu_m (G47, G47.71) | Branche | frei |
| monatlich | ifo-Geschäftsklima + HDE/GfK-Konsum | Branche | absolute Werte via Destatis-Dashboard-Tiles (verifiziert) |
| quartalsweise | IR-Berichte (Zalando inkl. About You, Inditex, H&M) | **Konzern** | Zalando: ~30 KPIs inkl. Historie seit 2020 aus strukturierter XLSX (siehe unten); Inditex/H&M: einzelne KPIs per PDF-Regex, Inditex meist nur Link (JS-Seite) |

**Wichtig:** Bon-KPIs (Bonanzahl, Teile/Bon, Ø-Bonwert) je Standort/Outlet sind **nicht öffentlich verfügbar** (nur GfK/NIQ, EHI, BTE als Bezahl-Panels). Die Quartals-KPIs aus IR-Berichten sind Konzernwerte und werden im Dashboard/Newsletter entsprechend gekennzeichnet.

**Google-Trends-Tab:** Eigener Dashboard-Tab mit Frequenz-Umschalter (täglich/wöchentlich/monatlich/quartalsweise – aggregiert im Browser aus den täglichen Rohdaten), einem Gesamt-Index über alle ausgewählten Suchbegriffe (neu berechnet beim Ab-/Anwählen einzelner Begriffe) und Einzelkarten je Begriff. Suchbegriffe sind in `config.json → google_trends.keyword_groups` in drei Gruppen organisiert: Online-Handel (Zalando, Zara, H&M), Modemarken Midprice (camel active, PME Legend, Marco Polo, Strellson, Windsor, Gerry Weber, s.Oliver, Tom Tailor) und Artikel-Oberkategorien (Jacke, Hose, T-Shirt, Kleid, Pullover, Mantel, Rock, Sneaker, Abendkleid) – frei erweiterbar, pytrends batcht automatisch in 5er-Gruppen.

**Zalando-IR-Extraktion (XLSX statt PDF-Regex):** Zalando veröffentlicht pro Quartal eine strukturierte Excel-Datei („Financials XLS") mit der kompletten Kennzahlenhistorie seit Q1/2020 – deutlich zuverlässiger als Text aus dem PDF zu regexen. `scripts/sources/ir_reports.py` findet den aktuellen Download-Link über das stabile `title`-Attribut auf der IR-Seite (z. B. „Q1 2026 Financials XLS"), liest die Sheets „1_Group key figures" und „4_Segment performance" (B2C/B2B/Reconciliation) und legt daraus ca. 34 Serien an – u. a. GMV, aktive Kunden, Ø-Bestellungen/Ø-Warenkorb je aktivem Kunden, Adjusted-EBIT(-Marge), EBIT(-Marge) je Segment, Cashflows, Mitarbeiterzahl, EPS. Margin-Zeilen werden automatisch in Prozentpunkte umgerechnet. Inditex und H&M liefern keine vergleichbare strukturierte Datei; für sie bleibt der bisherige PDF-Regex-Fallback (`kpi_patterns` in `config.json`) aktiv, meist nur der aktuelle Quartalswert. Konfiguration je Unternehmen in `config.json → ir_reports.companies`: `financials_xlsx_title`/`xlsx_sheets` aktivieren den XLSX-Weg, sonst greift automatisch der PDF-Weg.

**Radverkehr als Frequenz-Proxy:** Nachdem Hystreet pausiert ist (siehe unten) und Destatis' Passantenfrequenz-Erhebung zum 31.12.2025 eingestellt wurde, nutzt das Dashboard ersatzweise offene Fahrrad-Dauerzählstellen aus 5 Regionen (Baden-Württemberg, Hamburg, Leipzig, München, Münster/NRW) als groben, deutschlandweiten Tendenz-Indikator für Wegefrequenzen – **ausdrücklich keine Fußgängerzahlen**. Ein neuer Dashboard-Tab „Karte (Radverkehr)" zeigt alle Zählstellen auf einer Deutschlandkarte (Leaflet/OpenStreetMap), zusätzlich gibt es je Region eine Tagessummen-Serie im normalen Frequenz-Grid. Weitere Regionen lassen sich in `config.json → radverkehr.regions` + einer neuen `_fetch_<region>()`-Funktion in `scripts/sources/radverkehr.py` ergänzen; Details zur Quellenprüfung in COMPLIANCE.md Abschnitt 5.

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
9. **Google-Trends-/Aktien-Historie nachladen (einmaliger Backfill):** Normalbetrieb holt bei Google Trends nur die letzten 30 Tage (aus einem 3-Monats-Fenster) und bei Aktien nur die letzten 10 Handelstage – die Serien wachsen sonst erst ab jetzt Tag für Tag. Für Vorjahresvergleiche beim manuellen Start des „Täglicher KPI-Lauf"-Workflows die Felder „stocks_backfill_period" (z. B. `2y`, `5y`, `max` – jeder von yfinance akzeptierte Wert) und/oder „gtrends_backfill_timeframe" (z. B. `today 5-y` – jeder von pytrends akzeptierte Wert) füllen. Beide Felder sind unabhängig voneinander nutzbar und laufen in einem einzelnen Durchgang. Lokal äquivalent: `STOCKS_BACKFILL_PERIOD=2y GTRENDS_BACKFILL_TIMEFRAME="today 5-y" python scripts/run_update.py daily`. Hinweis zu Google Trends: Für Zeiträume über ca. 9 Monate liefert Google automatisch wöchentliche statt tägliche Werte (der 0-100-Index ist nur innerhalb einer einzelnen Anfrage vergleichbar, deshalb wird bewusst nicht in Tages-Chunks aufgeteilt).

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
