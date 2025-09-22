
"""
mrna_sell_diag_v7.py — SELL MRNA using previewId + Order payload (E*TRADE-style place).

USAGE:
  python mrna_sell_diag_v7.py --sell --debug
  python mrna_sell_diag_v7.py --sell --use-last
  python mrna_sell_diag_v7.py --sell 4 --force
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
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            out["bid"] = max(out["bid"], _f(q.get("bid") or q.get("bidPrice") or q.get("bestBid"), 0.0))
            out["last"] = max(out["last"], _f(q.get("last") or q.get("lastPrice") or q.get("lastTrade") or q.get("close"), 0.0))
            ALL = q.get("All") if isinstance(q.get("All"), dict) else None
            if ALL:
                out["bid"]  = max(out["bid"], _f(ALL.get("bid") or ALL.get("bidPrice") or ALL.get("bestBid"), 0.0))
                out["last"] = max(out["last"], _f(ALL.get("lastTrade") or ALL.get("lastPrice") or ALL.get("close"), 0.0))
            EHD = q.get("ExtendedHourQuoteDetail") if isinstance(q.get("ExtendedHourQuoteDetail"), dict) else None
            if EHD:
                out["bid"]  = max(out["bid"], _f(EHD.get("bid") or EHD.get("bidPrice") or EHD.get("bestBid"), 0.0))
                out["last"] = max(out["last"], _f(EHD.get("lastTrade") or EHD.get("lastPrice") or EHD.get("close"), 0.0))
    except Exception:
        pass
    try:
        g = et.get_quote(symbol)
        if isinstance(g, dict):
            QR = g.get("QuoteResponse") or {}
            qd = None
            if isinstance(QR, dict):
                qd = QR.get("QuoteData")
                if isinstance(qd, list) and qd:
                    qd = qd[0]
            if isinstance(qd, dict):
                ALL = qd.get("All") or {}
                EHD = qd.get("ExtendedHourQuoteDetail") or {}
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
    if "account_id_key" in names and "action" in names and "symbol" in names and "qty" in names and "price" in names:
        if debug: print("[DBG] preview -> (account_id_key, action, symbol, qty, price)")
        try:
            return fn(acct_key, "SELL", symbol, qty, float(limit_price)), "preview(acct,action,symbol,qty,price)"
        except Exception:
            return fn(account_id_key=acct_key, action="SELL", symbol=symbol, qty=qty, price=float(limit_price)), "preview(kwargs acct/action/symbol/qty/price)"
    try:
        return fn(symbol, qty, float(limit_price)), "preview(symbol,qty,price)"
    except Exception:
        try:
            return fn("SELL", symbol, qty, float(limit_price)), "preview(action,symbol,qty,price)"
        except Exception as e:
            return None, f"preview(all_failed: {e})"

def extract_preview_bits(prev: dict):
    R = prev.get("PreviewOrderResponse") or prev.get("previewOrderResponse") or {}
    pids = R.get("PreviewIds") or R.get("previewIds") or []
    if isinstance(pids, list) and pids:
        preview_id = pids[0].get("previewId") or pids[0].get("preview_id") or pids[0].get("id")
    else:
        preview_id = R.get("previewId") or R.get("preview_id")
    orders = R.get("Order") or R.get("order") or []
    if isinstance(orders, list) and orders:
        order = orders[0]
    elif isinstance(orders, dict):
        order = orders
    else:
        order = {}
    return preview_id, order

def place_with_preview_bits(acct_key: str, preview_id, order_payload, preview_obj: dict, debug=False):
    if not hasattr(et, "place_equity_order"):
        return None, "no place_equity_order"
    fn = et.place_equity_order
    try:
        return fn(acct_key, preview_id, order_payload), "place(acct, previewId, order)"
    except Exception as e:
        if debug: print("[DBG] place positional (acct, previewId, order) failed:", e)
    try:
        return fn(preview_id, order_payload), "place(previewId, order)"
    except Exception as e:
        if debug: print("[DBG] place positional (previewId, order) failed:", e)
    kw_variants = [
        {"account_id_key": acct_key, "preview_id": preview_id, "order": order_payload},
        {"accountIdKey": acct_key, "previewId": preview_id, "order": order_payload},
        {"account_id_key": acct_key, "previewId": preview_id, "orderPayload": order_payload},
        {"previewId": preview_id, "order": order_payload},
        {"preview_id": preview_id, "order": order_payload},
        {"previewId": preview_id, "orderPayload": order_payload},
        {"preview": preview_obj},
    ]
    for i,kw in enumerate(kw_variants, 1):
        try:
            return fn(**kw), f"place(kwargs variant #{i})"
        except Exception as e:
            if debug: print(f"[DBG] place kwargs variant #{i} failed:", e)
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
    base = q.get(src, 0.0) or q.get("last" if src=="bid" else "bid", 0.0)
    if base <= 0:
        print("[QUOTE] Could not get a valid price. Aborting.")
        return
    price = max(0.01, base - args.offset)
    print(f"[QUOTE] {SYMBOL} {src.upper()}={base:.2f} -> limit={price:.2f} (offset {args.offset:.2f})")

    prev, how = preview(acct_key, SYMBOL, qty, price, debug=args.debug)
    if prev is None:
        print(f"[PREVIEW] {how}"); return
    print(f"[PREVIEW] via {how} -> ok")
    try: print(_fmt(prev))
    except Exception: pass

    preview_id, order_payload = extract_preview_bits(prev)
    if not preview_id or not isinstance(order_payload, dict):
        print("[SELL] Could not extract previewId/order payload from preview response. Aborting.")
        return

    resp, how2 = place_with_preview_bits(acct_key, preview_id, order_payload, prev, debug=args.debug)
    if resp is None:
        print(f"[SELL] {how2}"); return
    print(f"[SELL] via {how2} -> ok")
    print(_fmt(resp))

if __name__ == "__main__":
    main()
