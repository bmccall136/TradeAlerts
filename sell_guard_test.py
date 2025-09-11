#!/usr/bin/env python3
"""
sell_guard_test.py — Minimal exit tester for one symbol.
- Polls quotes + your E*TRADE positions
- Triggers SELL when TP / SL thresholds hit (bps)
- Calls broker/etrade sell and logs the response
"""

import os, sys, time, json, math
import datetime as dt

from decimal import Decimal

# --- config (tweak here or via env) ---
SYMBOL      = os.getenv("TEST_SYMBOL", "").upper()   # e.g. "DAL". If blank, auto-pick first position.
TP_BPS      = int(os.getenv("TEST_TP_BPS", "30"))    # take-profit threshold in basis points (30 = 0.30%)
SL_BPS      = int(os.getenv("TEST_SL_BPS", "150"))   # stop-loss threshold in bps    (150 = 1.50%)
POLL_SEC    = float(os.getenv("TEST_POLL_SEC", "3.0"))
DRY_RUN     = os.getenv("TEST_DRY_RUN", "1") == "1"  # 1 = don’t place real order
LIMIT_FROM  = os.getenv("TEST_LIMIT_FROM", "last")   # "last" or "mid" (if your helper supports)
LIMIT_BPS   = int(os.getenv("TEST_LIMIT_BPS", "0"))  # optional offset in bps for limit orders
USE_MARKET  = os.getenv("TEST_USE_MARKET", "1") == "1"  # 1 = market sell, 0 = limit

# --- wiring ---
from services import etrade_service as et
try:
    from services import broker as _broker
    BROKER = _broker.get_broker("LIVE")
except Exception:
    BROKER = None

def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg, *a):
    s = msg if not a else msg % a
    print(f"{now()}  TEST  {s}", flush=True)

def _to_f(x):
    try:
        if x is None: return None
        if isinstance(x, (int,float)): return float(x)
        return float(str(x).replace(",",""))
    except Exception:
        return None

def _get_positions_map():
    """Return {SYM: {'qty': int, 'price_paid': float}} via E*TRADE."""
    out = {}
    try:
        raw = et.get_positions() or {}
    except Exception as e:
        log("get_positions failed: %s", e)
        raw = {}

    def visit(n):
        if isinstance(n, dict):
            prod = n.get("Product") or n.get("product") or {}
            sym  = (n.get("symbol") or prod.get("symbol") or "").upper()
            qty  = n.get("positionQty") or n.get("qty") or n.get("longQty") or n.get("longQuantity")
            paid = n.get("pricePaid") or n.get("avgPrice") or n.get("averagePrice") or n.get("costPerShare")
            if sym and qty:
                try:
                    q = int(float(qty))
                    if q > 0:
                        out[sym] = {"qty": q, "price_paid": _to_f(paid)}
                except Exception:
                    pass
            for v in n.values(): visit(v)
        elif isinstance(n, (list,tuple)):
            for v in n: visit(v)

    visit(raw)
    return out

def _get_last(sym):
    """Return (last, prev_close) from E*TRADE quotes (with ALL detail when available)."""
    try:
        raw = et.get_quote(sym, detailFlag="ALL") if hasattr(et, "get_quote") else et.get_quotes([sym], detailFlag="ALL")
    except Exception as e:
        log("get_quote failed for %s: %s", sym, e)
        return None, None

    def dig(node):
        if isinstance(node, dict):
            last = None; prev = None
            allb = node.get("All") or node.get("all")
            intr = node.get("Intraday") or node.get("intraday")
            if isinstance(allb, dict):
                last = _to_f(allb.get("lastTrade") or allb.get("lastPrice"))
                prev = _to_f(allb.get("previousClose") or allb.get("priorClose"))
                eh = allb.get("ExtendedHourQuoteDetail") or {}
                eh_last = _to_f(eh.get("lastPrice"))
                if eh_last is not None: last = eh_last
            if last is None and isinstance(intr, dict):
                last = _to_f(intr.get("lastTrade") or intr.get("lastPrice"))
            for v in node.values():
                if isinstance(v, (dict,list,tuple)):
                    l,p = dig(v)
                    last = last if last is not None else l
                    prev = prev if prev is not None else p
            return last, prev
        elif isinstance(node, (list,tuple)):
            L=P=None
            for v in node:
                l,p = dig(v)
                L = L if L is not None else l
                P = P if P is not None else p
            return L,P
        return None, None

    return dig(raw)

def _bps_change(last, basis):
    if not last or not basis: return 0.0
    try:
        return (last / basis - 1.0) * 10000.0
    except Exception:
        return 0.0

def _make_limit_px(last):
    if last is None: return None
    off = last * (LIMIT_BPS / 10000.0)
    px = last + off
    # round to 2 decimals typical for equities
    return round(px, 2)

def _place_sell(sym, qty, last):
    if DRY_RUN:
        log("[DRY-RUN] would SELL %s x%d at last=%.2f (use_market=%s, limit_bps=%d)",
            sym, qty, (last or 0.0), int(USE_MARKET), LIMIT_BPS)
        return {"ok": True, "dry_run": True}

    # Try broker wrapper first
    try:
        if BROKER and hasattr(BROKER, "sell_market") and USE_MARKET:
            resp = BROKER.sell_market(sym, qty)
            log("broker.sell_market(%s,%d) -> %s", sym, qty, str(resp)[:160])
            return {"ok": True, "broker": True, "resp": resp}
        if BROKER and hasattr(BROKER, "sell_limit") and not USE_MARKET:
            px = _make_limit_px(last)
            resp = BROKER.sell_limit(sym, qty, px)
            log("broker.sell_limit(%s,%d,%.2f) -> %s", sym, qty, px, str(resp)[:160])
            return {"ok": True, "broker": True, "resp": resp}
    except Exception as e:
        log("broker sell failed: %s", e)

    # Fallback: etrade_service direct (adjust to your function names if different)
    try:
        if hasattr(et, "sell_market") and USE_MARKET:
            resp = et.sell_market(sym, qty)
            log("et.sell_market(%s,%d) -> %s", sym, qty, str(resp)[:160])
            return {"ok": True, "et": True, "resp": resp}
        if hasattr(et, "sell_limit") and not USE_MARKET:
            px = _make_limit_px(last)
            resp = et.sell_limit(sym, qty, px)
            log("et.sell_limit(%s,%d,%.2f) -> %s", sym, qty, px, str(resp)[:160])
            return {"ok": True, "et": True, "resp": resp}
    except Exception as e:
        log("etrade_service sell failed: %s", e)

    return {"ok": False, "error": "no sell function available"}

def main():
    log("sell-tester starting (TP=%dbps, SL=%dbps, poll=%.1fs, dry_run=%s)",
        TP_BPS, SL_BPS, POLL_SEC, int(DRY_RUN))

    pos_map = _get_positions_map()
    if not pos_map:
        log("no positions found; nothing to test.")
        return 0

    sym = SYMBOL or next(iter(pos_map.keys()))
    if sym not in pos_map:
        log("symbol %s not in holdings; available: %s", sym, ", ".join(pos_map.keys()))
        return 1

    qty  = pos_map[sym]["qty"]
    paid = pos_map[sym]["price_paid"]
    log("testing %s (qty=%d, basis=%.2f)", sym, qty, paid or 0.0)

    while True:
        last, prev = _get_last(sym)
        if last is None:
            log("no last price yet; sleeping...")
            time.sleep(POLL_SEC); continue

        bps = _bps_change(last, paid or last)
        log("quote %s last=%.2f basis=%.2f Δ=%.2fbps (%.2f%%)",
            sym, last, (paid or 0.0), bps, bps/100.0)

        should_tp = (bps >= TP_BPS)
        should_sl = (bps <= -SL_BPS)

        if should_tp or should_sl:
            reason = "TP" if should_tp else "SL"
            log("TRIGGER %s → attempting SELL", reason)
            result = _place_sell(sym, qty, last)
            log("SELL result: %s", json.dumps(result)[:300])
            # stop after one attempt so logs are clear
            return 0

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    sys.exit(main())
