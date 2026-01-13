from flask import Flask, request, jsonify
import yfinance as yf

app = Flask(__name__)

@app.route("/api/market")
def market():
    ticker = request.args.get("ticker", "AAPL")

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return jsonify({
            "ticker": ticker,
            "price": info.get("currentPrice"),
            "marketCap": info.get("marketCap"),
            "currency": info.get("currency")
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
