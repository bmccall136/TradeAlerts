# C:\TradeAlerts\quick_sell_test.py
import sys
import time

sys.path.insert(0, r"C:\TradeAlerts")
from services import etrade_service as et

# === EDIT THESE ===
SYM = "WBD"  # symbol you hold
QTY = 1  # shares to sell (≤ what you own)
ORDER_TYPE = "MARKET"  # "MARKET" or "LIMIT"
DRY_RUN = False  # set False to actually place the order
AGGR_BPS = 150  # fallback limit inside bid (1.5%) when MARKET fails
TRIES = 5  # preview/place retries on transient errors
# ===================


def api_symbol(s: str) -> str:
    return s.replace("BF.B", "BF/B")


def is_code100(e: Exception) -> bool:
    s = str(e)
    return ("'code': 100" in s) or ("service is not currently available" in s)


def dig_bid_last(node):
    def visit(n):
        if isinstance(n, dict):
            bid = n.get("bid")
            last = n.get("lastPrice") or n.get("lastTrade") or n.get("last")
            if bid is not None or last is not None:
                return bid, last
            for v in n.values():
                r = visit(v)
                if r:
                    return r
        elif isinstance(n, (list, tuple)):
            for v in n:
                r = visit(v)
                if r:
                    return r
        return None

    return visit(node) or (None, None)


def preview_min(aid, sym, qty, px, price_type):
    # Use only the params your wrapper supports
    return et.preview_equity_order(
        aid, api_symbol(sym), int(qty), float(px), price_type=price_type, action="SELL"
    )


def place_with_retry(aid, sym, qty, price_type, px=None, tries=TRIES):
    last_exc = None
    for i in range(1, tries + 1):
        try:
            prv = preview_min(aid, sym, qty, (px or 0.0), price_type)
            placed = et.place_equity_order(prv, qty=int(qty))
            return placed
        except Exception as e:
            last_exc = e
            print(f"[error] place {price_type} try {i}: {e}")
            if is_code100(e) and i < tries:
                delay = 1.5**i
                print(f"[retry] code-100; backing off {delay:.1f}s…")
                time.sleep(delay)
                continue
            raise
    raise last_exc if last_exc else RuntimeError("unknown place failure")


def main():
    aid = et.account_id_key()
    free = int(et.available_to_sell(aid, SYM) or 0)
    print(f"Account: {aid}")
    print(f"Free to sell {SYM}: {free}")
    if free < QTY:
        print("Not enough free shares to sell.")
        return

    # If LIMIT, pick a price
    limit_px = None
    if ORDER_TYPE.upper() == "LIMIT":
        try:
            q = et.get_quote(SYM, detailFlag="ALL")
            bid, last = dig_bid_last(q)
        except Exception:
            bid = last = None
        base = bid if bid is not None else last
        if base is None:
            print("Could not determine a limit price; aborting.")
            return
        limit_px = round(float(base), 2)
        print(f"Limit to use: {limit_px:.2f}")

    if DRY_RUN:
        msg = f"[DRY RUN] Would place {ORDER_TYPE.upper()} SELL {SYM} x{QTY}"
        if ORDER_TYPE.upper() == "LIMIT":
            msg += f" @ {limit_px:.2f}"
        print(msg)
        return

    try:
        if ORDER_TYPE.upper() == "MARKET":
            try:
                placed = place_with_retry(aid, SYM, QTY, "MARKET")
            except Exception as e:
                if is_code100(e):
                    # MARKET failed with code-100 → try a marketable LIMIT
                    try:
                        q = et.get_quote(SYM, detailFlag="ALL")
                        bid, last = dig_bid_last(q)
                    except Exception:
                        bid = last = None
                    base = bid if bid is not None else last
                    if base is None:
                        raise
                    lim = round(float(base) * (1.0 - AGGR_BPS / 10_000.0), 2)
                    print(f"[fallback] MARKET code-100; trying LIMIT @ {lim:.2f}")
                    placed = place_with_retry(aid, SYM, QTY, "LIMIT", px=lim)
                else:
                    raise
        else:
            placed = place_with_retry(aid, SYM, QTY, "LIMIT", px=limit_px)

        print("Placed:", placed)
    finally:
        try:
            oo = et.get_open_orders(aid)
        except Exception as e:
            oo = {"open_orders_error": str(e)}
        print("Open orders:", oo)
        execs = et.recent_executions_as_trades(10) or []
        print("Recent execs (top 5):", execs[:5])


if __name__ == "__main__":
    main()
