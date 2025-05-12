
import requests
import json

alert = {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "signal": "BREAKOUT",
    "timestamp": "2025-04-23 00:40:18",
    "confidence": "100.0",
    "price": "199.66",
    "sparkline": "198.32,198.06,198.89,199.45,199.38,199.66",
    "chart_url": "https://finance.yahoo.com/quote/AAPL"
}

response = requests.post("http://localhost:5000/trade-alert", json=alert)
print("Status:", response.status_code)
print("Response:", response.text)
