from services import etrade_service as et
import json
aid = et.account_id_key()
prev = et.preview_equity_order(aid, "FCX", 1, 45.10, action="SELL", price_type="LIMIT")
print("preview ok:", (prev.get("PreviewOrderResponse") or {}).get("PreviewIds"))
placed = et.place_equity_order(prev)
print(json.dumps(placed, indent=2))
