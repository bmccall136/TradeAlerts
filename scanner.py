import time
import json
import logging
from datetime import datetime, time as dt_time, timedelta
from services.market_service import get_symbols, analyze_symbol

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ─── Market‑hours utilities ─────────────────────────────────────────────────────

MARKET_OPEN = dt_time(hour=9, minute=30)
MARKET_CLOSE = dt_time(hour=16, minute=0)
ET_OFFSET = timedelta(hours=-4)  # naive: assumes server clock is UTC

def _now_et():
    """Get current UTC time shifted to Eastern Time (ET)."""
    return datetime.utcnow() + ET_OFFSET

def in_market_hours():
    """Return True if now (ET) is between 9:30 and 16:00 (weekdays)."""
    now = _now_et()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE

def wait_for_open():
    """Sleep until the next ET market open, logging how long."""
    now = _now_et()
    # find next market-open datetime
    next_open_date = now.date()
    if now.time() >= MARKET_CLOSE or now.weekday() >= 5:
        # after close or weekend → move to next weekday
        next_open_date += timedelta(days=1)
        while next_open_date.weekday() >= 5:
            next_open_date += timedelta(days=1)
    open_dt = datetime.combine(next_open_date, MARKET_OPEN)
    # back to UTC
    open_dt_utc = open_dt - ET_OFFSET
    delta = open_dt_utc - datetime.utcnow()
    hours = delta.total_seconds() / 3600
    logger.info(f"Market closed. Sleeping for {hours:.2f}h until next open.")
    time.sleep(max(delta.total_seconds(), 0))

# ─── Main scanner loop ─────────────────────────────────────────────────────────

def main(simulation=False):
    syms = get_symbols(simulation=simulation)
    logger.info(f"Starting live scan of {len(syms)} symbols")
    while True:
        now = datetime.now()
        logger.info(f"Checking market hours at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        if not in_market_hours():
            wait_for_open()
            continue

        for sym in syms:
            try:
                alert = analyze_symbol(sym)
                # Do NOT call insert_alert here, analyze_symbol now does it!
            except Exception as e:
                logger.error(f"Error scanning {sym}: {e}")

        # pause between sweeps
        time.sleep(60)

if __name__ == "__main__":
    main(simulation=False)
