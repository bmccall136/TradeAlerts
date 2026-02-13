
#!/usr/bin/env python3
# sell_one.py — single-shot SELL helper (preview by default)
# Usage examples (PowerShell, from C:\TradeAlerts):
#   python -u sell_one.py MRNA 1              # preview MARKET & LIMIT
#   python -u sell_one.py MRNA 1 --place      # place orders after previews
#   python -u sell_one.py MRNA 1 --limit-from bid --limit-offset-bps 0 --place
#
# Notes:
# - Loads .env and applies env alias shim (ETRADE_API_KEY → ETRADE_CONSUMER_KEY, etc.).
# - Does MARKET and LIMIT previews; places only if --place set.
# - LIMIT price is derived from bid/last/mid with optional bps offset.
# - Prints concise results and exits non‑zero on hard errors.

import os, sys, argparse, math
from pathlib import Path

BASE_DIR = Path(r"C:\TradeAlerts")
sys.path.insert(0, str(BASE_DIR))

def _strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
        return v[1:-1]
    return v

def apply_env_aliases():
    alias_map = {
        "ETRADE_CONSUMER_KEY":   ["ETRADE_API_KEY", "CONSUMER_KEY"],
        "ETRADE_CONSUMER_SECRET":["ETRADE_API_SECRET", "CONSUMER_SECRET"],
        "ETRADE_OAUTH_TOKEN":    ["OAUTH_TOKEN"],
        "ETRADE_OAUTH_SECRET":   ["OAUTH_TOKEN_SECRET"],
        "ETRADE_ACCOUNT_ID_KEY": ["ACCOUNT_ID_KEY"],
        "ETRADE_ENV":            ["ETRADE_ENV"],
    }
    for target, sources in alias_map.items():
        if not os.environ.get(target):
            for s in sources:
                val = os.environ.get(s)
                if val:
                    os.environ[target] = _strip_quotes(val)
                    break

def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except Exception:
        pass
    apply_env_aliases()

def bps_mult(bps: int) -> float:
    return 1.0 + (bps / 10000.0)

def derive_limit(bid, last, ask, limit_from: str, offset_bps: int) -> float | None:
    base = None
    if limit_from == "bid":
        base = bid
    elif limit_from == "mid":
        if bid is not None and ask is not None:
            base = (bid + ask) / 2.0
    else:
        base = last
    if base is None:
        return None
    px = float(base) * bps_mult(offset_bps)
    return round(px, 2)

def dig_quote_fields(q: dict):
    bid = last = ask = None
    def rec(n):
        nonlocal bid, last, ask
        if isinstance(n, dict):
            if "bid" in n and n["bid"] is not None: bid = float(n["bid"])
            for k in ("lastPrice","lastTrade","last"):
                if k in n and n[k] is not None: last = float(n[k])
            if "ask" in n and n["ask"] is not None: ask = float(n["ask"])
            for v in n.values(): rec(v)
        elif isinstance(n, (list, tuple)):
            for v in n: rec(v)
    rec(q)
    return bid, last, ask

def main():
    p = argparse.ArgumentParser(description="Single-shot SELL helper (preview first).")
    p.add_argument("symbol", help="Ticker symbol, e.g., MRNA")
    p.add_argument("qty", type=int, help="Quantity to sell")
    p.add_argument("--place", action="store_true", help="Place after successful previews")
    p.add_argument("--limit-from", choices=["last","bid","mid"], default="last")
    p.add_argument("--limit-offset-bps", type=int, default=0)
    args = p.parse_args()

    load_env()

    try:
        from services import etrade_service as et
    except Exception:
        import etrade_service as et

    sym = args.symbol.upper()
    qty = int(args.qty)

    # account
    aid = et.account_id_key()
    print(f"[sell_one] account={aid} symbol={sym} qty={qty} place={args.place}")

    # quote
    q = et.get_quote(sym, "ALL")
    bid, last, ask = dig_quote_fields(q)
    print(f"[sell_one] quote: bid={bid} last={last} ask={ask}")

    # LIMIT preview
    limit_px = derive_limit(bid, last, ask, args.limit_from, args.limit_offset_bps)
    try:
        prv_lim = et.preview_equity_order(aid, sym, qty, limit_px, price_type="LIMIT", action="SELL")
        print(f"[sell_one] PREVIEW LIMIT SELL @ {limit_px}: OK")
    except Exception as e:
        print(f"[sell_one] PREVIEW LIMIT SELL ERROR: {e}")
        prv_lim = None

    # MARKET preview
    try:
        prv_mkt = et.preview_equity_order(aid, sym, qty, None, price_type="MARKET", action="SELL")
        print(f"[sell_one] PREVIEW MARKET SELL: OK")
    except Exception as e:
        print(f"[sell_one] PREVIEW MARKET SELL ERROR: {e}")
        prv_mkt = None

    if not args.place:
        print("[sell_one] Done (preview only). Add --place to actually place.")
        return 0

    placed_any = False
    if prv_lim:
        try:
            r = et.place_equity_order(prv_lim, qty=qty)
            print(f"[sell_one] PLACE LIMIT SELL: OK")
            placed_any = True
        except Exception as e:
            print(f"[sell_one] PLACE LIMIT SELL ERROR: {e}")

    if not placed_any and prv_mkt:
        try:
            r = et.place_equity_order(prv_mkt, qty=qty)
            print(f"[sell_one] PLACE MARKET SELL: OK")
            placed_any = True
        except Exception as e:
            print(f"[sell_one] PLACE MARKET SELL ERROR: {e}")

    return 0 if placed_any else 2

if __name__ == "__main__":
    raise SystemExit(main())
