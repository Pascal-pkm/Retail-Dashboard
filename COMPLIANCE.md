# Compliance: Nutzungsbedingungen & Lizenzen

Stand der Prüfung: 18.07.2026. **Vor dem ersten produktiven Lauf bitte die Freigabe-Checkliste unten bestätigen.**

## 1. Hystreet (hystreet.com/agb, Stand AGB: 03.06.2024) — ⚠️ KRITISCH

Die AGB des kostenlosen Angebots **„FREE"** (das über die kostenlose Registrierung inkl. API-Token erreichbar ist) enthalten Regelungen, die dem geplanten Setup **entgegenstehen**:

- **Nur private Nutzung durch Verbraucher** (§ 13 BGB). Bei nicht-privater Nutzung droht Mindestschaden i. H. der BASIC-Jahresgebühr (derzeit 6.000 € netto) (Ziff. 2.2).
- **Ziff. 8.1.5: „Die automatisierte Abfrage der hystreet.com-Datenbanken durch Roboter bzw. Softwaretools ist nicht gestattet."** Ein Cron-Job in GitHub Actions ist genau das.
- **Ziff. 8.1.2/8.1.3: Vervielfältigung, Verbreitung und jede Veröffentlichung** von Daten oder darauf basierenden Auswertungen zu nicht ausschließlich privaten Zwecken ist ohne **vorherige ausdrückliche Zustimmung** unzulässig — eine öffentliche GitHub-Pages-Seite und ein Newsletter sind Veröffentlichung/Verbreitung.
- Auch für wissenschaftliche/journalistische Verbreitung ist Zustimmung nötig (Ziff. 8.1.4).
- **Vertragsstrafe: 6.000 € je schuldhaftem Verstoß** (Ziff. 8.2).
- Hystreet ist Datenbankherstellerin nach § 87a UrhG; Quellenangabe „hystreet.com" ist bei jeder genehmigten Nutzung Pflicht.

**Konsequenz im Projekt:** Das Hystreet-Modul ist per Compliance-Gate **deaktiviert** (`config.json → hystreet.enabled=false`, zusätzlich fehlt das Secret). Es wird erst aktiviert, wenn du das bewusst entscheidest (siehe unten) — im Idealfall erst nach einer **schriftlichen Zustimmung von hystreet** (info@hystreet.com) für automatisierte API-Abfrage + Veröffentlichung auf der Dashboard-Seite/im Newsletter, oder mit einem entsprechenden kommerziellen/API-Vertrag. Die API-Doku und der kostenlose Test-Token (hystreet.com/developer) sind ausdrücklich als „Testen" beworben — für den Dauerbetrieb ist der Vertriebskontakt der richtige Weg.

**Architektur-Update (manueller Betrieb statt Cron):** Auf deinen Wunsch läuft der Hystreet-Abruf jetzt in einem eigenen Workflow **„Hystreet manuell"** (`.github/workflows/hystreet-manual.yml`) **ohne** `schedule:`-Trigger — er startet ausschließlich, wenn du im Actions-Tab auf „Run workflow" klickst (lokal alternativ: `python scripts/run_hystreet.py`). Das nimmt dem Betrieb den Dauerlauf-Charakter und gibt dir volle Kontrolle über Häufigkeit und Zeitpunkt. **Zwei AGB-Punkte bleiben davon aber unberührt und sind ein bewusst von dir akzeptiertes Restrisiko:**
- Ziff. 8.1.5 verbietet „automatisierte Abfrage ... durch Roboter bzw. Softwaretools" – das bezieht sich auf die Methode (ein Script ruft die API auf), nicht auf den Auslöser. Ob per Cron oder per Knopfdruck gestartet, technisch bleibt es ein Softwaretool statt manueller Browser-Nutzung.
- Ziff. 8.1.2/8.1.3 verbieten Veröffentlichung ohne Zustimmung. Repo und GitHub-Pages-Seite dieses Projekts sind **öffentlich**; landen Hystreet-Daten in `docs/data.json`, gelten sie als veröffentlicht — unabhängig davon, dass dein Newsletter privat bleibt.

**Historien-Backfill (2024–heute für Vorjahresvergleiche):** Der Workflow unterstützt optional einen einmaligen Backfill (Eingabefeld „backfill_from"), der pro Standort mehrere Anfragen in 366-Tage-Blöcken stellt (bei 49 Standorten ab 2024-01-01 rund 150 Anfragen in einem Durchgang, mit kurzer Pause zwischen den Requests). Das ist weiterhin ein einzelner, von dir manuell ausgelöster Lauf — aber ein deutlich höheres Anfragevolumen als das normale 8-Tage-Update. Die oben genannten Restrisiken (Ziff. 8.1.5, 8.1.2/8.1.3) gelten dafür unverändert bzw. verstärkt, da mehr Daten auf einmal abgefragt und veröffentlicht würden.

Falls du dieses Restrisiko vermeiden willst, sind die sauberen Alternativen: (a) das Repo/die Pages-Seite auf privat stellen, (b) Hystreet-Daten in eine nicht committete/private Datei statt `docs/data.json` schreiben lassen, oder (c) die Freigabe bei hystreet einholen. Sag Bescheid, falls einer dieser Wege gewünscht ist — aktuell ist bewusst Variante „öffentliches Repo, nur manuell statt automatisch" umgesetzt.

## 2. Destatis (GENESIS-Online & Dashboard Deutschland) — ✅ unkritisch mit Namensnennung

Beide stehen unter der **Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0)**:

- Vervielfältigung, Verbreitung, Veröffentlichung, Bearbeitung und **auch kommerzielle Nutzung sind ausdrücklich erlaubt**.
- Bedingung: **Quellenvermerk** (Bereitsteller „Statistisches Bundesamt (Destatis)", ggf. Tabelle/Datensatz, Datum) und **Verweis auf die Lizenz** (www.govdata.de/dl-de/by-2-0); bei bearbeiteten Daten Veränderungshinweis.
- GENESIS-Webservice erfordert eine kostenlose Registrierung (Zugangsdaten als Secrets `GENESIS_USER`/`GENESIS_PASS`).

Dashboard und Newsletter enthalten den Quellenvermerk inkl. Lizenzlink bereits im Footer.

## 3. Eurostat — ✅ unkritisch mit Namensnennung

Eurostat-Daten dürfen laut Eurostat-Lizenzpolitik (CC BY 4.0-basiert) frei weiterverwendet werden, auch kommerziell, mit Quellenangabe „Eurostat". Im Footer/Newsletter enthalten.

## 4. Übrige Quellen — Hinweise

- **Google Trends via pytrends:** inoffizielle Bibliothek, kein API-Vertrag; Werte sind relative Indizes. Ausfall-/Sperrrisiko einkalkuliert (Fehlerprotokoll statt Abbruch).
- **Pinterest Trends:** kein offizielles API; Best-Effort-Scraper, ToS-Grauzone. Auf Wunsch aktiviert (`pinterest_trends.enabled`), kann jederzeit deaktiviert werden.
- **Aktienkurse (Yahoo/Stooq):** nur zur Information, kein Weitervertrieb der Rohdaten.
- **ifo:** Kennzahl aus öffentlicher Pressemitteilung mit Quellenangabe (Zitatrecht/Pressemitteilungscharakter); keine Vervielfältigung ganzer Publikationen.
- **IR-Berichte:** öffentliche Pflichtveröffentlichungen; wir speichern Links + einzelne Kennzahlen mit Quellenangabe, keine PDF-/XLSX-Weiterverbreitung. Bei Zalando werden seit 07/2026 rein numerische Kennzahlen (keine Formatierung, Kommentare oder Layout) aus der öffentlich zum Download bereitgestellten „Financials XLS" strukturiert ausgelesen (statt einzelner Werte per PDF-Text-Regex) – die Rohdatei selbst wird nicht gespeichert oder veröffentlicht, nur die extrahierten Zahlen mit Link zur offiziellen Quelle.

## 5. Radverkehr-Dauerzählstellen (5 Regionen, Stand 07/2026) — ✅ unkritisch mit Namensnennung

Nutzerentscheidung 2026-07: Da Hystreet pausiert ist und Destatis' eigene Passantenfrequenz-Erhebung zum 31.12.2025 eingestellt wurde, wird als bundesweiter **Näherungswert** (ausdrücklich KEINE Fußgängerzahlen) auf offene Fahrrad-Dauerzählstellen zurückgegriffen. Alle fünf verwendeten Regionen wurden einzeln auf Format und Lizenz geprüft:

| Region | Quelle | Lizenz |
|---|---|---|
| Baden-Württemberg | MobiData BW (mobidata-bw.de) | dl-de/by-2.0 |
| Hamburg | Transparenzportal Hamburg / api.hamburg.de | dl-de/by-2.0 |
| Leipzig | Open Data Portal Leipzig (Geodienste) | dl-de/by-2.0 |
| München | Open Data Portal München (CKAN + Geoportal) | dl-de/by-2.0 |
| Münster (NRW) | opendata.stadt-muenster.de / GitHub-Repo od-ms | dl-de/by-2.0 |

Alle fünf stehen unter der **Datenlizenz Deutschland – Namensnennung – 2.0**, identisch zu Destatis/Eurostat (siehe oben): Vervielfältigung, Verbreitung, Veröffentlichung und kommerzielle Nutzung sind mit Quellenvermerk ausdrücklich erlaubt. Keine der fünf Quellen hat ein Hystreet-artiges Verbot automatisierter Abfrage; alle sind als offene Maschinen-Downloads (CSV/GeoJSON/API) konzipiert. Quellenvermerk je Region ist im Dashboard bei jeder Kennzahl/jedem Kartenmarker verlinkt.

**Bewusst ausgeklammert: Kiel/Schleswig-Holstein.** Der Datensatz „Zählwerte Radverkehrszähler (Radzählstationen) Kiel" (Anbieter: KielRegion GmbH, Lizenz frei/Open Data, 6 Standorte, tägliche Werte) existiert in der Mobilithek (bundesweiter Mobilitätsdaten-Marktplatz) und ist inhaltlich lizenzrechtlich unkritisch. Der Zugriff erfordert aber mehr als einen persönlichen Account: Man muss als „Bestellmanager" eine **Organisation** bei der Mobilithek registrieren (Formular mit Organisationsname/-typ, Adresse, vertretungsberechtigter Person), bevor überhaupt ein „Abonnieren"-Button für das Angebot erscheint (Stand: 18.07.2026, mit registriertem Nutzeraccount geprüft, ID `995322152055894016`). Auf Nutzerentscheidung daher vorerst weiterhin nicht eingebunden. Falls die Organisation später registriert und das Abonnement freigeschaltet wird, kann Kiel als sechste Region ergänzt werden (`scripts/sources/radverkehr.py` ist dafür bewusst pro Region erweiterbar aufgebaut) – dazu wird vermutlich ein API-Key/Endpoint aus dem Mobilithek-Abonnement benötigt, der als GitHub-Secret hinterlegt würde.

## 6. Freigabe-Checkliste vor Produktivbetrieb

- [ ] Hystreet: bewusste Entscheidung getroffen (Zustimmung eingeholt ODER Restrisiko akzeptiert ODER Modul bleibt deaktiviert)
- [ ] Newsletter-Empfänger (`NEWSLETTER_TO`) geprüft — nur eigene, private Adresse(n) hinterlegt
- [ ] GENESIS-Zugang registriert, Secrets hinterlegt
- [ ] Quellenvermerke auf Website + Newsletter geprüft
- [ ] `NEWSLETTER_ENABLED`-Variable erst nach dieser Bestätigung auf `true` setzen
