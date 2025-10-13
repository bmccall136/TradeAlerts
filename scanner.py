import os  # 👈 THIS was missing
import time
import json
import logging
from datetime import datetime, time as dt_time, timedelta
from services.market_service import get_symbols, analyze_symbol
import logging
from services.alert_service import insert_alert  # you already call it later
from services.log_utils import log_trigger, log_heartbeat
from datetime import timezone, timedelta
ET = timezone(timedelta(hours=-5))  # Permanent EST, no DST


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Ensure PID is saved relative to script location
base_path = os.path.dirname(os.path.abspath(__file__))
pid_file = os.path.join(base_path, "scanner.pid")

try:
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    print(f"[INIT] PID saved to {pid_file}")
except Exception as e:
    print(f"[ERROR] Could not write PID file: {e}")

from dotenv import load_dotenv
load_dotenv()


logger = logging.getLogger(__name__)

# ─── Market-hours utilities (DST-aware Eastern Time) ──────────────────────────
from datetime import datetime, time as dt_time, timedelta

try:
    # Python 3.9+ stdlib
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    # Windows often needs tzdata: `pip install tzdata`
    # Fallback to fixed EST if zoneinfo isn't available (not DST-aware)
    from datetime import timezone
    ET = timezone(timedelta(hours=-5))  # EST only (fallback)

MARKET_OPEN  = dt_time(hour=9,  minute=30)
MARKET_CLOSE = dt_time(hour=16, minute=0)

def _now_et() -> datetime:
    """Current time in Eastern Time (DST-aware when zoneinfo is available)."""
    # use UTCnow and convert (more robust on some systems)
    return datetime.now(tz=ZoneInfo("UTC")).astimezone(ET)

def in_market_hours() -> bool:
    """
    True if now (ET) is a weekday between 9:30 and 16:00.
    NOTE: This does not skip US market holidays; add a holiday calendar if needed.
    """
    now = _now_et()
    if now.weekday() >= 5:  # Sat=5, Sun=6
        return False
    t = now.timetz()  # time with tzinfo
    return (t >= MARKET_OPEN and t <= MARKET_CLOSE)

def _next_weekday(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def wait_for_open():
    """
    Sleep until the next ET market open (weekday 9:30).
    (Still ignores holidays; see note above.)
    """
    now = _now_et()
    # If after close or weekend, jump to next weekday; else use today
    open_date = now.date()
    if now.weekday() >= 5 or now.timetz() >= MARKET_CLOSE:
        open_date = _next_weekday(open_date)
    open_dt_et = datetime.combine(open_date, MARKET_OPEN, tzinfo=ET)
    # If it's before open today, keep today
    if now.timetz() < MARKET_OPEN and now.weekday() < 5:
        open_dt_et = datetime.combine(now.date(), MARKET_OPEN, tzinfo=ET)

    # Compute sleep in seconds using aware datetimes
    delta = (open_dt_et - now).total_seconds()
    hours = max(delta, 0) / 3600.0
    logger.info("Market closed. Sleeping for %.2fh until next open (%s ET).",
                hours, open_dt_et.strftime("%Y-%m-%d %H:%M:%S"))
    if delta > 0:
        time.sleep(delta)

# ─── Main scanner loop ─────────────────────────────────────────────────────────

def main(simulation=False):
    syms = get_symbols(simulation=simulation)
    logger.info(f"Starting live scan of {len(syms)} symbols")
    while True:
        now = datetime.now()
        logger.info(f"Checking market hours at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        is_open = in_market_hours()
        logger.info(f"[CHECK] in_market_hours() = {is_open}")
        if not is_open:
            logger.info("[CHECK] Market is CLOSED according to logic. Waiting for open.")
            wait_for_open()
            continue
        logger.info("[CHECK] Market is OPEN! Proceeding to scan symbols...")
        # prove the logging pipeline is alive even when no alerts fire
        try:
            log_heartbeat("scan_start", {
                "min_signals": os.getenv("MIN_SIGNALS") or "",
                "vwap_thresh": os.getenv("VWAP_THRESHOLD") or ""
            })
        except Exception:
            pass

        for sym in syms:
            logger.info(f"→Scanning {sym}")
            try:
                alert = analyze_symbol(sym)
                if alert:
                    # --- CSV LOG FIRST (don’t let logging break trading) ---
                    try:
                        log_trigger({
                            "symbol":        alert.get("symbol") or sym,
                            "price":         float(alert.get("price") or 0),
                            "ADX":           alert.get("adx"),
                            "ATR_val":       alert.get("atr"),
                            "ATR_pct":       alert.get("atr_pct"),
                            "Supertrend":    alert.get("supertrend") or alert.get("super_sig"),
                            "RSI":           alert.get("rsi"),
                            "MACD":          alert.get("macd_cross") or alert.get("macd"),
                            "BB_breakout":   alert.get("bb_breakout"),
                            "Vol_mult":      alert.get("vol_mult") or alert.get("volume_multiplier"),
                            "VWAP_diff_pct": alert.get("vwap_diff_pct") or alert.get("vwap_diff"),
                            "ATR_ge":        alert.get("atr_ok"),
                            "ATRpct_ge":     alert.get("atr_pct_ok"),
                            "Range_ge":      alert.get("range_ok"),
                            "Gap_ge":        alert.get("gap_ok"),
                            "Price_gt_SMA":  alert.get("price_gt_sma") or alert.get("price_sma_ok"),
                            "signals":       alert.get("triggers") or [alert.get("filter_name")],
                        })
                    except Exception:
                        pass
                    # --- existing behavior ---
                    insert_alert(**alert)
                    logger.info(f"→ Alert for {sym} inserted successfully.")
                else:
                    logger.info(f"→ {sym}: No alert generated this round.")

        # pause between sweeps
        time.sleep(60)

# At the bottom of scanner.py
def run_scan():
    # your scanning logic here
    print("Running scan...")

if __name__ == "__main__":
    main(simulation=False)
