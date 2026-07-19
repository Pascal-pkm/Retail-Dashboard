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
- **Pinterest Trends:** kein offizielles API; Best-Effort-Scraper, ToS-Grauzone. **Seit 07/2026 deaktiviert** (`pinterest_trends.enabled=false`): Pinterest verlangt für die Keyword-Suche jetzt ein Login (per Browser verifiziert – die Suche leitet sofort auf ein Anmelden/Registrieren-Modal um, kein Such-Request feuert mehr unauthentifiziert). Der bisher genutzte interne Endpunkt liefert nur noch 404. Da wir bewusst keine Konten anlegen oder Logins automatisieren, bleibt die Quelle deaktiviert, bis es einen offiziellen, oeffentlichen Zugang gibt.
- **Aktienkurse (Yahoo/Stooq):** nur zur Information, kein Weitervertrieb der Rohdaten.
- **ifo (Fallback-Weg):** Falls der direkte ifo-Abruf scheitert (siehe Abschnitt 7), greift ersatzweise die Kennzahl aus der öffentlichen Destatis-Pressemitteilung mit Quellenangabe (Zitatrecht/Pressemitteilungscharakter); keine Vervielfältigung ganzer Publikationen.
- **IR-Berichte:** öffentliche Pflichtveröffentlichungen; wir speichern Links + einzelne Kennzahlen mit Quellenangabe, keine PDF-/XLSX-Weiterverbreitung. Bei Zalando werden seit 07/2026 rein numerische Kennzahlen (keine Formatierung, Kommentare oder Layout) aus der öffentlich zum Download bereitgestellten „Financials XLS" strukturiert ausgelesen (statt einzelner Werte per PDF-Text-Regex) – die Rohdatei selbst wird nicht gespeichert oder veröffentlicht, nur die extrahierten Zahlen mit Link zur offiziellen Quelle.

## 5. Radverkehr-Dauerzählstellen (9 Regionen, Stand 07/2026) — ✅ unkritisch, Lizenz je Region geprüft

Nutzerentscheidung 2026-07: Da Hystreet pausiert ist und Destatis' eigene Passantenfrequenz-Erhebung zum 31.12.2025 eingestellt wurde, wird als bundesweiter **Näherungswert** (ausdrücklich KEINE Fußgängerzahlen) auf offene Fahrrad-Dauerzählstellen zurückgegriffen. Alle neun verwendeten Regionen wurden einzeln auf Format und Lizenz geprüft:

| Region | Quelle | Lizenz |
|---|---|---|
| Baden-Württemberg | MobiData BW (mobidata-bw.de) | dl-de/by-2.0 |
| Hamburg | Transparenzportal Hamburg / api.hamburg.de | dl-de/by-2.0 |
| Leipzig | Open Data Portal Leipzig (Geodienste) | dl-de/by-2.0 |
| München | Open Data Portal München (CKAN + Geoportal) | dl-de/by-2.0 |
| Münster (NRW) | opendata.stadt-muenster.de / GitHub-Repo od-ms | dl-de/by-2.0 |
| Dortmund (NRW) | open-data.dortmund.de (OpenDataSoft-API) | **dl-de/zero-2.0** |
| Düsseldorf (NRW) | opendata.duesseldorf.de | dl-de/by-2.0 |
| Köln (NRW) | offenedaten-koeln.de | **dl-de/zero-2.0** |
| Rostock (Ostseeküste) | opendata-hro.de / geo.sv.rostock.de | **CC0 1.0** |

Sieben der neun stehen unter der **Datenlizenz Deutschland – Namensnennung – 2.0** (identisch zu Destatis/Eurostat, siehe oben): Vervielfältigung, Verbreitung, Veröffentlichung und kommerzielle Nutzung sind mit Quellenvermerk ausdrücklich erlaubt. Dortmund und Köln stehen unter der noch offeneren **Datenlizenz Deutschland – Zero – 2.0**, Rostock sogar unter **Creative Commons CC0 1.0** (beides public-domain-äquivalent, nicht einmal Namensnennung ist Pflicht, wird im Dashboard aber trotzdem angezeigt). Keine der neun Quellen hat ein Hystreet-artiges Verbot automatisierter Abfrage; alle sind als offene Maschinen-Downloads (CSV/GeoJSON/API) konzipiert. Quellenvermerk je Region ist im Dashboard bei jeder Kennzahl/jedem Kartenmarker verlinkt.

**Norddeutschland/Küsten-Recherche 2026-07 (Nutzeranfrage: „Norddeutschland scheint unterrepräsentiert, die Küste ist interessant").** Geprüft wurden Schleswig-Holstein, Niedersachsen, Mecklenburg-Vorpommern, Bremen sowie die Städte Kiel, Lübeck, Rostock, Flensburg, Wilhelmshaven, Cuxhaven und Sylt/Nordfriesland. Ergebnis:

- **Rostock**: neu aufgenommen. 11 Zählstellen, CC0-1.0, darunter explizit Ostseeküsten-/Badeort-Standorte (Warnemünde Wetterwarte, Markgrafenheide, Graal-Müritz). Technischer Sonderfall: Die Datenquelle ist eine einzelne, seit 11/2013 fortlaufend wachsende CSV-Datei (Stand 07/2026: 154 MB, 15-Minuten-Werte). Ein täglicher Komplett-Download wäre unpraktikabel; `_fetch_rostock()` lädt daher nur die letzten ~30 MB der Datei per HTTP-Range-Request (`ROSTOCK_TAIL_BYTES`), mit einem clientseitigen Sicherheitsnetz falls ein Proxy/Server den Range-Header ignoriert und trotzdem die komplette Datei liefert.
- **Bremen**: geprüft (12 Zählstellen seit 2012, sichtbar über die VMZ-Webseite), aber **keine offizielle Open-Data-Lizenz gefunden** — nur ein Blogbeitrag, der die Daten ohne Beschreibung des Zugriffswegs von der VMZ-Webseite bezogen hat. Ohne erkennbare Lizenz analog zu Bochum nicht aufgenommen.
- **Kiel, Lübeck, Flensburg, Sylt/Nordfriesland, Wilhelmshaven, Cuxhaven**: keine eigenen offen lizenzierten Radverkehrs-Messwert-Datensätze gefunden (Kiel bleibt weiterhin nur über die in Abschnitt 5 unten beschriebene Mobilithek-Organisationsregistrierung erreichbar).

**NRW-Vollrecherche 2026-07 (Nutzeranfrage: „Werden diese ganzen Frequenzen auch schon gezählt? Open NRW hat sehr viele Frequenzzähler").** Da Open.NRW/govdata.de deutlich mehr NRW-Radverkehrszähler listet als nur Münster, wurden systematisch geprüft: Bochum, Dortmund, Düsseldorf, Köln, Wuppertal, Kreis Viersen, Rhein-Kreis-Neuss und das GEOportal.NRW. Ergebnis:

- **Dortmund, Düsseldorf, Köln**: offen lizenziert (siehe Tabelle oben) und mit tatsächlich abrufbaren Messwerten (nicht nur Standort-Metadaten) — neu aufgenommen.
- **Bochum**: explizit ausgeschlossen. Die Eco-Counter-Ressourcen der Stadt sind mit `http://dcat-ap.de/def/licenses/other-closed` lizenziert; die Stadt verweist auf das Eigentum von Eco-Counter an den Rohdaten und untersagt eine Weiterverbreitung/konkurrierende Nutzung. Wichtig: Eco-Counter-Hardware allein ist **kein** Ausschlussgrund (Dortmund und Düsseldorf nutzen teils dieselbe Hardware, veröffentlichen ihre Auswertungen aber unter eigener offener Lizenz) — jede Stadt muss einzeln anhand ihrer eigenen Distributions-Lizenz geprüft werden, nicht pauschal nach Hersteller.
- **Wuppertal, Kreis Viersen, Rhein-Kreis-Neuss, GEOportal.NRW**: geprüft, aber keine eigenen offen lizenzierten Messwert-Datensätze gefunden (nur Infrastruktur-/Planungsdaten wie Radwege/Radrouten/Einbahnstraßen-Ausnahmen, oder bei Rhein-Kreis-Neuss nur eine Standort-Liste ohne Zählwerte) — nicht aufgenommen. Bei Bedarf später erneut prüfbar, falls diese Portale neue Datensätze veröffentlichen.

**Sonderfall Köln — veraltete Daten trotz offener Lizenz.** Der Kölner Datensatz „Fahrrad Verkehrsdaten Köln" liegt nur als Jahres-CSV mit Monatssummen vor und wird seit dem Jahrgang 2022 nicht mehr aktualisiert (Stand 07/2026, letzter geprüfter Abruf: Jahrgänge 2016–2022 verfügbar, 2023/2024/2025 existieren nicht). Da die Lizenz (DL-DE-Zero-2.0) unkritisch ist, wird die Quelle trotzdem eingebunden — die Serie im Dashboard bleibt einfach stehen, bis (falls überhaupt) neue Jahrgänge erscheinen; `radverkehr.py` prüft bei jedem Lauf automatisch, ob ein neuerer Jahrgang veröffentlicht wurde.

**Verbindungs-Timeouts bei Düsseldorf/Köln (07/2026, behoben).** Im täglichen Lauf traten gehäuft Connection-Timeouts gegen opendata.duesseldorf.de und offenedaten-koeln.de auf (vermutlich Rate-Limiting der kleinen Stadtportale bei ~20-45 schnell aufeinanderfolgenden Anfragen aus der GitHub-Actions-IP-Range). Behoben durch kleine Pausen zwischen den Requests (0.3-0.4s) plus einen zusätzlichen Retry-Versuch je Anfrage in `_fetch_duesseldorf()`/`_fetch_koeln()`.

**Sonderfall Düsseldorf — Jahresarchiv statt Live-Daten.** Die „Wetterabhängige Jahresübersicht" erscheint als vollständige Jahresdatei erst ca. 6 Monate nach Jahresende (2025er-Daten seit ca. 06/2026 verfügbar, 2026er-Daten entsprechend erst ab ca. Mitte 2027). `_fetch_duesseldorf()` lädt bei jedem täglichen Lauf das aktuelle + das vorherige Jahr neu (kleine CSV-Dateien, unproblematisch); die Region-Summenserie bleibt zwischen den jährlichen Updates einfach auf dem letzten Stand.

**Bewusst ausgeklammert: Kiel/Schleswig-Holstein.** Der Datensatz „Zählwerte Radverkehrszähler (Radzählstationen) Kiel" (Anbieter: KielRegion GmbH, Lizenz frei/Open Data, 6 Standorte, tägliche Werte) existiert in der Mobilithek (bundesweiter Mobilitätsdaten-Marktplatz) und ist inhaltlich lizenzrechtlich unkritisch. Der Zugriff erfordert aber mehr als einen persönlichen Account: Man muss als „Bestellmanager" eine **Organisation** bei der Mobilithek registrieren (Formular mit Organisationsname/-typ, Adresse, vertretungsberechtigter Person), bevor überhaupt ein „Abonnieren"-Button für das Angebot erscheint (Stand: 18.07.2026, mit registriertem Nutzeraccount geprüft, ID `995322152055894016`). Auf Nutzerentscheidung daher vorerst weiterhin nicht eingebunden. Falls die Organisation später registriert und das Abonnement freigeschaltet wird, kann Kiel als weitere Region ergänzt werden (`scripts/sources/radverkehr.py` ist dafür bewusst pro Region erweiterbar aufgebaut) – dazu wird vermutlich ein API-Key/Endpoint aus dem Mobilithek-Abonnement benötigt, der als GitHub-Secret hinterlegt würde.

## 6. Passantenfrequenzen Oldenburg (`fussgaenger.py`) — ✅ unkritisch, andere rechtliche Situation als Hystreet direkt

Nutzeranfrage 2026-07: Nachdem festgestellt wurde, dass Norddeutschland/die Küste bei den Radverkehrsdaten unterrepräsentiert ist, wurde nach weiteren Frequenz-Quellen gesucht. Dabei aufgetaucht: Die Stadt Oldenburg lässt seit 11/2019 durch die Firma **Hystreet** (siehe Abschnitt 1) Laserscanner-Passantenzähler in ihrer Innenstadt betreiben — mittlerweile 4 Standorte (Achternstraße, Haarenstraße, Haarenstraße Ost, Lange Straße) — und veröffentlicht die eigenen Messwerte als Jahres-CSV auf ihrem eigenen Open-Data-Portal (opendata.oldenburg.de) unter der **Datenlizenz Deutschland – Namensnennung – 2.0**.

**Warum das rechtlich anders zu bewerten ist als der direkte Hystreet-Zugriff (Abschnitt 1):** Hystreets eigene AGB (Ziff. 8.1.2/8.1.3) verbieten NUTZERN des Hystreet-Portals/der Hystreet-API die Veröffentlichung der über den API-Zugang bezogenen Daten ohne gesonderte Zustimmung. Hier greift dieses Projekt aber nicht auf Hystreets API zu — es lädt eine CSV-Datei, die die **Stadt Oldenburg als Auftraggeberin** der Messung auf ihrem eigenen Server unter einer eigenen, offenen Lizenz bereitstellt. Die Stadt ist in diesem Fall die Instanz, die über die Veröffentlichung ihrer eigenen erhobenen Daten entscheidet, und hat sich dafür sichtbar entschieden (eigener Open-Data-Datensatz, DCAT-Metadaten, öffentlich dokumentiert). Es gibt keinen Hinweis darauf, dass die Stadt dabei gegen einen eigenen Vertrag mit Hystreet verstößt — im Gegenteil, viele Kommunen lassen sich das Recht zur offenen Weiterveröffentlichung der eigenen Messwerte vertraglich zusichern, wenn sie einen Zähldienstleister beauftragen (vergleichbar mit dem bereits im Projekt etablierten Muster bei Eco-Counter-Zählstellen: Dortmund/Düsseldorf veröffentlichen ihre Eco-Counter-Auswertungen offen, obwohl Bochum das für seine eigenen Eco-Counter-Daten explizit untersagt — die Entscheidung liegt jeweils bei der Kommune, nicht beim Hardware-/Messdienstleister).

**Einordnung:** kein Restrisiko-Fall wie ifo (Abschnitt 7) oder der direkte Hystreet-Zugriff, sondern ein regulärer offen lizenzierter Datensatz — wird daher ohne gesonderte Nutzerentscheidung eingebunden. Datenstand: Jahresarchiv (DCAT `frequency=ANNUAL`), 2020–2025 verfügbar (Stand 07/2026, 2026er-Jahrgang erscheint erst nach Jahresende), `fussgaenger.py` lädt bei jedem Lauf automatisch aktuelles + Vorjahr.

## 7. ifo Institut — direkte ifo-Zeitreihen (Geschäftsklima/-lage/-erwartungen) — ⚠️ Restrisiko akzeptiert

Seit 07/2026 lädt `scripts/sources/ifo_hde.py` primär die von ifo direkt bereitgestellte Excel-Zeitreihe unter ifo.de/ifo-zeitreihen (kompletter Monatsverlauf seit 01/2005, statt nur des Werts aus dem Destatis-Pressetext). Der Download-Bereich verlinkt als Nutzungsbedingung die Seite „Bestellinformationen für ifo Zeitreihen", die wörtlich sagt:

> „Die Nutzung der Daten ist nur zur privaten Information zulässig. Die Weitergabe bzw. Veröffentlichung ist nur nach besonderer Vereinbarung mit dem ifo Institut gestattet."

Das steht im direkten Widerspruch zu einer öffentlichen GitHub-Pages-Seite — inhaltlich dieselbe Art von Einschränkung wie bei Hystreet (Abschnitt 1), nur ohne die dort explizit genannte Vertragsstrafe. Geprüft am 19.07.2026 per Browser (Cookie-Banner akzeptiert, Seite direkt aufgerufen).

**Nutzerentscheidung 2026-07-19:** Trotz dieser Einschränkung wird die Quelle für die öffentliche Website genutzt (Option „Restrisiko akzeptieren" bewusst gewählt, nachdem die Alternative — bei der stark eingeschränkten Destatis-Pressetext-Variante mit nur 1–2 Punkten pro Monat zu bleiben — als Ausweichoption angeboten wurde). Einschränkend umgesetzt:

- Es wird **nicht die Originaldatei** gespeichert oder verlinkt, nur einzelne extrahierte Zahlenwerte (Geschäftsklima, -lage, -erwartungen je Monat) mit Quellenangabe.
- Fällt der direkte Abruf aus (z. B. weil ifo den Zugang technisch einschränkt), greift automatisch der rechtlich unkritische Destatis-Fallback (Abschnitt 4).

Falls du dieses Restrisiko nachträglich vermeiden willst: (a) Rückkehr zum reinen Destatis-Fallback (in `ifo_hde.py` `_fetch_ifo_direct` deaktivieren/entfernen), oder (b) ifo Institut (Kontakt laut Zeitreihen-Seite: wohlrabe@ifo.de, sauer@ifo.de) um eine Vereinbarung für die Veröffentlichung bitten — analog zum Hystreet-Vorgehen.

## 8. Freigabe-Checkliste vor Produktivbetrieb

- [ ] Hystreet: bewusste Entscheidung getroffen (Zustimmung eingeholt ODER Restrisiko akzeptiert ODER Modul bleibt deaktiviert)
- [ ] ifo-Zeitreihen (Abschnitt 7): bewusste Entscheidung getroffen (Restrisiko akzeptiert ODER Rückkehr zum Destatis-Fallback ODER Zustimmung bei ifo eingeholt)
- [ ] Newsletter-Empfänger (`NEWSLETTER_TO`) geprüft — nur eigene, private Adresse(n) hinterlegt
- [ ] GENESIS-Zugang registriert, Secrets hinterlegt
- [ ] Quellenvermerke auf Website + Newsletter geprüft
- [ ] `NEWSLETTER_ENABLED`-Variable erst nach dieser Bestätigung auf `true` setzen
