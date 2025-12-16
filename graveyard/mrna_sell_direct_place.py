r"""
mrna_sell_direct_place.py — preview with your wrapper, then PLACE by calling et._epost
using the numeric accountId returned in the preview. This avoids the wrapper's
place_equity_order() using the wrong path segment (account_id_key instead of numeric).

USAGE:
  python .\mrna_sell_direct_place.py --sell --debug
  python .\mrna_sell_direct_place.py --sell --market
  python .\mrna_sell_direct_place.py --sell --limit 27.05
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

SYMBOL = "MRNA"


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
            for src in (q, q.get("All") or {}):
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
                allsec = qd.get("All") or {}
                for k in ("bid", "bidPrice", "bestBid"):
                    if k in allsec:
                        return f(allsec[k], 0.0)
    except Exception:
        pass
    return 0.0


def build_place_body_from_preview(
    prev: dict, qty_override: int | None = None
) -> tuple[str, dict]:
    pr = prev.get("PreviewOrderResponse") or {}
    acct_num = str(pr.get("accountId") or "").strip()
    if not acct_num:
        raise RuntimeError("preview missing numeric accountId")

    orders = pr.get("Order") or []
    if not isinstance(orders, list) or not orders:
        raise RuntimeError("preview missing Order[]")
    order = orders[0]

    # qty override if requested
    if qty_override is not None:
        instr = order.get("Instrument") or []
        if instr:
            instr[0]["quantity"] = str(int(qty_override))

    # find previewId robustly
    pid = pr.get("previewId")
    if not pid:
        pids = pr.get("PreviewIds") or pr.get("previewIds") or []
        if isinstance(pids, list) and pids and isinstance(pids[0], dict):
            pid = pids[0].get("previewId") or pids[0].get("id")
    if not pid:
        raise RuntimeError("previewId not found in preview")

    place_body = {
        "PlaceOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": None,
            "PreviewIds": [{"previewId": int(pid)}],
            "Order": [order],
        }
    }
    return acct_num, place_body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sell", nargs="?", const="__AUTO__", help="sell all available if omitted"
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=float)
    ap.add_argument("--offset", type=float, default=0.02)
    ap.add_argument("--market", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    acct_key = get_acct_key()
    print("[INFO] account_id_key:", acct_key)

    avail = available_to_sell(acct_key, SYMBOL)
    print(f"[POS] {SYMBOL}: available_to_sell={avail}")

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

    # price
    if args.market:
        pt = "MARKET"
        price = None
        print("[QUOTE] using MARKET")
    elif args.limit and args.limit > 0:
        pt = "LIMIT"
        price = float(args.limit)
        print(f"[QUOTE] using manual --limit {price:.2f}")
    else:
        bid = best_bid(SYMBOL)
        if bid <= 0:
            print("[QUOTE] Could not get a valid BID; use --market or --limit.")
            return
        pt = "LIMIT"
        price = max(0.01, bid - args.offset)
        print(
            f"[QUOTE] {SYMBOL} BID={bid:.2f} -> limit={price:.2f} (offset {args.offset:.2f})"
        )

    # preview via wrapper (works fine)
    try:
        prev = et.preview_equity_order(
            acct_key,
            SYMBOL,
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

    # build place body using numeric accountId from preview, POST directly via _epost
    try:
        acct_num, place_body = build_place_body_from_preview(prev)
    except Exception as e:
        print("[SELL] could not build place body:", e)
        return
    if args.debug:
        print("[DBG] place path:", f"/accounts/{acct_num}/orders/place.json")
        print("[DBG] place body:")
        print(j(place_body))

    # Do the POST
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = et._epost(f"/accounts/{acct_num}/orders/place.json", place_body)
            print(f"[SELL] placed on attempt {attempt}")
            print(j(resp))
            return
        except Exception as e:
            last_err = e
            msg = str(e)
            print(f"[DBG] direct place attempt {attempt} failed:", msg)
            if "service is not currently available" in msg and attempt < 3:
                time.sleep(1.0)
                continue
            break

    print("[SELL] failed:", last_err)


if __name__ == "__main__":
    main()
