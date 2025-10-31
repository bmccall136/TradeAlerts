
# live_tick_stub.py - dry-run loop that uses AvailableToTrade for sizing
import os, time, logging
from static_bp import choose_balance, parse_balances

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOG = logging.getLogger("live")

try:
    from services import etrade_service as et
except Exception as e:
    et = None
    LOG.warning("services import failed: %s", e)

SYMBOLS = ["NEM", "MRNA", "CBOE"]

def quote(sym):
    try:
        if hasattr(et, "get_quote"):
            q = et.get_quote(sym)
            src = q.get("All") or q
            px = src.get("lastTrade") or src.get("lastPrice") or src.get("close") or 0.0
            return float(px or 0.0)
    except Exception as e:
        LOG.warning("quote failed for %s: %s", sym, e)
    return 0.0

def balances():
    try:
        if hasattr(et, "get_balances"):
            return et.get_balances()
    except Exception as e:
        LOG.warning("balances failed: %s", e)
        return getattr(e, "response", {}) or {}
    return {}

def main():
    raw = balances()
    usable, src = choose_balance(raw)
    bal = parse_balances(raw)
    LOG.info("[LIVE] funds: chosen=$%.2f (src=%s) buyingPower=$%.2f",
             float(usable or 0), src, float((bal.get("buyingPower") or 0)))
    max_per_trade = float(os.environ.get("MAX_PER_TRADE", "100"))

    candidates = []
    for sym in SYMBOLS:
        px = quote(sym)
        budget = min(float(usable or 0), max_per_trade)
        qty = int(budget // px) if px > 0 else 0
        LOG.info("[LIVE] %s: px=%.2f budget=%.2f -> qty=%d", sym, px, budget, qty)
        if qty >= 1:
            candidates.append((sym, px, qty))

    if not candidates:
        LOG.info("[LIVE] tick: no purchasable candidates; usable=$%.2f", float(usable or 0))
        return

    LOG.info("[LIVE] candidates: %s", candidates)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(30)
