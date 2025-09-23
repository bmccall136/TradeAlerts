
"""
mrna_sell_final.py — minimal, signature-accurate placement using your wrapper.

USAGE (from C:\TradeAlerts):
  # Default: LIMIT at (BID - 0.02), auto-sell available qty
  python .\mrna_sell_final.py --sell --debug

  # Explicit limit
  python .\mrna_sell_final.py --sell --limit 27.05

  # MARKET sell (no price required)
  python .\mrna_sell_final.py --sell --market

  # Force a qty (will clamp to available if --force given)
  python .\mrna_sell_final.py --sell 10 --force
"""

import sys, argparse, json, time, os
from typing import Any, Dict

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from services import etrade_service as et

SYMBOL = "MRNA"

def j(x: Any) -> str:
    try: return json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception: return str(x)

def f(x, d=0.0):
    try: return float(x)
    except Exception: return d

def get_acct_key() -> str:
    # Your wrapper exposes either get_account_id_key() or account_id_key
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
            return f(et.available_to_sell(acct_key, symbol), 0.0)
        except Exception:
            pass
    return 0.0

def best_bid(symbol: str) -> float:
    # Minimal quote getter: try fetch_etrade_quote -> get_quote
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            for k in ("bid","bidPrice","bestBid"):
                if k in q:
                    return f(q[k], 0.0)
            allsec = q.get("All") if isinstance(q.get("All"), dict) else None
            if allsec:
                for k in ("bid","bidPrice","bestBid"):
                    if k in allsec: return f(allsec[k], 0.0)
    except Exception:
        pass
    try:
        g = et.get_quote(symbol)
        if isinstance(g, dict):
            qr = g.get("QuoteResponse") or {}
            qd = qr.get("QuoteData")
            if isinstance(qd, list) and qd:
                qd = qd[0]
            if isinstance(qd, dict):
                allsec = qd.get("All") or {}
                for k in ("bid","bidPrice","bestBid"):
                    if k in allsec: return f(allsec[k], 0.0)
    except Exception:
        pass
    return 0.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sell", nargs="?", const="__AUTO__", help="sell all available if omitted")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=float, help="explicit limit price (ignored for --market)")
    ap.add_argument("--offset", type=float, default=0.02, help="BID - offset (ignored for --market)")
    ap.add_argument("--market", action="store_true", help="MARKET sell (no price)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    acct = get_acct_key()
    print("[INFO] account_id_key:", acct)

    avail = available_to_sell(acct, SYMBOL)
    print(f"[POS] {SYMBOL}: available_to_sell={avail}")

    if args.sell is None:
        return

    qty = avail if args.sell == "__AUTO__" else f(args.sell, -1)
    if qty <= 0:
        print("[SELL] Aborting: qty <= 0"); return
    if qty > avail:
        if args.force:
            print(f"[SELL] Requested {qty} > available {avail}; clamping.")
            qty = avail
        else:
            print(f"[SELL] Requested {qty} exceeds available {avail}. Use --force or cancel reserving orders."); return
    qty = int(qty)
    if qty <= 0:
        print("[SELL] Fractional only; route likely disallows fractional sells."); return

    # Build preview with your wrapper's EXACT signature
    if args.market:
        print("[QUOTE] using MARKET")
        price = None
        pt = "MARKET"
    else:
        if args.limit and args.limit > 0:
            price = float(args.limit)
            print(f"[QUOTE] using manual --limit {price:.2f}")
        else:
            bid = best_bid(SYMBOL)
            if bid <= 0:
                print("[QUOTE] Could not get a valid BID; use --market or --limit."); return
            price = max(0.01, bid - args.offset)
            print(f"[QUOTE] {SYMBOL} BID={bid:.2f} -> limit={price:.2f} (offset {args.offset:.2f})")
        pt = "LIMIT"

    try:
        prev = et.preview_equity_order(
            acct, SYMBOL, qty, price,
            action="SELL",
            price_type=pt,
            order_term="GOOD_FOR_DAY",
            market_session="REGULAR",
        )
    except Exception as e:
        print("[PREVIEW] failed:", e); return

    print("[PREVIEW] ok"); 
    if args.debug: print(j(prev))

    # Place using the EXACT signature: place_equity_order(preview_resp: dict, qty: int|None = None)
    # Add light retries for transient 500s.
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = et.place_equity_order(prev)  # qty=None; wrapper will reuse preview qty
            print(f"[SELL] ok on attempt {attempt}")
            print(j(resp))
            return
        except Exception as e:
            last_err = e
            msg = str(e)
            print(f"[DBG] place attempt {attempt} failed:", msg)
            if "service is not currently available" in msg and attempt < 3:
                time.sleep(0.9)
                continue
            # fall through and exit if not transient

    print("[SELL] failed:", last_err)

if __name__ == "__main__":
    main()
