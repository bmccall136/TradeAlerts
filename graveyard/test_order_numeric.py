# --- test_order_numeric.py ---
import json, traceback
from services import etrade_service as et

print("=== test_order_numeric.py starting ===")

try:
    ident = et.account_identity() or {}
    aid_num = ident.get("account_id")
    aid_key = ident.get("account_id_key")

    if not aid_num:
        raise RuntimeError("No numeric account_id found in account_identity().")

    print(f"[test] numeric account_id = {aid_num!r}")
    print(f"[test] account_id_key     = {aid_key!r}")

    # ----- CONFIGURE YOUR TEST HERE -----
    symbol = "ALB"        # pick something
    qty    = 1            # tiny qty
    action = "SELL"       # or BUY
    price  = None         # MARKET ORDER
    # -------------------------------------

    print("[test] doing PREVIEW...")

    # force PREVIEW using NUMERIC account ID
    preview = et.preview_equity_order(
        account_id_key=aid_num,   # <<<<<< numeric ID here
        symbol=symbol,
        qty=qty,
        price=price,
        action=action,
        price_type="MARKET",
        order_term="GOOD_FOR_DAY",
        market_session="REGULAR",
    )

    print("[test] PREVIEW response:")
    print(json.dumps(preview, indent=2))

    print("\n[test] doing PLACE...")

    try:
        # PLACE **also forced to use numeric account ID**
        placed = et.place_equity_order(
            preview,
            qty=qty,
            use_numeric_id=True   # optional helper if needed
        )
        print("[test] PLACE response:")
        print(json.dumps(placed, indent=2))

    except Exception as e:
        print("[test] ERROR during place_equity_order:")
        print(e)
        traceback.print_exc()

except Exception as outer:
    print("[test] FATAL error in script:")
    print(outer)
    traceback.print_exc()
