import time
import logging
from datetime import datetime
from pathlib import Path
import yfinance as yf
from services.etrade_service import fetch_etrade_quote
from services.trading_helpers import (
    set_cash, buy_stock, sell_stock, get_cash, nuke_simulation_db
)
from services.market_service import fetch_data_with_timeout

# configure logging
tools = logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s %(levelname)7s %(message)s")

# control flag for the simulation loop
_sim_stop = False

def stop_simulation():
    """Signal the running simulation loop to exit on next iteration."""
    global _sim_stop
    _sim_stop = True


def load_symbols():
    """Load the list of symbols from your SP500 file."""
    p = Path(__file__).parent.parent / "sp500_symbols.txt"
    return [s.strip() for s in p.read_text().splitlines() if s.strip()]


def calculate_qty(settings, data):
    """Turn max_per_trade into whole-share qty based on latest price."""
    try:
        price   = float(data.get("price") if isinstance(data, dict) else getattr(data, "price", 0))
        max_amt = float(settings.max_per_trade)
        if price <= 0:
            return 0
        qty = int(max_amt // price)
        return max(qty, 1)
    except Exception as e:
        logging.error(f"[sim] calculate_qty error: {e}")
        return 1


def evaluate_exit(pos, settings):
    """Return True if any exit condition fires (trailing-stop or sell-after-days)."""
    price = pos.get("price", 0)
    # trailing stop
    if getattr(settings, 'use_trailing_stop', False):
        peak = pos.get("peak_price", price)
        if price <= peak * (1 - settings.trailing_stop_pct):
            return True
    # time-based exit
    entry_time = pos.get("entry_time")
    if getattr(settings, 'sell_after_days', None) and entry_time:
        if (datetime.utcnow() - entry_time).days >= settings.sell_after_days:
            return True
    return False


def run_simulation_loop(settings):
    logging.debug(f"[sim] starting run_simulation_loop with settings={settings}")
    # reset database & seed cash
    nuke_simulation_db()
    set_cash(settings.starting_cash)
    logging.debug(f"[sim] after seed cash: {get_cash()}")

    positions = {}
    symbols   = load_symbols()

    while not _sim_stop:
        # ENTRY scan
        for sym in symbols:
            df = fetch_data_with_timeout(sym)
            if df is None or df.empty:
                logging.debug(f"[sim] no data for {sym}, skipping")
                continue

            latest = df.iloc[-1]
            price  = float(latest["Close"])
            vwap   = float(latest.get("VWAP", 0.0))

            logging.debug(f"[sim] {sym}: price={price}, vwap={vwap}")

            if getattr(settings, 'vwap_on', False) and (price - vwap) < settings.vwap_threshold:
                logging.debug(f"[sim] {sym} filtered by VWAP")
                continue
            if getattr(settings, 'single_entry_only', False) and sym in positions:
                logging.debug(f"[sim] {sym} already in positions")
                continue

            # calculate order size
            data = {"symbol": sym, "price": price, "vwap": vwap}
            qty  = calculate_qty(settings, data)
            t0   = datetime.utcnow().isoformat(sep=' ')

            try:
                buy_stock(sym, qty, price, trade_time=t0)
                logging.info(f"[sim] BUY {sym} x{qty} @ {price}")
                positions[sym] = {
                    "entry_time": datetime.fromisoformat(t0),
                    "qty":        qty,
                    "peak_price": price,
                    "price":      price
                }
            except ValueError as e:
                logging.warning(f"[sim] skip BUY {sym}: {e} ({qty}@{price})")

        # EXIT scan
        for sym, pos in list(positions.items()):
            df = fetch_data_with_timeout(sym)
            if df is None or df.empty:
                continue
            price = float(df.iloc[-1]["Close"])
            pos["price"] = price
            logging.debug(f"[sim] {sym} now at price={price}")

            if evaluate_exit(pos, settings):
                t1 = datetime.utcnow().isoformat(sep=' ')
                try:
                    sell_stock(sym, pos["qty"], pos["price"], trade_time=t1)
                    logging.info(f"[sim] SELL {sym} x{pos['qty']} @ {pos['price']}")
                except ValueError as e:
                    logging.warning(f"[sim] skip SELL {sym}: {e}")
                positions.pop(sym)

        # Pause until next iteration (default to 60s if not set)
        time.sleep(getattr(settings, 'poll_interval', 60))
