# services/simulation_service.py

import logging
import time                # (module, for time.sleep etc.)
from datetime import datetime, timedelta, time as dt_time
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo
from services.trading_helpers       import buy_stock, set_cash, insert_trade, insert_or_update_holding
from services.market_service        import analyze_symbol
from services.trading_helpers import market_is_open, seconds_until_open
import pandas as pd
import pandas_market_calendars as mcal
from requests.exceptions import HTTPError

from services.trading_helpers import (
    setup_simulation_db,
    set_cash,
    get_cash,
    record_trade,
    get_positions,
)
from services.market_service import fetch_data_with_timeout, get_symbols
from services.etrade_service import fetch_etrade_quote
from settings import SIMULATION_DB

# module-level logger
logger     = logging.getLogger("sim")
sim_logger = logger

# flag to stop the simulation loop
_sim_stop  = False

# set up NYSE calendar and timezone
ET   = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")

def market_is_open():
    """
    Return True if NYSE is open right now, based on pandas_market_calendars schedule.
    """
    today = datetime.now(ET).date()
    schedule = nyse.schedule(start_date=today, end_date=today)
    if schedule.empty:
        return False

    # extract the single row for today
    row = schedule.iloc[0]

    # these are pandas.Timestamp localized to ET
    today_open_ts  = row.market_open
    today_close_ts = row.market_close

    # compare only the time portion
    market_open_time  = today_open_ts.time()
    market_close_time = today_close_ts.time()
    now_time          = datetime.now(ET).time()

    # also enforce normal NYSE clock (9:30 – 16:00)
    normal_open  = dt_time(9, 30)
    normal_close = dt_time(16, 0)

    return (
        (market_open_time  <= now_time <= market_close_time)
        and
        (normal_open       <= now_time <= normal_close)
    )

def seconds_until_open():
    now = datetime.now(ET)
    schedule = nyse.schedule(start_date=now.date(), end_date=(now + timedelta(days=2)).date())
    # find the next open time after now
    for idx, row in schedule.iterrows():
        open_dt = row.market_open.tz_convert(ET)
        close_dt = row.market_close.tz_convert(ET)
        if now < open_dt:
            return (open_dt - now).total_seconds()
        elif open_dt <= now <= close_dt:
            return 0
    return 24*3600  # fallback

from settings import _sim_stop
import time
from datetime import datetime
from services.broker_api import buy_stock, sell_stock, fetch_etrade_quote
from settings                import _sim_stop
import logging

logger = logging.getLogger("sim")

import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from services.settings_schema   import SimulationSettings
from services.risk_management   import wash_sale_prohibited, funds_not_settled
from services.trading_helpers   import (
    set_cash, get_cash, compute_qty,
)
from services.broker_api        import buy_stock, sell_stock
from services.market_service   import get_symbols
from services.trading_helpers import (
    setup_simulation_db,
    set_cash,
    get_cash,
    record_trade,
    get_positions,
)

from services.simulation_service import market_is_open, seconds_until_open

logger = logging.getLogger("sim")
_sim_stop = False

from services.settings_schema import SimulationSettings
# …other imports…

from datetime import datetime
import time
from services.trading_helpers import (
    buy_stock,
    insert_trade,
    insert_or_update_holding,
    compute_qty,
    get_cash,
)
from services.trading_helpers     import (
    buy_stock,
    set_cash,
    insert_trade,
    insert_or_update_holding,
    market_is_open,
    seconds_until_open,
)
from services.market_service       import analyze_symbol
# …the rest of your imports…
from services.risk_management import wash_sale_prohibited, funds_not_settled
from services.trading_helpers import setup_simulation_db, check_exit_orders
import logging

logger = logging.getLogger("sim")

def run_simulation_loop(settings: SimulationSettings):
    """
    Main simulation loop. `settings` is built by extract_simulation_settings().
    """

    # 1) ensure schema exists (and wipe if requested)
    setup_simulation_db()
    if settings.nuke_db:
        setup_simulation_db()

    # 2) seed starting cash
    from services.trading_helpers import set_cash, get_cash
    set_cash(settings.starting_cash)
    logger.info(f"[SIM] seed cash: ${get_cash():.2f}")

    # 3) load symbols
    symbols = get_symbols(simulation=True)
    logger.info(f"[SIM] Scanning {len(symbols)} symbols every minute…")

    while not _sim_stop:
        # ── market pause logic ─────────────────────────
        if settings.pause_when_market_closed and not market_is_open():
            wait = seconds_until_open()
            logger.info(f"[SIM] Market closed — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        # ── one pass over all symbols ───────────────────
        for sym in symbols:
            now = datetime.utcnow().isoformat()

            # A) analyze
            result = analyze_symbol(sym, settings)
            if not result or not result.get("triggers"):
                # nothing to do
                continue

            # B) count & log ALERT x/y
            triggers = result["triggers"]
            passed   = len(triggers)
            total    = sum((
                settings.sma_on,
                settings.rsi_on,
                settings.macd_on,
                settings.bb_on,
                settings.vol_on,
                settings.vwap_on,
                settings.news_on,
                settings.rsi_slope_on,
                settings.macd_hist_on,
                settings.bb_breakout_on,
            ))
            icon = "🚀" if passed == total else "⚠️" if passed else "❌"
            logger.info(f"[SIM] ALERT {sym} ({passed}/{total}) {icon}: {triggers}")

            # C) entry guard: only if all passed
            if passed != total:
                continue

            # D) wash-sale & settlement
            ts_now = datetime.utcnow()
            if wash_sale_prohibited(sym, ts_now, trade_log):
                logger.info(f"⛔ Skipping {sym} due to wash-sale rule")
                continue
            if funds_not_settled(sym, ts_now):
                logger.info(f"⛔ Skipping {sym} – funds not yet settled")
                continue

            # E) sizing & affordability
            price        = result["price"]
            qty          = compute_qty(settings, price)
            cost         = qty * price
            cash_on_hand = get_cash()
            if qty < 1 or cost > cash_on_hand:
                logger.info(f"[SKIP] {sym} cost ${cost:.2f} vs cash ${cash_on_hand:.2f}")
                continue

            # F) BUY!
            try:
                buy_stock(sym, qty, price)
                insert_trade(sym, "BUY", price, qty)
                insert_or_update_holding(sym, qty, price, price)
                trade_log.append({"symbol": sym, "action": "BUY", "time": ts_now})
                positions[sym] = {"entry_time": ts_now, "qty": qty, "entry_price": price}
                logger.info(f"✅ BUY   {sym} x{qty} @ {price:.2f}")
            except Exception as e:
                logger.error(f"❌ BUY failed {sym}: {e}", exc_info=True)

        # ─── exit logic ─────────────────────────────────────────
        check_exit_orders(settings)

        logger.info("⏸ Scan complete – sleeping 60s…")
        time.sleep(settings.poll_interval or 60)

def stop_simulation():
    global _sim_stop
    _sim_stop = True

# ── helpers ─────────────────────────────────────────────────────

def load_symbols():
    """Load the list of symbols from your SP500 file."""
    p = Path(__file__).parent.parent / "sp500_symbols.txt"
    return [s.strip() for s in p.read_text().splitlines() if s.strip()]

def calculate_qty(settings, data):
    """
    Turn max_per_trade into whole‐share qty based on latest price.
    Expects `data['price']` to be the live price.
    """
    try:
        price   = float(data.get("price") if isinstance(data, dict) else getattr(data, "price", 0))
        max_amt = float(settings.max_per_trade)
        if price <= 0:
            return 0
        qty = int(max_amt // price)
        return qty        # no fallback to 1
    except Exception as e:
        logging.error(f"[sim] calculate_qty error: {e}")
        return 0         # safest: treat errors as zero

def evaluate_exit(pos, settings):
    price = pos['price']
    entry = pos['entry_price']
    # 1) stop‐loss
    if settings.stop_loss_pct and price <= entry * (1 - settings.stop_loss_pct/100):
        return True
    # 2) take‐profit
    if settings.take_profit_pct and price >= entry * (1 + settings.take_profit_pct/100):
        return True
    # 3) trailing‐stop
    if settings.use_trailing_stop:
        peak = pos['peak_price']
        if price <= peak * (1 - settings.trailing_stop_pct):
            return True
    # 4) time‐based
    return False


