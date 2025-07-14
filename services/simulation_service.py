# services/simulation_service.py

import csv
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from settings import SIMULATION_DB, _sim_stop
from services.settings_schema import SimulationSettings
from services.trading_helpers import (
    setup_simulation_db,
    set_cash,
    get_cash,
    insert_trade,
    insert_or_update_holding,
    compute_qty,
    seconds_until_open,
    check_exit_orders,
)
from services.market_service import analyze_symbol, get_symbols
from services.risk_management import wash_sale_prohibited, funds_not_settled
from services.broker_api import buy_stock, sell_stock

# ── module-level logger ─────────────────────────────────────
logger = logging.getLogger("sim")

# ── NYSE calendar setup ────────────────────────────────────
ET   = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")

# ── helper to avoid name clash ─────────────────────────────
def _is_market_open():
    today = datetime.now(ET).date()
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        return False
    open_t  = sched.iloc[0].market_open.time()
    close_t = sched.iloc[0].market_close.time()
    now_t   = datetime.now(ET).time()
    return open_t <= now_t <= close_t

# ── trigger-log CSV path ───────────────────────────────────
LOGFILE = Path("logs/triggers.csv")
LOGFILE.parent.mkdir(parents=True, exist_ok=True)


def run_simulation_loop(settings: SimulationSettings):
    """
    Main simulation loop. `settings` is a SimulationSettings object.
    """
    # ── 1) DB setup ─────────────────────────────────────────
    setup_simulation_db()
    if getattr(settings, "nuke_db", False):
        setup_simulation_db()

    # ── 2) Seed cash ────────────────────────────────────────
    set_cash(settings.starting_cash)
    logger.info(f"[SIM] seed cash: ${get_cash():.2f}")

    # ── 3) Load symbols ─────────────────────────────────────
    symbols = get_symbols()
    logger.info(f"[SIM] Scanning {len(symbols)} symbols every loop…")

    # ── 4) Build indicator columns from settings ────────────
    INDICATOR_COLUMNS = [
        f"SMA 📈({settings.sma_length})",
        "RSI 📈",
        "MACD 🚀",
        "BB 📈",
        "VOL 🔊",
        "VWAP+ 💰",
        f"Price>SMA({settings.sma_length})",
        f"ATR14 ≥ {settings.atr_threshold}",
        f"ATR % ≥ {settings.atr_pct}%",
        f"Range % ≥ {settings.range_pct}%",
        f"Gap % ≥ {settings.gap_pct}%",
    ]

    # ── 5) CSV header ────────────────────────────────────────
    if not LOGFILE.exists():
        LOGFILE.parent.mkdir(exist_ok=True)
        with open(LOGFILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "symbol"] + INDICATOR_COLUMNS + ["buy"])

    # ── 6) Count enabled filters ─────────────────────────────
    indicator_keys = [
        "sma_on", "rsi_on", "macd_on", "bb_on",
        "vol_on", "vwap_on",
        "price_sma_on", "atr_on", "atr_pct_on",
        "range_on", "gap_on",
    ]
    total_enabled  = sum(1 for k in indicator_keys if getattr(settings, k, False))
    total_possible = len(INDICATOR_COLUMNS)   # 11
    # we only ever buy when *all* enabled pass:
    threshold      = total_enabled

    # ── Prepare in-memory trade log for wash‐sale checks ─────
    trade_log: list[dict] = []

    # ── 7) Main loop ────────────────────────────────────────
    while not _sim_stop:
        # pause if market closed
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        logger.info("🔁 Starting scan loop iteration")
        for sym in symbols:
            # pull analysis result
            result = analyze_symbol(sym, settings)
            if not result or "price" not in result:
                continue

            price        = result["price"]
            triggers     = result.get("triggers", [])
            passed_total = len(triggers)
            buy_flag     = int(passed_total == total_enabled)

            # build a 0/1 flag for each indicator column
            flags = [int(col in triggers) for col in INDICATOR_COLUMNS]

            # append one CSV row per symbol
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOGFILE, "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([ts, sym] + flags + [buy_flag])

            # log summaries
            logger.info(f"[SIM] ALERT {sym} ({passed_total}/{total_possible}) total : {triggers}")
            logger.info(f"[SIM] ALERT {sym} ({buy_flag}/1) for buy")

            # only buy if every enabled indicator passed
            if buy_flag == 0:
                continue

            # ── 8) wash-sale & settlement ────────────────────────
            now_dt = datetime.utcnow()
            if wash_sale_prohibited(sym, now_dt, trade_log):
                logger.info(f"⛔ Skipping {sym} due to wash-sale rule")
                continue
            if funds_not_settled(sym, now_dt):
                logger.info(f"⛔ Skipping {sym}: funds not yet settled")
                continue

            # ── 9) size order ────────────────────────────────────
            qty  = compute_qty(settings, price)
            cost = qty * price
            if qty < 1 or cost > get_cash():
                logger.info(f"[SKIP] {sym} cost ${cost:.2f} vs cash ${get_cash():.2f}")
                continue

            # ── 🔫 BUY ───────────────────────────────────────────
            try:
                buy_stock(sym, qty, price)
                insert_trade(sym, "BUY", price, qty)
                insert_or_update_holding(sym, qty, price, price)
                trade_log.append({"symbol": sym, "action": "BUY", "time": now_dt})
                logger.info(f"✅ BUY {sym} x{qty} @ ${price:.2f}")
            except Exception as e:
                logger.error(f"❌ Failed to BUY {sym}: {e}")

        # ── 10) exit logic ────────────────────────────────────
        check_exit_orders(settings)

        # ── 11) loop delay ───────────────────────────────────
        delay = getattr(settings, "poll_interval", 0)
        if delay > 0:
            logger.info(f"⏸ Scan complete — sleeping {delay:.1f}s…")
            time.sleep(delay)



def stop_simulation():
    global _sim_stop
    _sim_stop = True
