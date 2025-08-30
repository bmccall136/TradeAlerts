# place_stops.py — ARMS REAL STOP ORDERS FOR CURRENT HOLDINGS
from __future__ import annotations
import json, os, math

from services.broker import get_broker
from services.etrade_service import get_positions

SETTINGS = "live_settings.json"

def money(x): 
    try: return f"${float(x):,.2f}"
    except: return str(x)

def main():
    # load settings
    with open(SETTINGS, "r") as f:
        cfg = json.load(f)

    use_trailing = bool(cfg.get("use_trailing_stop", False))
    trail_pct    = float(cfg.get("trailing_stop_pct", 12))
    stop_pct     = float(cfg.get("stop_loss_pct", 5))
    order_term   = "GOOD_UNTIL_CANCEL"  # change if you prefer GFD
    market_sess  = "REGULAR"

    b = get_broker(cfg.get("broker_mode","LIVE"))
    acct = b._account_id_key

    positions = get_positions() or []
    armed = 0

    for p in positions:
        sym  = (p.get("symbol") or "").upper()
        qty  = int(float(p.get("qty") or 0))
        last = float(p.get("last_price") or 0.0)
        if not sym or qty <= 0 or last <= 0:
            continue

        print(f"\n{sym}: qty={qty} last={money(last)}")

        if use_trailing:
            # TRAILING STOP (percent)
            offset_val = float(trail_pct)
            print(f"  placing TRAILING_STOP_PRCT {offset_val:.2f}%")
            prev = b._et.preview_equity_order(
                acct, sym, qty, None, "SELL",
                price_type="TRAILING_STOP_PRCT",
                offset_type="TRAILING_STOP_PRCT",
                offset_value=offset_val,
                order_term=order_term,
                market_session=market_sess,
            )
        else:
            # PLAIN STOP @ X% below last
            stop = round(last * (1.0 - stop_pct/100.0), 2)
            print(f"  placing STOP @ {money(stop)} ({stop_pct:.2f}% below)")
            prev = b._et.preview_equity_order(
                acct, sym, qty, None, "SELL",
                price_type="STOP", stop_price=stop,
                order_term=order_term, market_session=market_sess,
            )

        pr = (prev.get("PreviewOrderResponse")
              or prev.get("PreviewOrderResponseV2") or prev) or {}
        pid = pr.get("previewId") or ((pr.get("PreviewIds") or [{}])[0].get("previewId"))
        if not pid:
            print("  !! no previewId in response; skipping")
            continue

        placed = b._et.place_equity_order(
            acct, sym, qty, None, "SELL", pid,
            price_type=("TRAILING_STOP_PRCT" if use_trailing else "STOP"),
            stop_price=(None if use_trailing else stop),
            offset_type=("TRAILING_STOP_PRCT" if use_trailing else None),
            offset_value=(offset_val if use_trailing else None),
            order_term=order_term, market_session=market_sess,
        )
        print("  ✅ placed:", (placed.get("PlaceOrderResponse") or {}).get("orderId") or "OK")
        armed += 1

    if armed == 0:
        print("\nNo stops placed.")
    else:
        print(f"\nDone. Armed stops for {armed} symbols.")

if __name__ == "__main__":
    main()
