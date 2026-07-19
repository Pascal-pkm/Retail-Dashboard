"""Newsletter-Versand via Gmail SMTP (App-Passwort): python scripts/newsletter.py <freq>

Benoetigte Umgebungsvariablen (GitHub-Secrets):
  GMAIL_ADDRESS       - deine Gmail-Adresse (Absender), z.B. deinname@gmail.com
  GMAIL_APP_PASSWORD  - App-Passwort aus den Google-Konto-Sicherheitseinstellungen
                        (NICHT dein normales Gmail-Passwort - dafuer muss die
                        2-Faktor-Authentifizierung aktiv sein: myaccount.google.com/apppasswords)
  NEWSLETTER_TO       - Empfaenger, kommagetrennt (i.d.R. deine eigene Adresse)
Optional: NEWSLETTER_ENABLED=true als Repo-Variable (Gate im Workflow).
Ohne Zugangsdaten bricht das Script NICHT hart ab (Exit 0 mit Hinweis).

Design/Inhalt (Stand 07/2026, siehe COMPLIANCE.md-Historie): "Spark"-Format
angelehnt an Apollo's "Daily Spark" (Torsten Slok) - kompakte Karten pro
Kennzahl (Zahl + Mini-Chart + 1-2 knappe Saetze), keine Fliesstext-Absaetze.
Farbschema 1:1 vom Dashboard (docs/index.html :root-Variablen) uebernommen.
Inhalts-Scoping je Frequenz (Nutzerentscheidung 2026-07):
  - taeglich:    Google-Trends-Tagesbewegungen + Radverkehr/Fussgaenger-
                 Tagessummen je Region (mit Wetter-Hinweis, keine YoY).
  - woechentlich: wie taeglich, aber auf Wochenbasis aggregiert (inkl. YoY).
  - monatlich:   wie woechentlich (Monatsbasis) + ifo-Geschaeftsklima-Indizes.
  - quartalsweise: wie monatlich (Quartalsbasis) + Zalando-IR-Kennzahlen.
"""
import os
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from common import (aggregate_avg, aggregate_sum, fmt_de, load_config,
                     load_data, pct_change, yoy_from_points)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# --- Farbschema 1:1 aus docs/index.html :root uebernommen ---------------
C = {
    "bg": "#2b3137", "bg2": "#22272b", "card": "#363d44", "border": "#484f57",
    "accent": "#d7e94a", "accent_dark": "#232a10", "text": "#eef1f2", "muted": "#9aa3ab",
    "up": "#6ee7a0", "down": "#f87171",
    "badge_standort_bg": "rgba(110,231,160,.15)", "badge_standort_fg": "#6ee7a0",
    "badge_konzern_bg": "rgba(248,113,113,.15)", "badge_konzern_fg": "#f87171",
    "badge_branche_bg": "rgba(96,165,250,.15)", "badge_branche_fg": "#60a5fa",
    "badge_region_bg": "rgba(216,180,254,.15)", "badge_region_fg": "#d8b4fe",
}

FREQ_LABEL = {"daily": "Täglich", "weekly": "Wöchentlich", "monthly": "Monatlich", "quarterly": "Quartal"}
PERIOD_WORD = {"daily": "Vortag", "weekly": "Vorwoche", "monthly": "Vormonat", "quarterly": "Vorquartal"}
VORJAHRES_WORD = {"weekly": "Vorjahreswoche", "monthly": "Vorjahresmonat", "quarterly": "Vorjahresquartal"}
SCOPE_BADGE = {
    "standort": ("Standortebene", C["badge_standort_bg"], C["badge_standort_fg"]),
    "konzern": ("Konzernebene – keine Standortdaten", C["badge_konzern_bg"], C["badge_konzern_fg"]),
    "branche": ("Branche/Gesamtmarkt", C["badge_branche_bg"], C["badge_branche_fg"]),
    "region": ("Regional-Index", C["badge_region_bg"], C["badge_region_fg"]),
}
FREQUENZ_UNIT = {
    "daily": "Fahrräder/Tag (Summe)", "weekly": "Fahrräder/Woche (Summe)",
    "monthly": "Fahrräder/Monat (Summe)", "quarterly": "Fahrräder/Quartal (Summe)",
}
FUSSGAENGER_UNIT = {
    "daily": "Fußgänger/Tag (Summe)", "weekly": "Fußgänger/Woche (Summe)",
    "monthly": "Fußgänger/Monat (Summe)", "quarterly": "Fußgänger/Quartal (Summe)",
}

# Kuratierte Zalando-Kopfzahlen fuer den Quartals-Newsletter (statt aller ~35
# KPIs aus der Financials-XLS) - siehe ir_reports.py fuer die vollstaendige Liste.
ZALANDO_HEADLINE_SIDS = [
    "ir_zalando_gross_merchandise_volume_gmv_in_m_eur",
    "ir_zalando_revenue_in_m_eur",
    "ir_zalando_ebit_in_m_eur",
    "ir_zalando_adjusted_ebit_margin_in",
    "ir_zalando_active_customers_ltm_m",
    "ir_zalando_free_cash_flow",
    "ir_zalando_number_of_orders_m",
]


def _short_name(cfg_name):
    """'Baden-Württemberg (MobiData BW)' -> 'Baden-Württemberg'."""
    return cfg_name.split(" (")[0].strip()


def _de_date(iso):
    """'2026-07-17' -> '17.07.' (fuer knappe Vergleichsangaben ohne festen Zeitwort)."""
    try:
        y, m, d = iso.split("-")
        return f"{d}.{m}."
    except Exception:  # noqa: BLE001
        return iso


def _arrow_color(chg):
    if chg is None:
        return "–", C["muted"]
    return ("▲", C["up"]) if chg >= 0 else ("▼", C["down"])


def _bar_chart(points, height=26, max_bars=10):
    """Email-sichere Mini-Sparkline aus Tabellenzellen (keine Bilder/SVG noetig,
    funktioniert auch in Gmail ohne 'externe Inhalte laden')."""
    pts = [p for p in points if p[1] is not None][-max_bars:]
    if len(pts) < 2:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    cells = []
    for _, v in pts:
        h = 3 + round((v - lo) / span * (height - 3))
        cells.append(
            f'<td style="vertical-align:bottom;padding:0 1px">'
            f'<div style="width:5px;height:{h}px;background:{C["accent"]};border-radius:1px"></div></td>'
        )
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
            f'<tr style="height:{height}px">{"".join(cells)}</tr></table>')


def _card(*, badge_text, badge_bg, badge_fg, title, value, unit, chg, chg_word, points, note, stand, source):
    arrow, color = _arrow_color(chg)
    chg_html = f'{arrow} {fmt_de(abs(chg))} % ggü. {chg_word}' if chg is not None else f'{arrow} kein Vergleichswert verfügbar'
    bars = _bar_chart(points)
    bars_cell = (f'<td style="vertical-align:bottom;padding-right:14px">{bars}</td>' if bars else "")
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="background:{C['card']};border:1px solid {C['border']};border-radius:10px;margin-bottom:12px">
<tr><td style="padding:14px 18px">
  <span style="display:inline-block;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;
    color:{badge_fg};background:{badge_bg};padding:3px 9px;border-radius:10px;margin-bottom:6px">{badge_text}</span>
  <div style="font-size:14px;font-weight:600;color:{C['text']};margin:5px 0 10px">{title}</div>
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
    {bars_cell}
    <td style="vertical-align:bottom">
      <div style="font-size:23px;font-weight:800;color:{C['text']};line-height:1">{fmt_de(value, 1)} <span style="font-size:13px;font-weight:400;color:{C['muted']}">{unit}</span></div>
      <div style="font-size:13px;font-weight:700;color:{color};margin-top:4px">{chg_html}</div>
    </td>
  </tr></table>
  {f'<div style="font-size:13px;color:#c7cdd2;margin-top:10px;line-height:1.45">{note}</div>' if note else ''}
  <div style="font-size:11px;color:{C['muted']};margin-top:8px">Stand {stand} · {source}</div>
</td></tr>
</table>"""


def _section(title, intro, cards_html):
    if not cards_html:
        return ""
    intro_html = f'<p style="font-size:13px;color:{C["muted"]};margin:0 0 14px;line-height:1.5">{intro}</p>' if intro else ""
    return f"""<h2 style="font-size:15px;color:{C['accent']};margin:26px 0 4px;font-weight:700">{title}</h2>
{intro_html}
{''.join(cards_html)}"""


# --- Google Trends --------------------------------------------------------

def _gtrends_cards(data, freq, threshold, max_cards=8):
    rows = []  # (abs_chg, html)
    quiet = 0
    for sid, s in sorted(data.get("series", {}).items()):
        if not sid.startswith("gtrends_") or not s.get("points"):
            continue
        pts = sorted(s["points"])
        agg = pts if freq == "daily" else aggregate_avg(pts, freq)
        if len(agg) < 2:
            continue
        (d_prev, v_prev), (d_new, v_new) = agg[-2], agg[-1]
        chg = pct_change(v_new, v_prev)
        if chg is None:
            continue
        if abs(chg) < threshold:
            quiet += 1
            continue
        badge = s.get("group_label", "Google Trends")
        card = _card(
            badge_text=badge, badge_bg=C["badge_branche_bg"], badge_fg=C["badge_branche_fg"],
            title=s["label"], value=v_new, unit="Punkte (0-100)", chg=chg, chg_word=PERIOD_WORD[freq],
            points=agg, note="", stand=d_new, source="Google Trends",
        )
        rows.append((abs(chg), card))
    rows.sort(key=lambda r: -r[0])
    cards = [html for _, html in rows[:max_cards]]
    hidden = len(rows) - len(cards) + quiet
    intro = "Suchinteresse (DE) aus Google Trends – nur auffällige Bewegungen (Schwelle ±%s %%)." % fmt_de(threshold)
    if hidden > 0:
        intro += f" {hidden} weitere Suchbegriffe ohne auffällige Bewegung nicht angezeigt."
    return _section("Google-Suchverhalten", intro, cards)


# --- Radverkehr / Fußgänger ("Frequenzen") --------------------------------

def _daily_region_sums(stations, region_filter=None):
    """Tagessummen je Region aus Stations-Rohdaten (fuer freq='daily', da die
    Website Tageswerte bewusst nicht anzeigt/aggregiert - siehe RV_SUBFREQS)."""
    by_region = {}
    for st in stations.values():
        region = region_filter or st.get("region") or "_"
        by_region.setdefault(region, {})
        for d, v in st.get("points", []):
            by_region[region][d] = by_region[region].get(d, 0.0) + v
    return {r: sorted(sums.items()) for r, sums in by_region.items()}


def _frequenz_cards(data, config, freq):
    cards = []

    # Radverkehr: 9 Regionen
    if freq == "daily":
        sums = _daily_region_sums(data.get("radverkehr_stations", {}))
        for region_key, cfg in config.get("radverkehr", {}).get("regions", {}).items():
            pts = sums.get(region_key, [])
            if len(pts) < 2:
                continue
            (d_prev, v_prev), (d_new, v_new) = pts[-2], pts[-1]
            chg = pct_change(v_new, v_prev)
            cards.append(_card(
                badge_text="Radverkehr-Proxy", badge_bg=C["badge_region_bg"], badge_fg=C["badge_region_fg"],
                title=_short_name(cfg["name"]), value=v_new, unit=FREQUENZ_UNIT["daily"], chg=chg,
                chg_word=_de_date(d_prev), points=pts,
                note="Tageswerte sind wetter-/saisonabhängig stark verrauscht – nicht als verlässlicher Trend zu werten.",
                stand=d_new, source=cfg.get("source", ""),
            ))
    else:
        for sid, s in sorted(data.get("series", {}).items()):
            if not sid.startswith("radverkehr_region_") or not s.get("points"):
                continue
            region_key = sid[len("radverkehr_region_"):]
            cfg = config.get("radverkehr", {}).get("regions", {}).get(region_key, {})
            agg = aggregate_sum(sorted(s["points"]), freq)
            v_new, chg, d_new = yoy_from_points(agg, freq)
            if v_new is None:
                continue
            note = "" if chg is not None else "Noch kein Vorjahreswert verfügbar (Datenhistorie zu kurz)."
            cards.append(_card(
                badge_text="Radverkehr-Proxy", badge_bg=C["badge_region_bg"], badge_fg=C["badge_region_fg"],
                title=_short_name(cfg.get("name", region_key)), value=v_new, unit=FREQUENZ_UNIT[freq], chg=chg,
                chg_word=VORJAHRES_WORD[freq], points=agg, note=note, stand=d_new, source=cfg.get("source", ""),
            ))

    # Fußgänger: aktuell nur Oldenburg (echte Zählung, kein Proxy)
    fg_cfg = config.get("fussgaenger", {}).get("oldenburg", {})
    if freq == "daily":
        sums = _daily_region_sums(data.get("fussgaenger_stations", {}), region_filter="oldenburg")
        pts = sums.get("oldenburg", [])
        if len(pts) >= 2:
            (d_prev, v_prev), (d_new, v_new) = pts[-2], pts[-1]
            chg = pct_change(v_new, v_prev)
            cards.append(_card(
                badge_text="Fußgänger (echte Zählung)", badge_bg=C["badge_region_bg"], badge_fg=C["badge_region_fg"],
                title=_short_name(fg_cfg.get("name", "Oldenburg")), value=v_new, unit=FUSSGAENGER_UNIT["daily"],
                chg=chg, chg_word=_de_date(d_prev), points=pts,
                note="Tageswerte sind wetter-/saisonabhängig stark verrauscht – nicht als verlässlicher Trend zu werten.",
                stand=d_new, source=fg_cfg.get("source", ""),
            ))
    else:
        s = data.get("series", {}).get("fussgaenger_region_oldenburg")
        if s and s.get("points"):
            agg = aggregate_sum(sorted(s["points"]), freq)
            v_new, chg, d_new = yoy_from_points(agg, freq)
            if v_new is not None:
                note = "" if chg is not None else "Noch kein Vorjahreswert verfügbar (Datenhistorie zu kurz)."
                cards.append(_card(
                    badge_text="Fußgänger (echte Zählung)", badge_bg=C["badge_region_bg"], badge_fg=C["badge_region_fg"],
                    title=_short_name(fg_cfg.get("name", "Oldenburg")), value=v_new, unit=FUSSGAENGER_UNIT[freq],
                    chg=chg, chg_word=VORJAHRES_WORD[freq], points=agg, note=note, stand=d_new,
                    source=fg_cfg.get("source", ""),
                ))

    if freq == "daily":
        intro = ("Tagessummen je Zählregion (Radverkehr = grober Wegefrequenz-Proxy, Fußgänger = echte Zählung). "
                  "Vergleich ggü. letztem verfügbaren Vortag, ohne Glättung – siehe Hinweise je Karte.")
    else:
        intro = ("Regionssummen mit Vorjahresvergleich, wie im Dashboard-Tab „Karte“ bzw. „Fußgänger“. "
                  "Radverkehr ist ein grober Wegefrequenz-Proxy, kein Fußgängerwert.")
    return _section("Frequenzen (Rad- & Fußverkehr)", intro, cards)


# --- ifo-Geschäftsklima (nur monatlich) -----------------------------------

def _ifo_cards(data):
    cards = []
    for sid in ("ifo_geschaeftsklima", "ifo_geschaeftslage", "ifo_geschaeftserwartungen"):
        s = data.get("series", {}).get(sid)
        if not s or len(s.get("points", [])) < 2:
            continue
        pts = sorted(s["points"])
        (d_prev, v_prev), (d_new, v_new) = pts[-2], pts[-1]
        chg = pct_change(v_new, v_prev)
        cards.append(_card(
            badge_text="Branche/Gesamtmarkt", badge_bg=C["badge_branche_bg"], badge_fg=C["badge_branche_fg"],
            title=s["label"], value=v_new, unit="Punkte", chg=chg, chg_word=PERIOD_WORD["monthly"],
            points=pts[-10:], note="", stand=d_new, source="ifo Institut / Handelsverband Deutschland (HDE)",
        ))
    return _section("ifo-Geschäftsklima Einzelhandel", "Stimmungsindikatoren für den deutschen Einzelhandel (ifo/HDE).", cards)


# --- Zalando IR-Kennzahlen (nur quartalsweise) ----------------------------

def _zalando_cards(data):
    cards = []
    for sid in ZALANDO_HEADLINE_SIDS:
        s = data.get("series", {}).get(sid)
        if not s or not s.get("points"):
            continue
        pts = sorted(s["points"])
        d_new, v_new = pts[-1]
        chg = pct_change(v_new, pts[-2][1]) if len(pts) >= 2 else None
        cards.append(_card(
            badge_text="Konzernebene – keine Standortdaten", badge_bg=C["badge_konzern_bg"], badge_fg=C["badge_konzern_fg"],
            title=s["label"].split(": ", 1)[-1], value=v_new, unit=s.get("unit", ""), chg=chg,
            chg_word=PERIOD_WORD["quarterly"], points=pts[-8:], note="", stand=d_new,
            source="Zalando SE Investor Relations",
        ))
    report = data.get("ir_reports", {}).get("zalando", {})
    intro = "Konzernweite Kennzahlen aus der quartalsweisen „Financials XLS“ (keine Standort-/Filialdaten)."
    if report.get("report_url"):
        intro += f' <a href="{report["report_url"]}" style="color:{C["accent"]}">Vollständiger Bericht ({report.get("quarter", "")}) →</a>'
    return _section("Zalando – Investor-Relations-Kennzahlen", intro, cards)


# --- Zusammenbau ------------------------------------------------------------

def build_html(data, freq, config):
    threshold = config.get("commentary_thresholds", {}).get(freq, 3.0)
    sections = [_gtrends_cards(data, freq, threshold), _frequenz_cards(data, config, freq)]
    if freq == "monthly":
        sections.append(_ifo_cards(data))
    if freq == "quarterly":
        sections.append(_zalando_cards(data))
    body = "".join(s for s in sections if s)
    if not body:
        body = f'<p style="color:{C["muted"]};padding:20px 0">Keine Daten für diese Periode vorhanden.</p>'

    url = config.get("dashboard_url", "#")
    today = date.today().strftime("%d.%m.%Y")
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:{C['bg']}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{C['bg']}">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;font-family:system-ui,-apple-system,'Segoe UI',Arial,sans-serif">
<tr><td style="background:{C['bg2']};border-radius:10px 10px 0 0;padding:22px 26px;border-bottom:3px solid {C['accent']}">
  <div style="font-size:20px;font-weight:800;color:{C['accent']};letter-spacing:.2px">Retail Spark</div>
  <div style="font-size:13px;color:{C['muted']};margin-top:4px">{FREQ_LABEL[freq]} · {today} · Retail-KPI-Dashboard – Mode &amp; Einzelhandel</div>
</td></tr>
<tr><td style="background:{C['bg']};padding:6px 26px 26px">
{body}
<p style="margin-top:22px"><a href="{url}" style="color:{C['accent']};font-size:13px;font-weight:600">→ Zum vollständigen Dashboard</a></p>
<hr style="border:none;border-top:1px solid {C['border']};margin-top:18px">
<p style="font-size:11px;color:{C['muted']};line-height:1.6;margin-top:14px">
Kennzahlen auf Konzernebene (z.&nbsp;B. GMV, EBIT) stammen aus Investor-Relations-Berichten und sind keine Standort-/Filialdaten.
Bon-KPIs je Standort sind nicht öffentlich verfügbar. Radverkehr-Zählstellen sind ein grober Tendenz-Proxy für Wegefrequenzen,
keine Fußgängerzahlen. Destatis-/ifo-Daten: Datenlizenz Deutschland – Namensnennung – 2.0 (dl-de/by-2-0).</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def send_via_gmail(html, subject, to_list, gmail_address, app_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Retail Spark", gmail_address))
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to_list, msg.as_string())


def main():
    freq = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if freq not in FREQ_LABEL:
        sys.exit(f"Aufruf: python scripts/newsletter.py <{'|'.join(FREQ_LABEL)}>")

    gmail_address = os.environ.get("GMAIL_ADDRESS", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to = [x.strip() for x in os.environ.get("NEWSLETTER_TO", "").split(",") if x.strip()]

    data = load_data()
    config = load_config()
    html = build_html(data, freq, config)

    # Vorschau immer ablegen (Artefakt/Debug)
    out = os.path.join(os.path.dirname(__file__), "..", f"newsletter_{freq}_preview.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Vorschau geschrieben: {out}")

    if not gmail_address or not app_password or not to:
        print("GMAIL_ADDRESS/GMAIL_APP_PASSWORD/NEWSLETTER_TO nicht vollständig gesetzt - Versand uebersprungen.")
        return

    subject = f"Retail Spark – {FREQ_LABEL[freq]} – {date.today().strftime('%d.%m.%Y')}"
    try:
        send_via_gmail(html, subject, to, gmail_address, app_password)
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(f"Gmail-Login fehlgeschlagen (App-Passwort korrekt & 2FA aktiv?): {e}")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Gmail-Versand fehlgeschlagen: {e}")

    print(f"Newsletter ({freq}) via Gmail an {len(to)} Empfänger versendet.")


if __name__ == "__main__":
    main()
