"""Regelbasierte Kommentierung: kurze Einordnung auffaelliger Veraenderungen."""
from common import fmt_de, now_iso, pct_change

PERIOD_WORD = {
    "daily": "Vortag",
    "weekly": "Vorwoche",
    "monthly": "Vormonat",
    "quarterly": "Vorquartal",
}


def _describe(label, chg, freq, scope):
    arrow = "▲" if chg > 0 else "▼"
    verb = "gestiegen" if chg > 0 else "gesunken"
    scope_note = " (Konzernwert, keine Standortdaten)" if scope == "konzern" and freq == "quarterly" else ""
    return f"{arrow} {label}: {fmt_de(abs(chg))} % ggü. {PERIOD_WORD[freq]} {verb}{scope_note}."


def generate(data, freq, config):
    threshold = config.get("commentary_thresholds", {}).get(freq, 3.0)
    items = []
    for sid, s in sorted(data.get("series", {}).items()):
        if s.get("frequency") != freq or len(s.get("points", [])) < 2:
            continue
        if sid.startswith("radverkehr_region_") or sid.startswith("fussgaenger_region_"):
            # Landen ausschliesslich im eigenen Karte-/Fussgaenger-Tab (siehe
            # docs/index.html), nicht mehr in der normalen Kommentierung - sonst
            # taucht dort eine Kennzahl auf, die auf diesem Tab gar nicht sichtbar ist.
            continue
        if "normalisiert" in s.get("unit", ""):
            # %-Veraenderung normalisierter Indizes ist nicht aussagekraeftig;
            # dafuer liefern die Dashboard-Widgets fertige Aussagen
            continue
        (d_prev, v_prev), (d_new, v_new) = s["points"][-2], s["points"][-1]
        chg = pct_change(v_new, v_prev)
        if chg is None:
            continue
        if abs(chg) >= threshold:
            items.append({
                "series": sid,
                "date": d_new,
                "change_pct": round(chg, 2),
                "text": _describe(s["label"], chg, freq, s.get("scope", "")),
            })
    items.sort(key=lambda x: -abs(x["change_pct"]))

    # Fertige Kennzahl-Aussagen aus dem Destatis-Dashboard (falls vorhanden)
    for w in data.get("dashboard_widgets", {}).get(freq, [])[:8]:
        items.append({"series": "dashboard_widget", "date": None, "change_pct": 0.0, "text": w})

    if not items:
        items.append({
            "series": None, "date": None, "change_pct": 0.0,
            "text": f"Keine auffälligen Veränderungen (Schwelle ±{fmt_de(threshold)} %) in dieser Periode.",
        })
    data.setdefault("commentary", {})[freq] = {"generated": now_iso(), "items": items[:15]}
    return items
