
"""
mrna_sell_diag_v5.py — signature-aware preview->place for your etrade_service.

What it fixes:
- Detects preview_equity_order signature by NAMEs (e.g., (symbol, qty, price) vs (action, symbol, qty, price)).
- Detects place_equity_order signature: either expects a preview object (common) or direct params.
- Uses available_to_sell(account_id_key, symbol) for allowed qty.
- Leaves a clear trail of which call-shape it picked.

USAGE:
  py mrna_sell_diag_v5.py                 # show availability & open SELLs
  py mrna_sell_diag_v5.py --sell          # sell all available_to_sell whole shares
  py mrna_sell_diag_v5.py --sell 5        # sell exactly 5 (clamped to available unless --force)
  py mrna_sell_diag_v5.py --sell --force  # clamp to available_to_sell automatically
  py mrna_sell_diag_v5.py --debug         # verbose
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

def available_to_sell(acct_key: str, symbol: str) -> float:
    if hasattr(et, "available_to_sell"):
        try:
            v = et.available_to_sell(acct_key, symbol)
            return _float(v, 0.0)
        except Exception:
            pass
    return 0.0

# ----- Signature-adaptive preview & place -----

def do_preview(acct_key: str, action: str, symbol: str, qty: int, debug=False):
    if not hasattr(et, "preview_equity_order"):
        return None, "no preview_equity_order"

    fn = et.preview_equity_order
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
    except Exception:
        sig, params = None, []

    # Normalize common names
    names = [p.lower() for p in params]

    # Case A: (symbol, qty, price)  => no action/acct_key
    if names == ["symbol", "qty", "price"] or set(["symbol","qty","price"]).issubset(set(names)) and len(names)==3:
        if debug: print("[DBG] preview using (symbol, qty, price)")
        return fn(symbol, qty, "MARKET"), "preview(symbol,qty,price)"

    # Case B: (action, symbol, qty, price)
    if names and names[0]=="action" and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview using (action, symbol, qty, price)")
        return fn(action, symbol, qty, "MARKET"), "preview(action,symbol,qty,price)"

    # Case C: (account_id_key, action, symbol, qty, price)
    if "account_id_key" in names and "action" in names and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview using (account_id_key, action, symbol, qty, price)")
        # positional if order matches, else kwargs
        try:
            if names[:5] == ["account_id_key","action","symbol","qty","price"]:
                return fn(acct_key, action, symbol, qty, "MARKET"), "preview(acct,action,symbol,qty,price)"
        except Exception:
            pass
        return fn(account_id_key=acct_key, action=action, symbol=symbol, qty=qty, price="MARKET"), "preview(kwargs acct/action/symbol/qty/price)"

    # Case D: kwargs variant (accountIdKey/account_id_key + orderAction/action + priceType/price + quantity/qty)
    kw = {}
    if "account_id_key" in names: kw["account_id_key"] = acct_key
    if "accountidkey" in names: kw["accountIdKey"] = acct_key
    if "action" in names or "orderaction" in names: kw["action" if "action" in names else "orderAction"] = action
    if "symbol" in names: kw["symbol"] = symbol
    if "quantity" in names or "qty" in names: kw["quantity" if "quantity" in names else "qty"] = qty
    if "ordertype" in names or "price" in names or "pricetype" in names:
        if "ordertype" in names: kw["orderType"] = "MARKET"
        elif "pricetype" in names: kw["priceType"] = "MARKET"
        else: kw["price"] = "MARKET"
    if kw:
        if debug: print("[DBG] preview using kwargs:", kw)
        return fn(**kw), "preview(kwargs-mapped)"

    # Fallback: try simplest 3-arg
    try:
        if debug: print("[DBG] preview fallback (symbol, qty, price)")
        return fn(symbol, qty, "MARKET"), "preview(fallback symbol,qty,price)"
    except Exception as e:
        if debug: print("[DBG] preview fallback failed:", e)

    return None, "preview(all_failed)"

def do_place(acct_key: str, action: str, symbol: str, qty: int, preview_obj: dict | None, debug=False):
    if not hasattr(et, "place_equity_order"):
        return None, "no place_equity_order"

    fn = et.place_equity_order
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
    except Exception:
        sig, params = None, []

    names = [p.lower() for p in params]

    # If function expects a preview object (common adapters):
    if len(names)==1 and names[0] in ("preview","order","payload","data"):
        if preview_obj is None:
            return None, "place(expected preview but preview_obj is None)"
        if debug: print("[DBG] place using single preview object param:", names[0])
        return fn(preview_obj), "place(preview-object)"

    # If expects (account_id_key, preview)
    if len(names)==2 and names[0] in ("account_id_key","accountidkey") and names[1] in ("preview","order","payload","data"):
        if preview_obj is None:
            return None, "place(expected preview but preview_obj is None)"
        if debug: print("[DBG] place using (account_id_key, preview)")
        kw = { names[0]: acct_key, names[1]: preview_obj }
        return fn(**kw), "place(acct+preview)"

    # Direct params variants (less common)
    # a) (action, symbol, qty, price)
    if names and names[0]=="action" and "symbol" in names and "qty" in names and ("price" in names or "ordertype" in names or "pricetype" in names):
        if "price" in names:
            if debug: print("[DBG] place using (action, symbol, qty, price)")
            return fn(action, symbol, qty, "MARKET"), "place(action,symbol,qty,price)"
        # kwargs flavor
        kwargs = {"action": action, "symbol": symbol, "qty": qty}
        if "ordertype" in names: kwargs["orderType"]="MARKET"
        elif "pricetype" in names: kwargs["priceType"]="MARKET"
        if debug: print("[DBG] place using kwargs:", kwargs)
        return fn(**kwargs), "place(kwargs action/symbol/qty/market)"

    # b) (symbol, qty, price)
    if names == ["symbol","qty","price"] or set(["symbol","qty","price"]).issubset(set(names)) and len(names)==3:
        if debug: print("[DBG] place using (symbol, qty, price)")
        return fn(symbol, qty, "MARKET"), "place(symbol,qty,price)"

    # c) dictionary payload as last resort (rare)
    payloads = [
        {"accountIdKey": acct_key, "orderAction": action, "symbol": symbol, "quantity": qty, "priceType": "MARKET"},
        {"account_id_key": acct_key, "action": action, "symbol": symbol, "quantity": qty, "orderType": "MARKET"},
        {"account": acct_key, "side": action, "symbol": symbol, "qty": qty, "type": "MARKET"},
    ]
    for i,p in enumerate(payloads, 1):
        try:
            if debug: print(f"[DBG] place dict#{i} trying:", p)
            return fn(p), f"place(dict#{i})"
        except Exception as e:
            if debug: print(f"[DBG] place dict#{i} failed:", e)

    return None, "place(all_failed)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="market sell (auto = all available_to_sell)")
    ap.add_argument("--force", action="store_true", help="if requested qty > available, clamp to available_to_sell")
    ap.add_argument("--debug", action="store_true", help="verbose")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    avail = available_to_sell(acct_key, SYMBOL)
    print(f"[POS] {SYMBOL}: available_to_sell={avail}")

    # Show open SELLs that could reserve qty
    opens = list_open_orders_for_symbol(acct_key, SYMBOL)
    if opens:
        print(f"[ORD] {len(opens)} open order(s) for {SYMBOL}:")
        for o in opens:
            side = (o.get("orderAction") or o.get("orderType") or "").upper()
            oid  = o.get("orderId") or o.get("orderNumber") or o.get("orderIdString") or o.get("orderid")
            st   = (o.get("orderStatus") or o.get("status") or "").upper()
            print(f"  - {oid} {side} status={st}")
    else:
        print("[ORD] No open orders for", SYMBOL)

    if args.sell is None:
        return

    # Determine qty
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
        print("[SELL] Available is fractional only; route likely disallows fractional sells.")
        return

    # Preview then place
    prev, how_prev = do_preview(acct_key, "SELL", SYMBOL, qty_int, debug=args.debug)
    if prev is not None:
        print(f"[PREVIEW] via {how_prev} -> ok")
        print(_fmt(prev))
    else:
        print(f"[PREVIEW] {how_prev}")

    resp, how_place = do_place(acct_key, "SELL", SYMBOL, qty_int, preview_obj=prev, debug=args.debug)
    if resp is not None:
        print(f"[SELL] via {how_place} -> ok")
        print(_fmt(resp))
    else:
        print(f"[SELL] {how_place}")

if __name__ == "__main__":
    main()
