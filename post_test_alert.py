import requests

alert = {
    "symbol": "TSLA",
    "name": "Tesla Inc.",
    "price": 180.55,
    "vwap": 179.20,
    "vwap_diff": 1.35,
    "qty": 150,
    "sparkline": "[179.1, 179.5, 180.0, 180.3, 180.55]",
    "triggers": "MACD 🚀 VWAP 📈 RSI 📉"
}

res = requests.post("http://127.0.0.1:5000/alerts", json=alert)
print(f"Status: {res.status_code}")
