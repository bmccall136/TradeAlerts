# _preview_probe.py  (PowerShell-friendly preview smoke test)
import json
import sys
from datetime import datetime
from datetime import time as dtime

from services import etrade_service as et  # your wrapper

ACC_KEY = "kW8LbkuGisPCK9Ey7C8iWA"  # <- from your logs
ACC_NUM = None  # if you know the numeric id, put it here; else leave None

SYMBOL = "HPQ"
QTY = 1
SIDE = "BUY"  # BUY/SELL


def now_session() -> str:
    t = datetime.now().time()
    return "REGULAR" if dtime(9, 30) <= t <= dtime(16, 0) else "EXTENDED"


def glimpse(obj, n=1400):
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


def try_preview(call_desc, **kwargs):
    """Call your wrapper with a variety of arg names; return (resp, pid, errstr)."""
    try:
        resp = et.preview_equity_order(**kwargs)
        pid = extract_preview_id(resp or {})
        return resp, pid, None
    except Exception as e:
        return None, None, f"{call_desc}: {e.__class__.__name__}: {e}"


def main():
    print("=== Preview probe (multi-path) ===")
    req = dict(
        symbol=SYMBOL,
        quantity=int(QTY),
        side=SIDE,
        price=None,  # MARKET
        order_type="MARKET",
        time_in_force="DAY",
        market_session=now_session(),
    )

    trials = []

    # 1) accountIdKey vs account_key (both are seen in wrappers)
    trials.append(("account_key", dict(account_key=ACC_KEY, **req)))
    trials.append(("accountIdKey", dict(accountIdKey=ACC_KEY, **req)))

    # 2) numeric id path if you have it
    if ACC_NUM:
        trials.append(("account_id", dict(account_id=ACC_NUM, **req)))
        trials.append(("accountId", dict(accountId=ACC_NUM, **req)))

    # 3) no-account (some wrappers inject default)
    trials.append(("no_account", dict(**req)))

    got_any = False
    for desc, kwargs in trials:
        print(f"\n--- TRY {desc} ---")
        resp, pid, err = try_preview(desc, **kwargs)
        if err:
            print("[threw] ", err)
            continue
        got_any = True
        print("raw:", glimpse(resp))
        print("previewId:", pid)
        msgs = (resp or {}).get("messages") or (resp or {}).get("Messages") or []
        if msgs:
            print("messages:", glimpse(msgs, 2000))
        if pid:
            print(f"\nOK via {desc} ✅")
            sys.exit(0)

    if not got_any:
        print("\nNo preview responses (all calls threw). This usually means AUTH needed.")
        sys.exit(3)

    print("\nNo previewId in any response. See messages/raw above. ❌")
    sys.exit(2)


if __name__ == "__main__":
    main()
