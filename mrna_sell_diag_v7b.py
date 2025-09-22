
"""
mrna_sell_diag_v7b.py — builds a proper PlaceOrderRequest from the preview and tries the likely call shapes.

What it adds vs v7:
- Constructs `PlaceOrderRequest` by copying the preview response:
    PlaceOrderRequest = {
      orderType: "EQ",
      PreviewIds: [...],
      Order: [...],
      clientOrderId: "<epoch>"
    }
- Tries `place_equity_order(payload)` and `place_equity_order(account_id_key, payload)`
  plus several kwargs fallbacks (placeOrderRequest= / request= / payload= / data= / order=).

Run:
  python mrna_sell_diag_v7b.py --sell --debug
"""

import sys, json, argparse, inspect, os, time
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

def best_quote(symbol: str) -> Dict[str, float]:
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

def preview(acct_key: str, symbol: str, qty: int, limit_price: float):
    fn = et.preview_equity_order
    # Your logs showed kwargs path works
    return fn(account_id_key=acct_key, action="SELL", symbol=symbol, qty=qty, price=float(limit_price))

def make_place_request_from_preview(prev: dict) -> Dict[str, Any]:
    R = prev.get("PreviewOrderResponse") or prev.get("previewOrderResponse") or {}
    order_type = R.get("orderType") or "EQ"
    preview_ids = R.get("PreviewIds") or R.get("previewIds") or []
    orders = R.get("Order") or R.get("order") or []

    if not isinstance(preview_ids, list) or not preview_ids:
        raise ValueError("preview missing PreviewIds[]")
    if isinstance(orders, dict):
        orders = [orders]
    if not isinstance(orders, list) or not orders:
        raise ValueError("preview missing Order[]")

    return {
        "PlaceOrderRequest": {
            "orderType": order_type,
            "clientOrderId": str(int(time.time())),
            "PreviewIds": preview_ids,
            "Order": orders
        }
    }

def try_place(fn, acct_key, payload, debug=False):
    # 1) single positional payload
    try:
        return fn(payload), "place(payload)"
    except Exception as e:
        if debug: print("[DBG] place(payload) failed:", e)
    # 2) (acct_key, payload)
    try:
        return fn(acct_key, payload), "place(acct_key, payload)"
    except Exception as e:
        if debug: print("[DBG] place(acct_key, payload) failed:", e)
    # 3) kwargs common names
    variants = [
        {"placeOrderRequest": payload.get("PlaceOrderRequest")},
        {"request": payload.get("PlaceOrderRequest")},
        {"payload": payload},
        {"data": payload},
        {"order": payload},  # some wrappers call it "order" even for EQ
        {"account_id_key": acct_key, "placeOrderRequest": payload.get("PlaceOrderRequest")},
        {"accountIdKey": acct_key, "PlaceOrderRequest": payload.get("PlaceOrderRequest")},
    ]
    for i,kw in enumerate(variants, 1):
        try:
            return fn(**kw), f"place(kwargs variant #{i})"
        except Exception as e:
            if debug: print(f"[DBG] kwargs variant #{i} failed:", e)
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

    q = best_quote(SYMBOL)
    src = "last" if args.use_last else "bid"
    base = q.get(src, 0.0) or q.get("last" if src=="bid" else "bid", 0.0)
    if base <= 0:
        print("[QUOTE] Could not get a valid price. Aborting.")
        return
    price = max(0.01, base - args.offset)
    print(f"[QUOTE] {SYMBOL} {src.upper()}={base:.2f} -> limit={price:.2f} (offset {args.offset:.2f})")

    try:
        prev = preview(acct_key, SYMBOL, qty, price)
    except Exception as e:
        print("[PREVIEW] failed:", e); return
    print("[PREVIEW] ok"); print(_fmt(prev))

    try:
        place_payload = make_place_request_from_preview(prev)
    except Exception as e:
        print("[SELL] Could not build PlaceOrderRequest:", e); return
    if args.debug:
        print("[DBG] PlaceOrderRequest:"); print(_fmt(place_payload))

    fn = et.place_equity_order
    resp, how = try_place(fn, acct_key, place_payload, debug=args.debug)
    if resp is None:
        print(f"[SELL] {how}"); return
    print(f"[SELL] via {how} -> ok"); print(_fmt(resp))

if __name__ == "__main__":
    main()
