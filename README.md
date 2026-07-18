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
| wöchentlich | Destatis Dashboard Deutschland (Tile-API) | Branche | dl-de/by-2-0 |
| wöchentlich | Pinterest Trends | Branche | Best-Effort, experimentell |
| monatlich | GENESIS 45212-0001 (inkl. Versand-/Internethandel) | Branche | Secrets nötig |
| monatlich | Eurostat sts_trtu_m (G47, G47.71) | Branche | frei |
| monatlich | ifo-Geschäftsklima + HDE/GfK-Konsum | Branche | absolute Werte via Destatis-Dashboard-Tiles (verifiziert) |
| quartalsweise | IR-Berichte (Zalando inkl. About You, Inditex, H&M) | **Konzern** | GMV, aktive Kunden, AOV etc.; Inditex nur Link (JS-Seite) |

**Wichtig:** Bon-KPIs (Bonanzahl, Teile/Bon, Ø-Bonwert) je Standort/Outlet sind **nicht öffentlich verfügbar** (nur GfK/NIQ, EHI, BTE als Bezahl-Panels). Die Quartals-KPIs aus IR-Berichten sind Konzernwerte und werden im Dashboard/Newsletter entsprechend gekennzeichnet.

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
scripts/sources/            ein Modul pro Datenquelle, je einzeln abgesichert
scripts/commentary.py       regelbasierte Kommentierung
scripts/newsletter.py       HTML-Newsletter + Gmail-SMTP-Versand (privat)
docs/index.html             Dashboard (Chart.js), liest docs/data.json
docs/data.json               Datenbasis (von Actions committet)
.github/workflows/          daily / weekly / monthly / quarterly / hystreet-manual (kein Cron)
COMPLIANCE.md                Lizenz-/AGB-Zusammenfassung + Freigabe-Checkliste
```

## Fehlerbehandlung

Jede Quelle ist einzeln gekapselt: Fällt eine aus, läuft der Rest weiter. Fehler landen in `data.json → errors.<frequenz>` und werden auf der Website als Hinweisbox angezeigt.
