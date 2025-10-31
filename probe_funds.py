# C:\TradeAlerts\probe_funds.py
import services.broker_patch  # ensure patched
from services.broker import LiveBroker

b = LiveBroker(mode="LIVE")
try:
    sc = b.get_settled_cash()
    bp = b.get_buying_power()
    print("settled_cash:", sc, " usable (ATT-first):", bp)
except Exception as e:
    print("probe error:", e)
