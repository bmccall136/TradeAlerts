import json
import traceback

from services import etrade_service as et

# ----- CONFIGURE YOUR TEST HERE -----
SYMBOL = "ALB"      # pick something small you own, or "ZZZZ" to be safe
QTY    = 1          # tiny qty
ACTION = "SELL"     # or "BUY"
PRICE  = None       # None = MARKET order
PRICE_TYPE = "MARKET"
ORDER_TERM = "GOOD_FOR_DAY"
MARKET_SESSION = "REGULAR"   # or "EXTENDED" if you want to test that
# ------------------------------------


def main():
    print("=== test_order.py starting ===")
    try:
        aid_key = et.account_id_key()
        print(f"[test] account_id_key = {aid_key!r}")

        print("[test] doing PREVIEW…")
        try:
            preview = et.preview_equity_order(
                account_id_key=aid_key,
                symbol=SYMBOL,
                qty=QTY,
                price=PRICE,
                action=ACTION,
                price_type=PRICE_TYPE,
                order_term=ORDER_TERM,
                market_session=MARKET_SESSION,
            )
            print("[test] PREVIEW response:")
            print(json.dumps(preview, indent=2))
        except Exception as e:
            print("\n[test] ERROR during preview_equity_order:")
            print(e)
            traceback.print_exc()
            return

        print("\n[test] doing PLACE…")
        try:
            placed = et.place_equity_order(preview, qty=QTY)
            print("[test] PLACE response:")
            print(json.dumps(placed, indent=2))
        except Exception as e:
            print("\n[test] ERROR during place_equity_order:")
            print(e)
            traceback.print_exc()

    except Exception as outer:
        print("\n[test] FATAL error in script:")
        print(outer)
        traceback.print_exc()


if __name__ == "__main__":
    main()
