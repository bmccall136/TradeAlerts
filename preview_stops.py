# preview_stops.py  — safe: PREVIEW ONLY
from services.broker import get_broker
from services.etrade_service import get_positions

ORDER_TERM = "GOOD_UNTIL_CANCEL"   # or "GOOD_FOR_DAY"
MARKET_SESSION = "REGULAR"         # or "EXTENDED"
FIXED_STOP_PCT = 5.0               # <- uses your live_settings.json idea; adjust if you want

def money(x):
    try: return f"${float(x):,.2f}"
    except: return str(x)

def get_preview_id(resp: dict):
    pr = resp.get("PreviewOrderResponse") or resp.get("PreviewOrderResponseV2") or resp
    pid = pr.get("previewId")
    if not pid:
        ids = pr.get("PreviewIds") or pr.get("previewIds") or []
        if isinstance(ids, dict): ids = [ids]
        if ids:
            pid = ids[0].get("previewId")
    return pid, pr

def main():
    b = get_broker("LIVE")  # preview is safe in LIVE
    positions = get_positions() or []
    if not positions:
        print("No positions returned.")
        return

    for p in positions:
        sym  = (p.get("symbol") or "").upper()
        qty  = int(p.get("qty") or 0)
        last = float(p.get("last_price") or 0.0)
        if not sym or qty <= 0 or last <= 0:
            continue

        stop = round(last * (1.0 - FIXED_STOP_PCT/100.0), 2)
        print(f"\n{sym}: qty={qty} last={money(last)}  STOP @ {money(stop)}  ({FIXED_STOP_PCT:.2f}% below)")

        prev = b._et.preview_equity_order(
            b._account_id_key, sym, qty, None, "SELL",
            price_type="STOP", stop_price=stop,
            order_term=ORDER_TERM, market_session=MARKET_SESSION
        )
        pid, pr = get_preview_id(prev)
        print("  previewId:", pid or "<none>")
        # any warnings/messages from E*TRADE:
        msgs = (pr.get("messageList") or pr.get("Messages") or {}).get("message") or []
        if isinstance(msgs, dict): msgs = [msgs]
        for m in msgs:
            print("  MSG:", m.get("type"), m.get("code"), "-", m.get("description"))

if __name__ == "__main__":
    main()
