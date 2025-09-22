
"""
mrna_sell_diag_v3.py — tailored for etrade_service that uses account_id_key + get_positions/get_open_orders/place_equity_order.

USAGE (from C:\\TradeAlerts):
  py mrna_sell_diag_v3.py                 # show account key, MRNA totals/available, open SELLs
  py mrna_sell_diag_v3.py --sell          # market sell ALL *available_to_sell* shares
  py mrna_sell_diag_v3.py --sell 5        # market sell exactly 5
  py mrna_sell_diag_v3.py --force         # when qty > available, clamp to available_to_sell
  py mrna_sell_diag_v3.py --debug         # print raw payload snippets while probing

Notes:
- This version DOES NOT cancel orders (your etrade_service has no cancel_* function). It will list SELL orders and their ids so you can cancel in E*TRADE if needed.
- Uses functions detected in your module listing: get_account_id_key, get_positions, get_open_orders, available_to_sell, place_equity_order.
"""

import sys, json, argparse
from typing import Any, Dict, List

import os
HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from services import etrade_service as et
except Exception as e:
    print("[FATAL] Could not import services.etrade_service:", e)
    sys.exit(1)

SYMBOL = "MRNA"

def _fmt(o: Any) -> str:
    try:
        return json.dumps(o, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(o)

def _float(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d

def get_acct_key() -> str:
    # Prefer function
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k: return str(k)
        except Exception as e:
            print("[DBG] get_account_id_key() failed:", e)
    # Fallback constant
    if hasattr(et, "account_id_key"):
        k = getattr(et, "account_id_key")
        if k: return str(k)
    raise RuntimeError("Could not determine account_id_key (need get_account_id_key() or account_id_key).")

def list_open_orders_for_symbol(account_id_key: str, symbol: str) -> List[Dict[str, Any]]:
    orders = []
    fn = None
    if hasattr(et, "get_open_orders"):
        fn = et.get_open_orders
    elif hasattr(et, "list_open_orders"):
        fn = et.list_open_orders
    if fn:
        try:
            orders = fn(account_id_key) or []
        except Exception as e:
            print("[WARN] get/list_open_orders failed:", e)
            return []
    out = []
    symu = symbol.upper()
    for o in orders:
        try:
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            # Find all symbols in the order legs
            legs = o.get("orderDetail") or o.get("orderDetails") or []
            if isinstance(legs, dict): legs = [legs]
            found = False
            for leg in legs:
                inst = leg.get("instrument") or []
                if isinstance(inst, dict): inst = [inst]
                for i in inst:
                    s = (i.get("symbol") or i.get("productSymbol") or i.get("symbolDescription") or "").upper()
                    if s == symu:
                        found = True; break
                if found: break
            if not legs and o.get("symbol"):
                if str(o["symbol"]).upper() == symu:
                    found = True
            if found: out.append(o)
        except Exception:
            pass
    return out

def get_position_row(account_id_key: str, symbol: str, debug=False) -> Dict[str, Any] | None:
    pos = None
    try:
        pos = et.get_positions(account_id_key)
    except Exception as e:
        print("[WARN] get_positions failed:", e)
        return None
    items = pos
    if isinstance(items, dict):
        for k in ("positions","Position","securitiesAccountPositions","data","items","portfolioPositions"):
            if k in items and isinstance(items[k], list):
                items = items[k]; break
    if not isinstance(items, list):
        items = [items]
    symu = symbol.upper()
    for p in items:
        try:
            sym = (p.get("symbol") or p.get("Product",{}).get("symbol") or p.get("securitySymbol","")).upper()
            if sym == symu:
                if debug:
                    print("[DBG] Position row raw:\n", _fmt(p))
                return p
        except Exception:
            continue
    return None

def available_to_sell(account_id_key: str, symbol: str) -> float:
    # Prefer helper if present
    if hasattr(et, "available_to_sell"):
        try:
            v = et.available_to_sell(account_id_key, symbol)
            return _float(v, 0.0)
        except Exception as e:
            print("[DBG] available_to_sell helper failed:", e)
    # Fallback derive from position
    p = get_position_row(account_id_key, symbol)
    if not p: return 0.0
    for k in ("quantityAvailable","qtyAvailable","availableQuantity","available"):
        if k in p: return _float(p.get(k), 0.0)
    lots = p.get("lots") or p.get("lot") or []
    if isinstance(lots, dict): lots = [lots]
    avail = 0.0
    for lot in lots:
        for k in ("availableQty","qtyAvailable","quantityAvailable"):
            if k in lot:
                avail += _float(lot.get(k), 0.0)
    if avail > 0: return avail
    for k in ("longQuantity","quantity","qty","positionQuantity"):
        if k in p: return max(0.0, _float(p.get(k), 0.0))
    return 0.0

def place_market_sell(account_id_key: str, symbol: str, qty: float) -> Dict[str, Any]:
    if qty <= 0:
        raise ValueError("qty must be > 0")
    if not hasattr(et, "place_equity_order"):
        raise RuntimeError("etrade_service.place_equity_order is missing; can't place market sell.")
    # Your adapter usually takes (account_id_key, action, symbol, quantity, orderType)
    return et.place_equity_order(account_id_key, "SELL", symbol, qty, "MARKET")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="market sell (auto = all available_to_sell)")
    ap.add_argument("--force", action="store_true", help="if requested qty > available, clamp to available_to_sell")
    ap.add_argument("--debug", action="store_true", help="print extra raw payloads")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    pos = get_position_row(acct_key, SYMBOL, debug=args.debug)
    total = 0.0
    if pos:
        total = max(0.0, 
            float(pos.get("longQuantity") or pos.get("quantity") or pos.get("qty") or 0.0)
        )
    avail = available_to_sell(acct_key, SYMBOL)

    print(f"[POS] {SYMBOL}: total={total}  available_to_sell={avail}")

    # List SELL orders that could be reserving qty
    open_sells = list_open_orders_for_symbol(acct_key, SYMBOL)
    if open_sells:
        print(f"[ORD] {len(open_sells)} open order(s) for {SYMBOL}:")
        for o in open_sells:
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            oid  = o.get("orderId") or o.get("orderNumber") or o.get("orderIdString") or o.get("orderid")
            st   = (o.get("orderStatus") or o.get("status") or "").upper()
            print(f"  - {oid} {side} status={st}")
        print("      NOTE: This adapter has no cancel() helper. Cancel in E*TRADE if these are reserving quantity.")
    else:
        print("[ORD] No open orders for", SYMBOL)

    if args.sell is None:
        return

    # Determine qty to sell
    if args.sell == "__AUTO__":
        qty = avail
    else:
        try:
            qty = float(args.sell)
        except Exception:
            print("[SELL] Invalid qty; use a positive number or omit to auto-sell available.")
            return

    if qty <= 0:
        print("[SELL] Aborting: qty <= 0 (nothing available).")
        return

    if qty > avail:
        if args.force:
            print(f"[SELL] Requested qty {qty} > available {avail}; clamping to available due to --force.")
            qty = avail
        else:
            print(f"[SELL] Requested qty {qty} exceeds available {avail}. Either cancel reserving orders or use --force.")
            return

    # Floor to whole shares (most equity routes require integers)
    qty_int = int(qty)
    if qty_int <= 0:
        print("[SELL] Available is fractional only; adapter likely disallows fractional sells.")
        return

    print(f"[SELL] Placing MARKET sell: {SYMBOL} qty={qty_int}")
    try:
        resp = place_market_sell(acct_key, SYMBOL, qty_int)
        print("[SELL] Response:")
        print(_fmt(resp))
    except Exception as e:
        print("[SELL] Order placement failed:", e)

if __name__ == "__main__":
    main()
