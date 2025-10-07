import json
import time

from services import etrade_service as et

aid = et.account_id_key()
coid = f"sg-fcx-{int(time.time()*1000)}"
prev = et.preview_equity_order(
    aid, "FCX", 1, None, action="SELL", price_type="MARKET", client_order_id=coid
)
print("preview-only OK:", "PreviewOrderResponse" in prev)
print(json.dumps(prev, indent=2))
