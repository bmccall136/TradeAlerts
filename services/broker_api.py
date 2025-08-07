from settings import SIMULATION_DB
import os
os.environ["ALERT_DB_PATH"] = SIMULATION_DB
import sqlite3, time
from pathlib import Path

from services.trading_helpers import (
    get_cash,
    set_cash,
    get_avg_cost,
    insert_trade,
    insert_or_update_holding,
    get_position,        # If used below
)
from services.etrade_service import fetch_etrade_quote

def get_price(symbol: str) -> float:
    """
    Fetch the current live price for `symbol`.
    """
    return fetch_etrade_quote(symbol)


def fetch_live_data(symbol: str) -> float:
    """
    Your existing fetch_live_data; just make sure it calls get_price().
    """
    price = get_price(symbol)
    return price

def buy_stock(symbol, qty):
    # record a BUY in your simulation DB
    conn = sqlite3.connect(SIMULATION_DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO trades(symbol, action, qty, price, timestamp) VALUES (?,?,?, ?,datetime('now'))",
                (symbol, 'BUY', qty, get_price(symbol)))
    conn.commit()
    conn.close()

def sell_stock(symbol: str, qty: int, price: float, trade_time: str = None):
    """
    Sells `qty` shares of `symbol` at `price`.
    """
    # Deduct qty from holdings (or set to zero if selling all)
    holding = get_position(symbol)
    if not holding or holding.get("qty", 0) < qty:
        raise RuntimeError(f"Not enough shares to sell for {symbol} (have {holding.get('qty', 0)}, tried to sell {qty})")

    proceeds = qty * price
    set_cash(get_cash() + proceeds)
    avg = get_avg_cost(symbol)
    pnl = (price - avg) * qty

    insert_trade(symbol, 'SELL', price, qty, pnl, trade_time)
    insert_or_update_holding(symbol, qty=-qty, avg_cost=avg, last_price=price)

def fetch_live_data(symbol):
    # fetch price + indicators however you do it
    price = get_price(symbol)
    return {
        "symbol": symbol,
        "price": price,
        "sma":  price * 0.98,   # placeholder
        "rsi":  55.2,           # placeholder
        # …
    }

# you’ll probably need get_price, get_qty, etc.
