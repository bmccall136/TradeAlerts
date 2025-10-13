# _preview_probe_autoadapt.py  — direct call with your wrapper's param names
import json
import sys
import traceback
from datetime import datetime
from datetime import time as dtime

from services import etrade_service as et

ACC_KEY = "kW8LbkuGisPCK9Ey7C8iWA"  # your accountIdKey
SYMBOL = "HPQ"
QTY = 1


def now_session() -> str:
    t = datetime.now().time()
    return "REGULAR" if dtime(9, 30) <= t <= dtime(16, 0) else "EXTENDED"


def glimpse(obj, n=1600):
    try:
        return json.dumps(obj, indent=2)[:n]
    except Exception:
        return str(obj)[:n]


def extract_preview_id(resp: dict):
    for fn in [
        lambda r: (r.get("PreviewIds") or [None])[0],
        lambda r: (r.get("previewIds") or [None])[0],
        lambda r: (r.get("Order") or {}).get("previewIds", [None])[0],
        lambda r: (r.get("order") or [{}])[0].get("previewId"),
        lambda r: (r.get("Order") or [{}])[0].get("PreviewIds", [None])[0],
    ]:
        try:
            pid = fn(resp)
            if pid:
                return str(pid)
        except Exception:
            pass
    return None


def main():
    try:
        resp = et.preview_equity_order(
            account_id_key=ACC_KEY,
            symbol=SYMBOL,
            qty=int(QTY),
            price=None,  # MARKET => price_type='MARKET'
            action="BUY",
            price_type="MARKET",
            order_term="GOOD_FOR_DAY",
            market_session=now_session(),
        )
        print("RAW PREVIEW:", glimpse(resp))
        pid = extract_preview_id(resp or {})
        print("previewId:", pid)
        sys.exit(0 if pid else 2)
    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
