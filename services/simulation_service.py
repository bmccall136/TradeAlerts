# services/simulation_service.py

import time
from services.trading_helpers import (
    nuke_simulation_db,
    fetch_live_data,
    buy_stock,
    sell_stock
)
from services.market_service import get_symbols

# flag to tell the loop when to stop
_sim_stop = False

def run_simulation_loop(settings):
    """Background loop—pure orchestration only."""
    global _sim_stop
    _sim_stop = False

    # start fresh
    nuke_simulation_db()

    symbols = get_symbols()
    while not _sim_stop:
        for sym in symbols:
            data = fetch_live_data(sym)
            if evaluate_entry(data, settings):
                qty = calculate_qty(settings, data)
                buy_stock(sym, qty, data["price"])
            if evaluate_exit(data, settings):
                exit_qty = calculate_exit_qty(data)
                sell_stock(sym, exit_qty, data["price"])
        time.sleep(settings.poll_interval)

def stop_simulation():
    """Signal the running loop to exit on next iteration."""
    global _sim_stop
    _sim_stop = True
