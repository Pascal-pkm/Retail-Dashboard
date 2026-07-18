"""Newsletter-Versand via Gmail SMTP (App-Passwort): python scripts/newsletter.py <freq>

Benoetigte Umgebungsvariablen (GitHub-Secrets):
  GMAIL_ADDRESS       - deine Gmail-Adresse (Absender), z.B. deinname@gmail.com
  GMAIL_APP_PASSWORD  - App-Passwort aus den Google-Konto-Sicherheitseinstellungen
                        (NICHT dein normales Gmail-Passwort - dafuer muss die
                        2-Faktor-Authentifizierung aktiv sein: myaccount.google.com/apppasswords)
  NEWSLETTER_TO       - Empfaenger, kommagetrennt (i.d.R. deine eigene Adresse)
Optional: NEWSLETTER_ENABLED=true als Repo-Variable (Gate im Workflow).
Ohne Zugangsdaten bricht das Script NICHT hart ab (Exit 0 mit Hinweis).
"""
import os
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from common import fmt_de, load_config, load_data, pct_change

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

FREQ_TITLE = {
    "daily": "Täglicher Überblick",
    "weekly": "Wochenbericht",
    "monthly": "Monatsbericht",
    "quarterly": "Quartalsbericht",
}
PERIOD_WORD = {"daily": "Vortag", "weekly": "Vorwoche", "monthly": "Vormonat", "quarterly": "Vorquartal"}
SCOPE_BADGE = {
    "standort": "Standortebene",
    "konzern": "Konzernebene – keine Standortdaten",
    "branche": "Branche/Gesamtmarkt",
}


def build_html(data, freq, config):
    rows = []
    for sid, s in sorted(data.get("series", {}).items()):
        if s.get("frequency") != freq or not s.get("points"):
            continue
        d, v = s["points"][-1]
        chg = pct_change(v, s["points"][-2][1]) if len(s["points"]) >= 2 else None
        chg_html = "–"
        if chg is not None:
            color = "#1a7f37" if chg >= 0 else "#c62828"
            chg_html = f'<span style="color:{color}">{"+" if chg >= 0 else ""}{fmt_de(chg)} %</span>'
        rows.append(
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid #eee'>{s['label']}"
            f"<br><small style='color:#888'>{SCOPE_BADGE.get(s.get('scope'), '')}</small></td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right'>{fmt_de(v, 2)} {s.get('unit', '')}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:right'>{chg_html}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #eee'><small>{d}</small></td></tr>"
        )

    comments = data.get("commentary", {}).get(freq, {}).get("items", [])
    comment_html = "".join(f"<li style='margin-bottom:6px'>{c['text']}</li>" for c in comments)

    ir_html = ""
    if freq == "quarterly" and data.get("ir_reports"):
        links = "".join(
            f"<li><a href='{r['report_url']}'>{r['name']} – {r.get('quarter', '')}</a></li>"
            for r in data["ir_reports"].values() if r.get("report_url")
        )
        ir_html = f"<h3>Aktuelle IR-Berichte (Konzernebene)</h3><ul>{links}</ul>"

    sources = sorted({s.get("source", "") for s in data["series"].values()
                      if s.get("frequency") == freq and s.get("source")})
    url = config.get("dashboard_url", "#")

    return f"""<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;color:#222;max-width:680px;margin:auto">
<h2 style="border-bottom:3px solid #1a3c6e;padding-bottom:6px">Retail-KPI {FREQ_TITLE[freq]} – {date.today().strftime('%d.%m.%Y')}</h2>
<h3>Kommentierung (automatisch, regelbasiert)</h3>
<ul>{comment_html or '<li>Keine Kommentare.</li>'}</ul>
<h3>Kennzahlen (Veränderung ggü. {PERIOD_WORD[freq]})</h3>
<table style="border-collapse:collapse;width:100%">
<tr style="background:#f3f5f8"><th style="padding:6px 10px;text-align:left">KPI</th><th style="padding:6px 10px;text-align:right">Wert</th><th style="padding:6px 10px;text-align:right">Δ</th><th style="padding:6px 10px;text-align:left">Stand</th></tr>
{''.join(rows) or '<tr><td colspan=4 style="padding:10px">Keine Daten vorhanden.</td></tr>'}
</table>
{ir_html}
<p><a href="{url}">→ Zum vollständigen Dashboard</a></p>
<hr style="border:none;border-top:1px solid #ddd">
<p style="font-size:12px;color:#888">Hinweis: Kennzahlen auf Konzernebene (z.&nbsp;B. GMV, AOV) stammen aus Investor-Relations-Berichten
und sind keine Standort-/Filialdaten. Bon-KPIs je Standort sind nicht öffentlich verfügbar.<br>
Quellen: {'; '.join(sources) or '–'}.<br>
Destatis-Daten: Datenlizenz Deutschland – Namensnennung – 2.0 (dl-de/by-2-0).</p>
</body></html>"""


def send_via_gmail(html, subject, to_list, gmail_address, app_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Retail KPI Dashboard", gmail_address))
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to_list, msg.as_string())


def main():
    freq = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if freq not in FREQ_TITLE:
        sys.exit(f"Aufruf: python scripts/newsletter.py <{'|'.join(FREQ_TITLE)}>")

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

    subject = f"Retail-KPI {FREQ_TITLE[freq]} – {date.today().strftime('%d.%m.%Y')}"
    try:
        send_via_gmail(html, subject, to, gmail_address, app_password)
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(f"Gmail-Login fehlgeschlagen (App-Passwort korrekt & 2FA aktiv?): {e}")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Gmail-Versand fehlgeschlagen: {e}")

    print(f"Newsletter ({freq}) via Gmail an {len(to)} Empfänger versendet.")


if __name__ == "__main__":
    main()
