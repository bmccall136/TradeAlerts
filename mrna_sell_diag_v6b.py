
"""
mrna_sell_diag_v6b.py — same as v6, but pulls price from multiple quote helpers and nested fields (All/ExtendedHourQuoteDetail).

USAGE:
  python mrna_sell_diag_v6b.py --sell --debug
  python mrna_sell_diag_v6b.py --sell --use-last
  python mrna_sell_diag_v6b.py --sell --offset 0.05
  python mrna_sell_diag_v6b.py --sell 4 --force
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

def _f(x, d=0.0):
    try: return float(x)
    except Exception: return d

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
        try: return _f(et.available_to_sell(acct_key, symbol), 0.0)
        except Exception: pass
    return 0.0

def best_quote(symbol: str, debug=False) -> Dict[str, float]:
    out = {"bid": 0.0, "last": 0.0}
    # fetch_etrade_quote
    try:
        q = et.fetch_etrade_quote(symbol)
        if debug and isinstance(q, dict): print("[DBG] fetch_etrade_quote keys:", list(q.keys()))
        if isinstance(q, dict):
            out["bid"] = max(out["bid"], _f(q.get("bid") or q.get("bidPrice") or q.get("bestBid"), 0.0))
            out["last"] = max(out["last"], _f(q.get("last") or q.get("lastPrice") or q.get("lastTrade") or q.get("close"), 0.0))
            # nested "All"
            ALL = q.get("All") if isinstance(q.get("All"), dict) else None
            if ALL:
                out["bid"]  = max(out["bid"], _f(ALL.get("bid") or ALL.get("bidPrice") or ALL.get("bestBid"), 0.0))
                out["last"] = max(out["last"], _f(ALL.get("lastTrade") or ALL.get("lastPrice") or ALL.get("close"), 0.0))
            # nested "ExtendedHourQuoteDetail"
            EHD = q.get("ExtendedHourQuoteDetail") if isinstance(q.get("ExtendedHourQuoteDetail"), dict) else None
            if EHD:
                out["bid"]  = max(out["bid"], _f(EHD.get("bid") or EHD.get("bidPrice") or EHD.get("bestBid"), 0.0))
                out["last"] = max(out["last"], _f(EHD.get("lastTrade") or EHD.get("lastPrice") or EHD.get("close"), 0.0))
    except Exception:
        pass

    # get_quote -> QuoteResponse.QuoteData[0].All / ExtendedHourQuoteDetail
    try:
        g = et.get_quote(symbol)
        if isinstance(g, dict):
            QR = g.get("QuoteResponse") or g.get("quoteResponse") or {}
            qd = None
            if isinstance(QR, dict):
                qd = QR.get("QuoteData") or QR.get("quoteData")
                if isinstance(qd, list) and qd:
                    qd = qd[0]
            if isinstance(qd, dict):
                ALL = qd.get("All") or qd.get("all") or {}
                EHD = qd.get("ExtendedHourQuoteDetail") or qd.get("extendedHourQuoteDetail") or {}
                out["bid"]  = max(out["bid"], _f(ALL.get("bid") or ALL.get("bidPrice") or ALL.get("bestBid"), 0.0))
                out["last"] = max(out["last"], _f(ALL.get("lastTrade") or ALL.get("lastPrice") or ALL.get("close"), 0.0))
                out["bid"]  = max(out["bid"], _f(EHD.get("bid") or EHD.get("bidPrice") or EHD.get("bestBid"), 0.0))
                out["last"] = max(out["last"], _f(EHD.get("lastTrade") or EHD.get("lastPrice") or EHD.get("close"), 0.0))
    except Exception:
        pass

    # get_quotes_map / get_quotes
    for helper in ("get_quotes_map","get_quotes"):
        try:
            fn = getattr(et, helper)
            val = fn([symbol])
            if isinstance(val, dict):
                for v in val.values():
                    if isinstance(v, dict):
                        ALL = v.get("All") or {}
                        EHD = v.get("ExtendedHourQuoteDetail") or {}
                        out["bid"]  = max(out["bid"], _f(ALL.get("bid") or ALL.get("bidPrice") or ALL.get("bestBid"), 0.0))
                        out["last"] = max(out["last"], _f(ALL.get("lastTrade") or ALL.get("lastPrice") or ALL.get("close"), 0.0))
                        out["bid"]  = max(out["bid"], _f(EHD.get("bid") or EHD.get("bidPrice") or EHD.get("bestBid"), 0.0))
                        out["last"] = max(out["last"], _f(EHD.get("lastTrade") or EHD.get("lastPrice") or EHD.get("close"), 0.0))
            elif isinstance(val, list) and val:
                v = val[0]
                if isinstance(v, dict):
                    ALL = v.get("All") or {}
                    EHD = v.get("ExtendedHourQuoteDetail") or {}
                    out["bid"]  = max(out["bid"], _f(ALL.get("bid") or ALL.get("bidPrice") or ALL.get("bestBid"), 0.0))
                    out["last"] = max(out["last"], _f(ALL.get("lastTrade") or ALL.get("lastPrice") or ALL.get("close"), 0.0))
                    out["bid"]  = max(out["bid"], _f(EHD.get("bid") or EHD.get("bidPrice") or EHD.get("bestBid"), 0.0))
                    out["last"] = max(out["last"], _f(EHD.get("lastTrade") or EHD.get("lastPrice") or EHD.get("close"), 0.0))
        except Exception:
            pass

    return out

def preview(acct_key: str, symbol: str, qty: int, limit_price: float, debug=False):
    if not hasattr(et, "preview_equity_order"):
        return None, "no preview_equity_order"
    fn = et.preview_equity_order
    try:
        sig = inspect.signature(fn); names = [p.lower() for p in sig.parameters.keys()]
    except Exception:
        sig, names = None, []
    if names == ["symbol","qty","price"] or ("symbol" in names and "qty" in names and "price" in names and len(names)==3):
        if debug: print("[DBG] preview -> (symbol, qty, price)")
        return fn(symbol, qty, float(limit_price)), "preview(symbol,qty,price)"
    if names and names[0]=="action" and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview -> (action, symbol, qty, price)")
        return fn("SELL", symbol, qty, float(limit_price)), "preview(action,symbol,qty,price)"
    if "account_id_key" in names and "action" in names and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview -> (account_id_key, action, symbol, qty, price)")
        try:
            return fn(acct_key, "SELL", symbol, qty, float(limit_price)), "preview(acct,action,symbol,qty,price)"
        except Exception:
            return fn(account_id_key=acct_key, action="SELL", symbol=symbol, qty=qty, price=float(limit_price)), "preview(kwargs acct/action/symbol/qty/price)"
    kw = {}
    if "account_id_key" in names: kw["account_id_key"]=acct_key
    if "accountidkey" in names: kw["accountIdKey"]=acct_key
    if "action" in names or "orderaction" in names: kw["action" if "action" in names else "orderAction"]="SELL"
    if "symbol" in names: kw["symbol"]=symbol
    if "qty" in names or "quantity" in names: kw["qty" if "qty" in names else "quantity"]=qty
    if "price" in names: kw["price"]=float(limit_price)
    if kw:
        if debug: print("[DBG] preview -> kwargs", kw)
        return fn(**kw), "preview(kwargs-mapped)"
    return fn(symbol, qty, float(limit_price)), "preview(fallback symbol,qty,price)"

def place_from_preview(acct_key: str, preview_obj: dict, debug=False):
    if not hasattr(et, "place_equity_order"):
        return None, "no place_equity_order"
    fn = et.place_equity_order
    try:
        sig = inspect.signature(fn); names = [p.lower() for p in sig.parameters.keys()]
    except Exception:
        sig, names = None, []
    if len(names)==1 and names[0] in ("preview","order","payload","data"):
        if debug: print("[DBG] place -> (preview)")
        return fn(preview_obj), "place(preview)"
    if len(names)==2 and names[0] in ("account_id_key","accountidkey") and names[1] in ("preview","order","payload","data"):
        if debug: print("[DBG] place -> (account_id_key, preview)")
        return fn(**{names[0]:acct_key, names[1]:preview_obj}), "place(acct+preview)"
    try:
        if debug: print("[DBG] place -> kwargs fallback (preview=)")
        return fn(preview=preview_obj), "place(kwargs preview=)"
    except Exception:
        pass
    return None, "place(all_failed)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="sell all avail if omitted")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--offset", type=float, default=0.02)
    ap.add_argument("--use-last", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    avail = available_to_sell(acct_key, SYMBOL)
    print(f"[POS] {SYMBOL}: available_to_sell={avail}")

    if args.sell is None:
        return

    qty = avail if args.sell == "__AUTO__" else _f(args.sell, -1)
    if qty <= 0:
        print("[SELL] Aborting: qty <= 0")
        return
    if qty > avail:
        if args.force:
            print(f"[SELL] Requested {qty} > available {avail}; clamping.")
            qty = avail
        else:
            print(f"[SELL] Requested {qty} exceeds available {avail}. Use --force or cancel reserving orders.")
            return
    qty = int(qty)
    if qty <= 0:
        print("[SELL] Fractional only; route likely disallows fractional sells.")
        return

    q = best_quote(SYMBOL, debug=args.debug)
    src = "last" if args.use_last else "bid"
    base = q.get(src, 0.0)
    if base <= 0:
        base = q.get("last" if src=="bid" else "bid", 0.0)
        src = "last" if src=="bid" else "bid"
    if base <= 0:
        print("[QUOTE] Could not get a valid price from any helper. Aborting (previews need a float price).")
        return
    price = max(0.01, base - args.offset)
    print(f"[QUOTE] {SYMBOL} {src.upper()}={base:.2f} -> limit={price:.2f} (offset {args.offset:.2f})")

    try:
        prev, how = preview(acct_key, SYMBOL, qty, price, debug=args.debug)
    except Exception as e:
        print("[PREVIEW] failed:", e)
        return
    if prev is None:
        print(f"[PREVIEW] {how}")
        return
    print(f"[PREVIEW] via {how} -> ok")
    try:
        print(_fmt(prev))
    except Exception:
        pass

    try:
        resp, how2 = place_from_preview(acct_key, prev, debug=args.debug)
    except Exception as e:
        print("[SELL] place failed:", e); return
    if resp is None:
        print(f"[SELL] {how2}"); return
    print(f"[SELL] via {how2} -> ok")
    print(_fmt(resp))

if __name__ == "__main__":
    main()
