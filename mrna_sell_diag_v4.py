
"""
mrna_sell_diag_v4.py — adapts to your etrade_service signatures at runtime.

USAGE:
  py mrna_sell_diag_v4.py                 # show availability & open SELLs
  py mrna_sell_diag_v4.py --sell          # sell all available_to_sell whole shares
  py mrna_sell_diag_v4.py --sell 5        # sell exactly 5 (clamped to available unless --force)
  py mrna_sell_diag_v4.py --sell --force  # clamp to available_to_sell automatically
  py mrna_sell_diag_v4.py --debug         # verbose
"""

import sys, json, argparse, inspect, os
from typing import Any, Dict, List

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from services import etrade_service as et

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
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k: return str(k)
        except Exception:
            pass
    if hasattr(et, "account_id_key"):
        k = getattr(et, "account_id_key")
        if k: return str(k)
    raise RuntimeError("Could not determine account_id_key")

def get_positions_zero_arg(debug=False):
    if not hasattr(et, "get_positions"):
        return None
    try:
        sig = inspect.signature(et.get_positions)
        if len(sig.parameters) == 0:
            return et.get_positions()
        else:
            if debug:
                print("[DBG] get_positions has params; skipping to avoid wrong call:", sig)
            return None
    except Exception as e:
        if debug:
            print("[DBG] get_positions() call failed:", e)
        return None

def get_position_row(symbol: str, debug=False) -> Dict[str, Any] | None:
    pos = get_positions_zero_arg(debug=debug)
    if pos is None:
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

def available_to_sell(acct_key: str, symbol: str, debug=False) -> float:
    if hasattr(et, "available_to_sell"):
        try:
            v = et.available_to_sell(acct_key, symbol)
            return _float(v, 0.0)
        except Exception as e:
            if debug: print("[DBG] available_to_sell helper failed:", e)
    p = get_position_row(symbol, debug=debug)
    if not p: return 0.0
    for k in ("quantityAvailable","qtyAvailable","availableQuantity","available"):
        if k in p: return _float(p.get(k), 0.0)
    lots = p.get("lots") or p.get("lot") or []
    if isinstance(lots, dict): lots = [lots]
    avail = 0.0
    for lot in lots:
        for k in ("availableQty","qtyAvailable","quantityAvailable"):
            if k in lot: avail += _float(lot.get(k), 0.0)
    if avail > 0: return avail
    for k in ("longQuantity","quantity","qty","positionQuantity"):
        if k in p: return max(0.0, _float(p.get(k), 0.0))
    return 0.0

def list_open_orders_for_symbol(acct_key: str, symbol: str) -> List[Dict[str, Any]]:
    fn = None
    if hasattr(et, "get_open_orders"): fn = et.get_open_orders
    elif hasattr(et, "list_open_orders"): fn = et.list_open_orders
    if not fn:
        return []
    try:
        orders = fn(acct_key) or []
    except Exception:
        try:
            orders = fn() or []
        except Exception:
            return []
    out = []
    symu = symbol.upper()
    for o in orders:
        try:
            legs = o.get("orderDetail") or o.get("orderDetails") or []
            if isinstance(legs, dict): legs = [legs]
            found = False
            for leg in legs:
                inst = leg.get("instrument") or []
                if isinstance(inst, dict): inst = [inst]
                for i in inst:
                    s = (i.get("symbol") or i.get("productSymbol") or i.get("symbolDescription") or "").upper()
                    if s == symu: found = True; break
                if found: break
            if not legs and o.get("symbol"):
                if str(o["symbol"]).upper() == symu:
                    found = True
            if found: out.append(o)
        except Exception:
            pass
    return out

def _try_preview(acct_key, action, symbol, qty, debug=False):
    if not hasattr(et, "preview_equity_order"):
        return None, "no preview_equity_order"
    fn = et.preview_equity_order
    sig = None
    try:
        sig = inspect.signature(fn)
    except Exception:
        pass

    try:
        if sig and len(sig.parameters) >= 5:
            return fn(acct_key, action, symbol, qty, "MARKET"), "preview(positional)"
    except Exception as e:
        if debug: print("[DBG] preview positional failed:", e)

    try:
        return fn(account_id_key=acct_key, action=action, symbol=symbol, quantity=qty, orderType="MARKET"), "preview(kwargs)"
    except Exception as e:
        if debug: print("[DBG] preview kwargs failed:", e)

    payloads = [
        {"account_id_key": acct_key, "action": action, "symbol": symbol, "quantity": qty, "orderType": "MARKET"},
        {"accountIdKey": acct_key, "orderAction": action, "symbol": symbol, "quantity": qty, "priceType": "MARKET"},
        {"account": acct_key, "side": action, "symbol": symbol, "qty": qty, "type": "MARKET"},
    ]
    for i,p in enumerate(payloads, 1):
        try:
            return fn(p), f"preview(dict#{i})"
        except Exception as e:
            if debug: print(f"[DBG] preview dict#{i} failed:", e)

    return None, "preview(all_failed)"

def _try_place(acct_key, action, symbol, qty, debug=False):
    if not hasattr(et, "place_equity_order"):
        raise RuntimeError("etrade_service.place_equity_order missing")
    fn = et.place_equity_order
    sig = None
    try:
        sig = inspect.signature(fn)
    except Exception:
        pass

    try:
        if sig and len(sig.parameters) >= 5:
            return fn(acct_key, action, symbol, qty, "MARKET"), "place(positional)"
    except Exception as e:
        if debug: print("[DBG] place positional failed:", e)

    try:
        return fn(account_id_key=acct_key, action=action, symbol=symbol, quantity=qty, orderType="MARKET"), "place(kwargs)"
    except Exception as e:
        if debug: print("[DBG] place kwargs failed:", e)

    payloads = [
        {"account_id_key": acct_key, "action": action, "symbol": symbol, "quantity": qty, "orderType": "MARKET"},
        {"accountIdKey": acct_key, "orderAction": action, "symbol": symbol, "quantity": qty, "priceType": "MARKET"},
        {"account": acct_key, "side": action, "symbol": symbol, "qty": qty, "type": "MARKET"},
    ]
    for i,p in enumerate(payloads, 1):
        try:
            return fn(p), f"place(dict#{i})"
        except Exception as e:
            if debug: print(f"[DBG] place dict#{i} failed:", e)

    raise RuntimeError("No compatible calling convention for place_equity_order")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="market sell (auto = all available_to_sell)")
    ap.add_argument("--force", action="store_true", help="if requested qty > available, clamp to available_to_sell")
    ap.add_argument("--debug", action="store_true", help="verbose")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    pos = get_position_row(SYMBOL, debug=args.debug)
    total = 0.0
    if pos:
        total = max(0.0, float(pos.get("longQuantity") or pos.get("quantity") or pos.get("qty") or 0.0))

    avail = available_to_sell(acct_key, SYMBOL, debug=args.debug)
    print(f"[POS] {SYMBOL}: total={total}  available_to_sell={avail}")

    open_sells = list_open_orders_for_symbol(acct_key, SYMBOL)
    if open_sells:
        print(f"[ORD] {len(open_sells)} open order(s) for {SYMBOL}:")
        for o in open_sells:
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            oid  = o.get("orderId") or o.get("orderNumber") or o.get("orderIdString") or o.get("orderid")
            st   = (o.get("orderStatus") or o.get("status") or "").upper()
            print(f"  - {oid} {side} status={st}")
    else:
        print("[ORD] No open orders for", SYMBOL)

    if args.sell is None:
        return

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
            print(f"[SELL] Requested qty {qty} exceeds available {avail}. Use --force or cancel reserving orders.")
            return

    qty_int = int(qty)
    if qty_int <= 0:
        print("[SELL] Available is fractional only; most routes disallow fractional sells.")
        return

    prev, how_prev = _try_preview(acct_key, "SELL", SYMBOL, qty_int, debug=args.debug)
    if prev is not None:
        print(f"[PREVIEW] via {how_prev} -> ok")
        print(_fmt(prev))
    else:
        print(f"[PREVIEW] {how_prev}")

    try:
        resp, how = _try_place(acct_key, "SELL", SYMBOL, qty_int, debug=args.debug)
        print(f"[SELL] via {how} -> ok")
        print(_fmt(resp))
    except Exception as e:
        print("[SELL] All placement attempts failed:", e)

if __name__ == "__main__":
    main()
