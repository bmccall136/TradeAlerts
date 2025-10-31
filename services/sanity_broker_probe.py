# sanity_broker_probe.py  (run:  python -u sanity_broker_probe.py)
import logging
from services.broker import get_broker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

b = get_broker("LIVE")
print("account_id_key:", b.account_id_key or "(none)")

try:
    att = b.get_available_to_trade()
    sc  = b.get_settled_cash()
    bp  = b.get_buying_power(fresh=True)
    summ = b.get_account_summary()
    ui   = summ.get("ui", {})
    print("AvailableToTrade:", att)
    print("SettledCash     :", sc)
    print("BuyingPower     :", bp)
    print("UI keys         :", list(ui.keys()))
except Exception as e:
    print("probe failed:", e)
