"""Google-Trends-Suchinteresse zu Modemarken/-kategorien via pytrends (inoffiziell).

Normalbetrieb fragt nur "today 3-m" ab und speichert davon die letzten 30 Tage -
die Serie waechst dadurch Tag fuer Tag von selbst. Fuer Vorjahresvergleiche gibt
es einen einmaligen Backfill-Modus ueber die Umgebungsvariable
GTRENDS_BACKFILL_TIMEFRAME (jeder von pytrends akzeptierte timeframe-String,
z.B. "today 5-y" oder "2019-01-01 2026-07-18"). WICHTIG: Google Trends skaliert
den 0-100-Index relativ INNERHALB einer Anfrage - mehrere kurze Anfragen
aneinanderzuhaengen wuerde nicht vergleichbare Werte liefern. Deshalb wird beim
Backfill bewusst NICHT in Chunks aufgeteilt, sondern eine einzelne lange Anfrage
gestellt (Google liefert dafuer automatisch woechentliche statt taegliche
Aufloesung - die Serie bleibt trotzdem "frequency": "daily", nur mit groesserem
Punktabstand in der Historie). Lokal: GTRENDS_BACKFILL_TIMEFRAME="today 5-y"
python scripts/run_update.py daily. Ueber GitHub Actions: Feld
"gtrends_backfill_timeframe" beim manuellen Start des taeglichen Workflows.
"""
import os
import time

from common import add_point, upsert_series

SOURCE = "Google Trends (via pytrends, inoffiziell)"


def fetch(data, config, errors):
    from pytrends.request import TrendReq

    cfg = config.get("google_trends", {})
    keywords = cfg.get("keywords", [])[:25]
    geo = cfg.get("geo", "DE")
    backfill_timeframe = os.environ.get("GTRENDS_BACKFILL_TIMEFRAME", "").strip()
    timeframe = backfill_timeframe or cfg.get("timeframe", "today 3-m")
    if backfill_timeframe:
        print(f"google_trends: BACKFILL-Modus, timeframe={backfill_timeframe}", flush=True)

    # Hinweis: retries-Parameter von pytrends ist mit urllib3>=2 inkompatibel -> eigener Retry
    py = TrendReq(hl="de-DE", tz=60)
    # max. 5 Keywords pro Payload
    for i in range(0, len(keywords), 5):
        batch = keywords[i:i + 5]
        try:
            df = None
            for attempt in range(3):
                try:
                    py.build_payload(batch, geo=geo, timeframe=timeframe)
                    df = py.interest_over_time()
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 2:
                        raise
                    time.sleep(10 * (attempt + 1))
            if df is None or df.empty:
                raise RuntimeError(f"Leere Antwort fuer {batch}")
            if "isPartial" in df.columns:
                df = df[~df["isPartial"].astype(bool)]
            for kw in batch:
                if kw not in df.columns:
                    continue
                sid = "gtrends_" + kw.lower().replace(" ", "_").replace("&", "und")
                s = upsert_series(
                    data, sid,
                    label=f"Suchinteresse „{kw}“ ({geo})", frequency="daily",
                    unit="Index 0-100", scope="branche",
                    source=SOURCE, source_url="https://trends.google.de",
                )
                rows = df[kw] if backfill_timeframe else df[kw].tail(30)
                for ts, val in rows.items():
                    add_point(s, ts.date().isoformat(), float(val), "daily")
            time.sleep(2)
        except Exception as e:  # noqa: BLE001
            errors.append(("google_trends", f"{batch}: {e}"))
