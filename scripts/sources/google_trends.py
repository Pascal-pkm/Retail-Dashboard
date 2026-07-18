"""Google-Trends-Suchinteresse zu Modemarken/-kategorien via pytrends (inoffiziell)."""
import time

from common import add_point, upsert_series

SOURCE = "Google Trends (via pytrends, inoffiziell)"


def fetch(data, config, errors):
    from pytrends.request import TrendReq

    cfg = config.get("google_trends", {})
    keywords = cfg.get("keywords", [])[:25]
    geo = cfg.get("geo", "DE")
    timeframe = cfg.get("timeframe", "today 3-m")

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
                for ts, val in df[kw].tail(30).items():
                    add_point(s, ts.date().isoformat(), float(val), "daily")
            time.sleep(2)
        except Exception as e:  # noqa: BLE001
            errors.append(("google_trends", f"{batch}: {e}"))
