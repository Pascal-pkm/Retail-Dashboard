"""Quartalsweise IR-Berichte der Modekonzerne (Zalando, Inditex, H&M, About You).

WICHTIG: Alle hier erhobenen KPIs (GMV, aktive Kunden, AOV, Retourenquote) sind
KONZERNWEITE Werte aus offiziellen IR-Veroeffentlichungen - KEINE Standort-/
Filialdaten (die sind nicht oeffentlich verfuegbar, siehe README).

Vorgehen (best-effort):
1. IR-Seite laden, neuesten Quartals-PDF-Link finden.
2. PDF herunterladen, Text extrahieren, konfigurierte Regex-KPIs suchen.
3. Mindestens der Berichtslink wird immer gespeichert (data["ir_reports"]),
   auch wenn die KPI-Extraktion scheitert.
"""
import io
import re
from datetime import date

from common import add_point, http_get, now_iso, upsert_series

PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf[^"]*)"', re.IGNORECASE)
QUARTER_HINT = re.compile(r"(q[1-4]|quarter|interim|halbjahr|nine[- ]month|trading update)", re.IGNORECASE)


def _current_quarter_label():
    today = date.today()
    q = (today.month - 1) // 3 + 1
    # Berichte beziehen sich i.d.R. auf das Vorquartal
    q -= 1
    year = today.year
    if q == 0:
        q, year = 4, year - 1
    return f"{year}-Q{q}"


def _find_pdf(ir_url):
    html = http_get(ir_url).text
    links = PDF_LINK_RE.findall(html)
    if not links:
        return None
    scored = sorted(links, key=lambda u: 0 if QUARTER_HINT.search(u) else 1)
    url = scored[0]
    if url.startswith("/"):
        from urllib.parse import urljoin
        url = urljoin(ir_url, url)
    return url


def _extract_kpis(pdf_bytes, patterns):
    import pdfplumber

    out = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages[:15])
    for kpi, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                out[kpi] = float(m.group(1).replace(",", "."))
            except ValueError:
                continue
    return out


def fetch(data, config, errors):
    quarter = _current_quarter_label()
    reports = data.setdefault("ir_reports", {})
    for key, comp in config.get("ir_reports", {}).get("companies", {}).items():
        name = comp.get("name", key)
        try:
            pdf_url = _find_pdf(comp["ir_url"])
            entry = reports.setdefault(key, {})
            entry.update({
                "name": name, "quarter": quarter,
                "report_url": pdf_url or comp["ir_url"],
                "ir_url": comp["ir_url"], "checked": now_iso(),
                "scope": "konzern",
            })
            if not pdf_url:
                errors.append(("ir_reports", f"{name}: kein PDF-Link (JS-Seite?) - nur IR-Link gespeichert"))
                continue
            patterns = comp.get("kpi_patterns") or {}
            if patterns:
                pdf_bytes = http_get(pdf_url, timeout=90).content
                kpis = _extract_kpis(pdf_bytes, patterns)
                entry["kpis"] = kpis
                qdate = quarter.replace("-Q1", "-03-31").replace("-Q2", "-06-30") \
                               .replace("-Q3", "-09-30").replace("-Q4", "-12-31")
                for kpi, val in kpis.items():
                    sid = f"ir_{key}_" + "".join(c if c.isalnum() else "_" for c in kpi.lower())[:40]
                    s = upsert_series(
                        data, sid, label=f"{name}: {kpi}", frequency="quarterly",
                        unit=kpi[kpi.find("(") + 1:kpi.find(")")] if "(" in kpi else "",
                        scope="konzern",
                        source=f"{name} Investor Relations (Quartalsbericht)",
                        source_url=pdf_url,
                    )
                    add_point(s, qdate, val, "quarterly")
                if not kpis:
                    errors.append(("ir_reports", f"{name}: PDF gefunden, aber keine KPIs per Regex extrahiert ({pdf_url})"))
        except Exception as e:  # noqa: BLE001
            errors.append(("ir_reports", f"{name}: {e}"))
