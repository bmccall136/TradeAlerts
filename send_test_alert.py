
import requests

url = "http://localhost:5000/trade-alert"
data = {
    "symbol": "TEST",
    "name": "Test Inc.",
    "signal": "BREAKOUT",
    "timestamp": "2025-04-22 18:00:00",
    "confidence": "100.0",
    "price": "123.45",
    "sparkline": "121,122,123,124,125",
    "chart_url": "https://finance.yahoo.com/quote/TEST"
}

response = requests.post(url, json=data)
print(f"Status: {response.status_code}")
print("Response:", response.text)
