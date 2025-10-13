$code = @"
# sell_fcx_hardened.py — one-off hardened placement for FCX
# - Uses a fresh clientOrderId in PREVIEW and PLACE
# - Sends a minimal PLACE body (no read-only totals)
# - Formats price fields as 2-decimal strings
# - Posts to /accounts/{account_id_key}/orders/place.json

import sys, os, time, argparse, json
from typing import Any

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from services import etrade_service as et

SYMBOL = "FCX"

def j(x: Any) -> str:
    try: return json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception: return str(x)

def f2(val) -> str:
    return f"{float(val):.2f}"

def get_acct_key() -> str:
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k: return str(k)
        except Exception:
            pass
    if hasattr(et, "account_id_key"):
        return str(getattr(et, "account_id_key"))
    raise RuntimeError("Could not determine account_id_key")

def available_to_sell(acct_key: str, symbol: str) -> float:
    try:
        return float(et.available_to_sell(acct_key, symbol) or 0)
    except Exception:
        return 0.0

def best_bid(symbol: str) -> float:
    # Try fast quote paths; fall back to 0.0
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            for src in (q, q.get("All") or {}, q.get("ExtendedHourQuoteDetail") or {}):
                for k in ("bid","bidPrice","bestBid"):
                    if k in src:
                        return float(src[k])
    except Exception:
        pass
    try:
        g = et.get_quote(symbol)
        qr = (g or {}).get("QuoteResponse") or {}
        qd = qr.get("QuoteData")
        if isinstance(qd, list) and qd: qd = qd[0]
        if isinstance(qd, dict):
            for src in (qd.get("All") or {}, qd.get("ExtendedHourQuoteDetail") or {}):
                for k in ("bid","bidPrice","bestBid"):
                    if k in src: return float(src[k])
    except Exception:
        pass
    return 0.0

def build_min_place_body(preview: dict, client_id: str, qty_override: int|None=None) -> dict:
    pr = preview.get("PreviewOrderResponse") or {}
    orders = pr.get("Order") or []
    if not orders:
        raise RuntimeError("preview missing Order[]")
    src = orders[0]

    instr = (src.get("Instrument") or [])
    if not instr:
        raise RuntimeError("preview missing Instrument[]")

    prod = (instr[0].get("Product") or {})
    new_instr = [{
        "Product": {
            "securityType": str(prod.get("securityType") or "EQ"),
            "symbol": str(prod.get("symbol") or SYMBOL),
        },
        "orderAction": str(instr[0].get("orderAction") or "SELL"),
        "quantityType": "QUANTITY",
        "quantity": str(int(qty_override if qty_override is not None else instr[0].get("quantity") or 1)),
    }]

    order_min = {
        "orderTerm":     str(src.get("orderTerm") or "GOOD_FOR_DAY"),
        "priceType":     str(src.get("priceType") or "MARKET"),
        "marketSession": str(src.get("marketSession") or "REGULAR"),
        "allOrNone":     bool(src.get("allOrNone") or False),
        "Instrument":    new_instr,
    }
    if "limitPrice" in src and src["limitPrice"]:
        order_min["limitPrice"] = f2(src["limitPrice"])
    if "stopPrice" in src and src["stopPrice"]:
        order_min["stopPrice"] = f2(src["stopPrice"])

    pid = pr.get("previewId")
    if not pid:
        pids = pr.get("PreviewIds") or pr.get("previewIds") or []
        if isinstance(pids, list) and pids and isinstance(pids[0], dict):
            pid = pids[0].get("previewId") or pids[0].get("id")
    if not pid:
        raise RuntimeError("previewId not found")

    return {
        "PlaceOrderRequest": {
            "orderType": "EQ",
            "clientOrderId": client_id,
            "PreviewIds": [{"previewId": int(pid)}],
            "Order": [order_min],
        }
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--market", action="store_true")
    ap.add_argument("--limit", type=float)
    ap.add_argument("--offset", type=float, default=0.02)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    acct_key = get_acct_key()
    avail = available_to_sell(acct_key, SYMBOL)
    if avail < args.qty:
        print(f"[ABORT] Requested qty {args.qty} exceeds available_to_sell {avail}"); return

    # Price
    if args.market:
        price = None; pt = "MARKET"
        print("[QUOTE] MARKET")
    elif args.limit:
        price = float(args.limit); pt = "LIMIT"
        print(f"[QUOTE] LIMIT {price:.2f}")
    else:
        bid = best_bid(SYMBOL)
        if bid <= 0:
            print("[ABORT] No valid bid (use --market or --limit)"); return
        price = max(0.01, bid - args.offset); pt = "LIMIT"
        print(f"[QUOTE] BID={bid:.2f} -> LIMIT={price:.2f}")

    client_id = f"fcx-{int(time.time()*1000)}"

    # Preview (with explicit clientOrderId)
    prev = et.preview_equity_order(
        acct_key, SYMBOL, int(args.qty), price,
        action="SELL", price_type=pt, order_term="GOOD_FOR_DAY",
        market_session="REGULAR", client_order_id=client_id
    )
    if args.debug:
        print("[PREVIEW]"); print(j(prev))

    # Place (minimal body, same clientOrderId)
    body = build_min_place_body(prev, client_id, qty_override=int(args.qty))
    if args.debug:
        print("[PLACE BODY]"); print(j(body))

    resp = et._epost(f"/accounts/{acct_key}/orders/place.json", body)
    print("[PLACED]"); print(j(resp))

if __name__ == "__main__":
    main()
"@
$code | Set-Content .\sell_fcx_hardened.py -Encoding UTF8
