"""Aktienkurse relevanter Modekonzerne. Primaer yfinance, Fallback Stooq-CSV.

Normalbetrieb laedt nur die letzten 10 Handelstage (period="10d") - reicht fuer
den taeglichen Cron, da add_point() ohnehin dedupliziert und die Serie sich
Tag fuer Tag von selbst aufbaut. Fuer Vorjahresvergleiche (2024/2025 vs. 2026)
reicht das aber nicht aus; dafuer gibt es einen einmaligen Backfill-Modus ueber
die Umgebungsvariable STOCKS_BACKFILL_PERIOD (z.B. "2y", "5y", "max" - jeder
von yfinance akzeptierte period-Wert). Lokal: STOCKS_BACKFILL_PERIOD=2y python
scripts/run_update.py daily. Ueber GitHub Actions: Feld "stocks_backfill_period"
beim manuellen Start des taeglichen Workflows.
"""
import csv
import io
import os

from common import add_point, http_get, upsert_series

SOURCE = "Yahoo Finance (via yfinance) / Stooq"


def _via_yfinance(ticker, period="10d"):
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if hist is None or hist.empty:
        raise RuntimeError("keine Kursdaten")
    return [(idx.date().isoformat(), float(row["Close"])) for idx, row in hist.iterrows()]


def _via_stooq(symbol):
    r = http_get(f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows or rows[0].get("Close") in (None, "", "N/D"):
        raise RuntimeError("Stooq: keine Daten")
    row = rows[0]
    return [(row["Date"], float(row["Close"]))]


def fetch(data, config, errors):
    cfg = config.get("stocks", {})
    fallback = cfg.get("stooq_fallback", {})
    backfill_period = os.environ.get("STOCKS_BACKFILL_PERIOD", "").strip()
    period = backfill_period or "10d"
    if backfill_period:
        print(f"stocks: BACKFILL-Modus, period={backfill_period}", flush=True)
    for ticker, name in cfg.get("tickers", {}).items():
        points = None
        try:
            points = _via_yfinance(ticker, period=period)
        except Exception as e1:  # noqa: BLE001
            if ticker in fallback:
                try:
                    points = _via_stooq(fallback[ticker])
                except Exception as e2:  # noqa: BLE001
                    errors.append(("stocks", f"{name} ({ticker}): yfinance: {e1} | stooq: {e2}"))
            else:
                errors.append(("stocks", f"{name} ({ticker}): {e1}"))
        if not points:
            continue
        cur = "SEK" if ticker.endswith(".ST") else "EUR"
        s = upsert_series(
            data, f"stock_{ticker.lower().replace('.', '_').replace('-', '_')}",
            label=f"Aktie {name}", frequency="daily", unit=cur, scope="konzern",
            source=SOURCE, source_url=f"https://finance.yahoo.com/quote/{ticker}",
        )
        for d, close in points:
            add_point(s, d, close, "daily")
