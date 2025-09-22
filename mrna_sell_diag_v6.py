
"""
mrna_sell_diag_v6.py — SELL MRNA using your adapter's preview->place flow with a numeric price.

Why v6?
- Your preview_equity_order() requires a numeric "price" (it tried to float("MARKET")).
- This version fetches the current quote and uses a limit price derived from bid (default) or last.
- It then places using the preview object (or account_id_key + preview), depending on signature.

USAGE (from C:\TradeAlerts):
  python mrna_sell_diag_v6.py --sell                 # sell all available (limit @ bid - $0.02)
  python mrna_sell_diag_v6.py --sell 4               # sell 4 shares
  python mrna_sell_diag_v6.py --sell --use-last      # price from LAST instead of BID
  python mrna_sell_diag_v6.py --offset 0.05          # adjust limit: price = source - 0.05
  python mrna_sell_diag_v6.py --force                # clamp requested qty to available_to_sell
  python mrna_sell_diag_v6.py --debug                # verbose
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

def available_to_sell(acct_key: str, symbol: str) -> float:
    if hasattr(et, "available_to_sell"):
        try:
            v = et.available_to_sell(acct_key, symbol)
            return _float(v, 0.0)
        except Exception:
            pass
    return 0.0

def fetch_bid_last(symbol: str) -> Dict[str, float]:
    """
    Returns {"bid": bid_price_or_0, "last": last_price_or_0}
    """
    out = {"bid": 0.0, "last": 0.0}
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            # try common keys
            for k in ("bid","Bid","bidPrice","bidRealTime","bid64","bestBid","BidPrice"):
                if k in q:
                    out["bid"] = _float(q[k], out["bid"])
            for k in ("last","Last","lastPrice","lastTrade","lastRealTime","close","LastPrice"):
                if k in q:
                    out["last"] = _float(q[k], out["last"])
            # nested?
            if out["bid"] == 0.0:
                for v in q.values():
                    if isinstance(v, dict):
                        for k in ("bid","bidPrice","bestBid"):
                            if k in v:
                                out["bid"] = _float(v[k], out["bid"])
                    if out["bid"]>0: break
            if out["last"] == 0.0:
                for v in q.values():
                    if isinstance(v, dict):
                        for k in ("last","lastPrice","lastTrade","close"):
                            if k in v:
                                out["last"] = _float(v[k], out["last"])
                    if out["last"]>0: break
    except Exception:
        pass
    return out

def preview_sell(acct_key: str, symbol: str, qty: int, limit_price: float, debug=False):
    """
    Call preview_equity_order using the signature it advertises.
    Returns (preview_obj, how_used).
    """
    if not hasattr(et, "preview_equity_order"):
        return None, "no preview_equity_order"
    fn = et.preview_equity_order
    try:
        sig = inspect.signature(fn); names = [p.lower() for p in sig.parameters.keys()]
    except Exception:
        sig, names = None, []

    # Preferred shapes based on your logs:
    # 1) (symbol, qty, price)
    if names == ["symbol","qty","price"] or (set(["symbol","qty","price"]).issubset(set(names)) and len(names)==3):
        if debug: print("[DBG] preview -> (symbol, qty, price)")
        return fn(symbol, qty, float(limit_price)), "preview(symbol,qty,price)"

    # 2) (action, symbol, qty, price)
    if names and names[0]=="action" and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview -> (action, symbol, qty, price)")
        return fn("SELL", symbol, qty, float(limit_price)), "preview(action,symbol,qty,price)"

    # 3) (account_id_key, action, symbol, qty, price) or kwargs equivalent
    if "account_id_key" in names and "action" in names and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview -> (account_id_key, action, symbol, qty, price)")
        try:
            if names[:5] == ["account_id_key","action","symbol","qty","price"]:
                return fn(acct_key, "SELL", symbol, qty, float(limit_price)), "preview(acct,action,symbol,qty,price)"
        except Exception as e:
            if debug: print("[DBG] preview positional failed:", e)
        return fn(account_id_key=acct_key, action="SELL", symbol=symbol, qty=qty, price=float(limit_price)), "preview(kwargs acct/action/symbol/qty/price)"

    # 4) kwargs fallback mappings
    kw = {}
    if "account_id_key" in names: kw["account_id_key"] = acct_key
    if "accountidkey" in names: kw["accountIdKey"] = acct_key
    if "action" in names or "orderaction" in names: kw["action" if "action" in names else "orderAction"] = "SELL"
    if "symbol" in names: kw["symbol"] = symbol
    if "quantity" in names or "qty" in names: kw["quantity" if "quantity" in names else "qty"] = qty
    if "price" in names: kw["price"] = float(limit_price)
    if kw:
        if debug: print("[DBG] preview -> kwargs", kw)
        return fn(**kw), "preview(kwargs-mapped)"

    # last resort
    if debug: print("[DBG] preview -> fallback (symbol, qty, price)")
    return fn(symbol, qty, float(limit_price)), "preview(fallback symbol,qty,price)"

def place_from_preview(acct_key: str, preview_obj: dict, debug=False):
    """
    Call place_equity_order using preview object.
    Supports signatures: (preview), (account_id_key, preview), (payload), etc.
    """
    if not hasattr(et, "place_equity_order"):
        return None, "no place_equity_order"
    fn = et.place_equity_order
    try:
        sig = inspect.signature(fn); names = [p.lower() for p in sig.parameters.keys()]
    except Exception:
        sig, names = None, []

    # (preview) only
    if len(names)==1 and names[0] in ("preview","order","payload","data"):
        if debug: print("[DBG] place -> single preview param:", names[0])
        return fn(preview_obj), "place(preview-object)"

    # (account_id_key, preview)
    if len(names)==2 and names[0] in ("account_id_key","accountidkey") and names[1] in ("preview","order","payload","data"):
        if debug: print("[DBG] place -> (account_id_key, preview)")
        return fn(**{names[0]: acct_key, names[1]: preview_obj}), "place(acct+preview)"

    # kwargs fallback
    try:
        if debug: print("[DBG] place -> kwargs fallback")
        return fn(preview=preview_obj), "place(kwargs preview=)"
    except Exception:
        pass

    return None, "place(all_failed)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="market sell (auto = all available_to_sell)")
    ap.add_argument("--force", action="store_true", help="if requested qty > available, clamp to available_to_sell")
    ap.add_argument("--offset", type=float, default=0.02, help="subtract this from price source (default $0.02)")
    ap.add_argument("--use-last", action="store_true", help="use LAST instead of BID for limit price source")
    ap.add_argument("--debug", action="store_true", help="verbose logs")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    avail = available_to_sell(acct_key, SYMBOL)
    print(f"[POS] {SYMBOL}: available_to_sell={avail}")

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

    # Compute a sane limit price
    q = fetch_bid_last(SYMBOL)
    src = "last" if args.use_last else "bid"
    base = q.get(src, 0.0)
    if base <= 0 and src == "bid":
        base = q.get("last", 0.0)
        src = "last"
    price = max(0.01, base - args.offset)  # sell slightly through the bid for fill
    print(f"[QUOTE] {SYMBOL} {src.upper()}={base:.2f} -> limit={price:.2f} (offset {args.offset:.2f})")

    # Preview then place
    try:
        prev, how_prev = preview_sell(acct_key, SYMBOL, qty_int, price, debug=args.debug)
    except Exception as e:
        print("[PREVIEW] failed:", e)
        return
    if prev is None:
        print(f"[PREVIEW] {how_prev}")
        return
    print(f"[PREVIEW] via {how_prev} -> ok")
    # Optionally show compact preview info
    try:
        print(_fmt(prev))
    except Exception:
        pass

    try:
        resp, how_place = place_from_preview(acct_key, prev, debug=args.debug)
    except Exception as e:
        print("[SELL] place failed:", e)
        return
    if resp is None:
        print(f"[SELL] {how_place}")
        return
    print(f"[SELL] via {how_place} -> ok")
    print(_fmt(resp))

if __name__ == "__main__":
    main()
