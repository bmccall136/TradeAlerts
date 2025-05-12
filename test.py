import requests
import datetime

test_alert = {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "signal": "BREAKOUT",
    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "confidence": "100.0",
    "price": "$172.50",
    "sparkline": "170.1,170.5,171.2,171.8,172.3,172.5",
    "chart_url": "https://finance.yahoo.com/quote/AAPL"
}

res = requests.post("http://localhost:5000/trade-alert", json=test_alert)
print("✅ Sent!" if res.status_code == 200 else f"❌ Failed: {res.status_code}")
