import json
from services.market_service import analyze_symbol

SETTINGS_PATH = r"C:\TradeAlerts\live_settings_swing.json"
SYMS = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY", "AMD", "META", "AMZN"]

with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    settings = json.load(f)

for s in SYMS:
    price, triggered, passed = analyze_symbol(s, settings)
    print(f"{s:5} price={price} passed={passed} triggers={triggered}")
