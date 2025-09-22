
"""
mrna_sell_diag_v7c.py — focuses on placement: tries positional calls with the preview object.

After preview, attempts in this order:
  1) place_equity_order(preview_full)                  # full dict with "PreviewOrderResponse"
  2) place_equity_order(preview_inner)                 # the inner "PreviewOrderResponse" dict
  3) place_equity_order(account_id_key, preview_full)
  4) place_equity_order(account_id_key, preview_inner)

Run:
  python mrna_sell_diag_v7c.py --sell --debug
"""

import sys, json, argparse, inspect, os
from typing import Any, Dict

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
            out["bid"]  = max(out["bid"],  _f(q.get("bid") or q.get("bidPrice") or q.get("bestBid"), 0.0))
            out["last"] = max(out["last"], _f(q.get("last") or q.get("lastPrice") or q.get("lastTrade") or q.get("close"), 0.0))
    except Exception:
        pass
    return out

def preview(acct_key: str, symbol: str, qty: int, limit_price: float):
    return et.preview_equity_order(account_id_key=acct_key, action="SELL", symbol=symbol, qty=qty, price=float(limit_price))

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
        print("[SELL] Aborting: qty <= 0"); return
    if qty > avail:
        if args.force:
            print(f"[SELL] Requested {qty} > available {avail}; clamping."); qty = avail
        else:
            print(f"[SELL] Requested {qty} exceeds available {avail}. Use --force or cancel reserving orders."); return
    qty = int(qty)
    if qty <= 0:
        print("[SELL] Fractional only; route likely disallows fractional sells."); return

    q = best_quote(SYMBOL)
    src = "last" if args.use_last else "bid"
    base = q.get(src, 0.0) or q.get("last" if src=="bid" else "bid", 0.0)
    if base <= 0:
        print("[QUOTE] Could not get a valid price. Aborting."); return
    price = max(0.01, base - args.offset)
    print(f"[QUOTE] {SYMBOL} {src.upper()}={base:.2f} -> limit={price:.2f} (offset {args.offset:.2f})")

    try:
        prev = preview(acct_key, SYMBOL, qty, price)
    except Exception as e:
        print("[PREVIEW] failed:", e); return
    print("[PREVIEW] ok"); print(_fmt(prev))

    inner = prev.get("PreviewOrderResponse") or prev.get("previewOrderResponse")
    if not isinstance(inner, dict):
        print("[SELL] Preview missing inner 'PreviewOrderResponse' dict."); return

    fn = et.place_equity_order

    # 1) place(preview_full)
    try:
        resp = fn(prev)
        print("[SELL] via place(preview_full) -> ok"); print(_fmt(resp)); return
    except Exception as e:
        if args.debug: print("[DBG] place(preview_full) failed:", e)

    # 2) place(preview_inner)
    try:
        resp = fn(inner)
        print("[SELL] via place(preview_inner) -> ok"); print(_fmt(resp)); return
    except Exception as e:
        if args.debug: print("[DBG] place(preview_inner) failed:", e)

    # 3) place(account_id_key, preview_full)
    try:
        resp = fn(acct_key, prev)
        print("[SELL] via place(acct_key, preview_full) -> ok"); print(_fmt(resp)); return
    except Exception as e:
        if args.debug: print("[DBG] place(acct_key, preview_full) failed:", e)

    # 4) place(account_id_key, preview_inner)
    try:
        resp = fn(acct_key, inner)
        print("[SELL] via place(acct_key, preview_inner) -> ok"); print(_fmt(resp)); return
    except Exception as e:
        if args.debug: print("[DBG] place(acct_key, preview_inner) failed:", e)

    print("[SELL] all placement attempts failed.")

if __name__ == "__main__":
    main()
