import logging
import re
import time

from flask import Flask, request, jsonify, send_from_directory
import yfinance as yf

app = Flask(__name__, static_folder=None)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

CACHE_TTL = 60
_cache = {}

TICKER_RE = re.compile(r"^[A-Z0-9.\-=^]{1,15}$")
HISTORY_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}


def normalize_ticker(raw):
    """Accept Bloomberg-style input like 'AAPL US' and return a Yahoo symbol."""
    ticker = raw.strip().upper()
    if ticker.endswith(" US"):
        ticker = ticker[:-3].strip()
    ticker = ticker.replace(" ", "")
    return ticker if TICKER_RE.match(ticker) else None


def cached(key, fetch):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    value = fetch()
    _cache[key] = (time.time(), value)
    return value


def fetch_quote(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info or {}

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        try:
            price = stock.fast_info.last_price
        except Exception:
            price = None

    if price is None and not info.get("shortName"):
        return None

    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    change_pct = None
    if price is not None and prev_close:
        change_pct = round((price - prev_close) / prev_close * 100, 2)

    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName"),
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),
        "price": price,
        "previousClose": prev_close,
        "changePercent": change_pct,
        "volume": info.get("volume") or info.get("regularMarketVolume"),
        "marketCap": info.get("marketCap"),
        "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
    }


def fetch_history(ticker, period):
    df = yf.Ticker(ticker).history(period=period)
    return [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 4)}
        for idx, row in df.iterrows()
    ]


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/market")
def market():
    ticker = normalize_ticker(request.args.get("ticker", "AAPL"))
    if not ticker:
        return jsonify({"error": "invalid ticker"}), 400

    try:
        data = cached(("quote", ticker), lambda: fetch_quote(ticker))
    except Exception:
        log.exception("quote fetch failed for %s", ticker)
        return jsonify({"error": "market data provider unavailable"}), 502

    if data is None:
        return jsonify({"error": f"ticker not found: {ticker}"}), 404
    return jsonify(data)


@app.route("/api/history")
def history():
    ticker = normalize_ticker(request.args.get("ticker", "AAPL"))
    if not ticker:
        return jsonify({"error": "invalid ticker"}), 400
    period = request.args.get("period", "1mo")
    if period not in HISTORY_PERIODS:
        return jsonify({"error": f"invalid period, use one of: {sorted(HISTORY_PERIODS)}"}), 400

    try:
        points = cached(("history", ticker, period), lambda: fetch_history(ticker, period))
    except Exception:
        log.exception("history fetch failed for %s", ticker)
        return jsonify({"error": "market data provider unavailable"}), 502

    if not points:
        return jsonify({"error": f"ticker not found: {ticker}"}), 404
    return jsonify({"ticker": ticker, "period": period, "points": points})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
