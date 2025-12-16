r"""
sell_equity_now.py — Sell an equity now using your wrapper; fallback to direct POST w/ account_id_key path.

USAGE (from C:\TradeAlerts):
  # Sell all available of FCX, LIMIT at BID-0.02
  python .\sell_equity_now.py --symbol FCX --sell --debug

  # Sell exactly 1 share at MARKET
  python .\sell_equity_now.py --symbol FCX --sell 1 --market

  # Sell 1 with explicit limit
  python .\sell_equity_now.py --symbol FCX --sell 1 --limit 45.02
"""

import argparse
import json
import os
import sys
import time
from typing import Any

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from services import etrade_service as et


def j(x: Any) -> str:
    try:
        return json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(x)


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def get_acct_key() -> str:
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k:
                return str(k)
        except Exception:
            pass
    if hasattr(et, "account_id_key"):
        k = et.account_id_key
        if k:
            return str(k)
    raise RuntimeError("Could not determine account_id_key")


def available_to_sell(acct_key: str, symbol: str) -> float:
    if hasattr(et, "available_to_sell"):
        try:
            return f(et.available_to_sell(acct_key, symbol), 0.0)
        except Exception:
            pass
    return 0.0


def best_bid(symbol: str) -> float:
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            for src in (q, q.get("All") or {}, q.get("ExtendedHourQuoteDetail") or {}):
                for k in ("bid", "bidPrice", "bestBid"):
                    if k in src:
                        return f(src[k], 0.0)
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
                for src in (
                    qd.get("All") or {},
                    qd.get("ExtendedHourQuoteDetail") or {},
                ):
                    for k in ("bid", "bidPrice", "bestBid"):
                        if k in src:
                            return f(src[k], 0.0)
    except Exception:
        pass
    return 0.0


def build_place_body_from_preview(prev: dict, qty_override: int | None = None) -> dict:
    pr = prev.get("PreviewOrderResponse") or {}
    orders = pr.get("Order") or []
    if not isinstance(orders, list) or not orders:
        raise RuntimeError("preview missing Order[]")
    order = orders[0]
    # qty override if requested
    if qty_override is not None:
        instr = order.get("Instrument") or []
        if instr:
            instr[0]["quantity"] = str(int(qty_override))
    # previewId
    pid = pr.get("previewId")
    if not pid:
        pids = pr.get("PreviewIds") or pr.get("previewIds") or []
        if isinstance(pids, list) and pids and isinstance(pids[0], dict):
            pid = pids[0].get("previewId") or pids[0].get("id")
    if not pid:
        raise RuntimeError("previewId not found in preview")
    return {
        "PlaceOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": None,
            "PreviewIds": [{"previewId": int(pid)}],
            "Order": [order],
        }
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument(
        "--sell", nargs="?", const="__AUTO__", help="sell all available if omitted"
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=float)
    ap.add_argument("--offset", type=float, default=0.02)
    ap.add_argument("--market", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    avail = available_to_sell(acct_key, symbol)
    print(f"[POS] {symbol}: available_to_sell={avail}")

    if args.sell is None:
        return

    qty = avail if args.sell == "__AUTO__" else f(args.sell, -1)
    if qty <= 0:
        print("[SELL] Aborting: qty <= 0")
        return
    if qty > avail:
        if args.force:
            print(f"[SELL] Requested {qty} > available {avail}; clamping.")
            qty = avail
        else:
            print(
                f"[SELL] Requested {qty} exceeds available {avail}. Use --force or cancel reserving orders."
            )
            return
    qty = int(qty)
    if qty <= 0:
        print("[SELL] Fractional only; route likely disallows fractional sells.")
        return

    # Price build
    if args.market:
        pt = "MARKET"
        price = None
        print("[QUOTE] using MARKET")
    elif args.limit and args.limit > 0:
        pt = "LIMIT"
        price = float(args.limit)
        print(f"[QUOTE] using manual --limit {price:.2f}")
    else:
        bid = best_bid(symbol)
        if bid <= 0:
            print("[QUOTE] Could not get a valid BID; use --market or --limit.")
            return
        pt = "LIMIT"
        price = max(0.01, bid - args.offset)
        print(
            f"[QUOTE] {symbol} BID={bid:.2f} -> limit={price:.2f} (offset {args.offset:.2f})"
        )

    # PREVIEW via wrapper
    try:
        prev = et.preview_equity_order(
            acct_key,
            symbol,
            qty,
            price,
            action="SELL",
            price_type=pt,
            order_term="GOOD_FOR_DAY",
            market_session="REGULAR",
        )
    except Exception as e:
        print("[PREVIEW] failed:", e)
        return
    print("[PREVIEW] ok")
    if args.debug:
        print(j(prev))

    # PLACE via wrapper first (exact signature)
    last_err = None
    for attempt in range(1, 3):
        try:
            resp = et.place_equity_order(prev)  # wrapper uses the preview qty
            print(f"[SELL] placed via wrapper on attempt {attempt}")
            print(j(resp))
            return
        except Exception as e:
            last_err = e
            msg = str(e)
            print(f"[DBG] wrapper place attempt {attempt} failed:", msg)
            if "service is not currently available" in msg and attempt < 2:
                time.sleep(0.9)
                continue
            break

    # FALLBACK: direct POST with account_id_key in URL (to avoid wrapper path issues)
    try:
        body = build_place_body_from_preview(prev)
        if args.debug:
            print("[DBG] fallback place body:")
            print(j(body))
        resp = et._epost(f"/accounts/{acct_key}/orders/place.json", body)
        print("[SELL] placed via direct fallback")
        print(j(resp))
        return
    except Exception as e:
        print("[SELL] fallback failed:", e)
        return


if __name__ == "__main__":
    main()
