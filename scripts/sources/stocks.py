"""Aktienkurse relevanter Modekonzerne. Primaer yfinance, Fallback Stooq-CSV."""
import csv
import io

from common import add_point, http_get, upsert_series

SOURCE = "Yahoo Finance (via yfinance) / Stooq"


def _via_yfinance(ticker):
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="10d", auto_adjust=False)
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
    for ticker, name in cfg.get("tickers", {}).items():
        points = None
        try:
            points = _via_yfinance(ticker)
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
