# _sell_preview_probe.py
import json, sys, traceback, os
os.environ.setdefault("ETRADE_ENV", "production")

try:
    from services import etrade_service as et
except Exception as e:
    print("IMPORT FAIL:", e)
    sys.exit(2)

def choose_first_holding(p):
    # tolerate many shapes
    pr = (p or {}).get("PortfolioResponse", {})
    aps = pr.get("AccountPortfolio") or []
    if isinstance(aps, dict): aps = [aps]
    for ap in aps:
        positions = (
            ap.get("Position") or ap.get("position") or
            ap.get("Positions") or ap.get("positions") or []
        )
        if isinstance(positions, dict): positions = [positions]
        for row in positions:
            inst = row.get("instrument") or row.get("Instrument") or {}
            sym  = (inst.get("symbol") or row.get("symbol") or "").upper()
            qty  = (
                row.get("longQty") or row.get("longQuantity") or
                row.get("qty") or row.get("quantity") or
                row.get("positionQty") or row.get("positionQuantity") or 0
            )
            try:
                if sym and float(qty) > 0:
                    return sym, int(float(qty))
            except Exception:
                continue
    return None, None

def main():
    force_symbol = None  # e.g., "TXT"
    qty = 1

    acct = et.get_primary_account_key()
    print("[ACCT]", acct)

    pos = et.get_positions(acct)
    sym, held = choose_first_holding(pos) if not force_symbol else (force_symbol, None)
    if not sym:
        print("No eligible holdings found to preview.")
        return 0

    if held is not None and held < qty:
        qty = held

    print(f"[PREVIEW] SELL MARKET {sym} x{qty}")
    try:
        # Prefer the same preview path your earlier probe used
        # If your wrapper exposes a helper, keep this call name:
        #
        #   et.preview_equity_order(acct, symbol, qty, orderAction='SELL', priceType='MARKET')
        #
        # If your signature differs, adapt the kwargs accordingly.
        resp = et.preview_equity_order(
            account_id_key=acct,
            symbol=sym,
            quantity=qty,
            orderAction="SELL",
            priceType="MARKET",
        )
        print("RAW PREVIEW:", json.dumps(resp, indent=2))
        # try to surface any error info if present
        err = (resp or {}).get("Error") or (resp or {}).get("error")
        if err:
            print("[ERROR CODE]", err.get("code"), "-", err.get("message"))
            return 1
        print("[OK] Preview succeeded.")
        return 0
    except Exception as e:
        print("[EXC]", e)
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    sys.exit(main())
