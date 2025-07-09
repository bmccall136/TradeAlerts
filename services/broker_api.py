# services/broker_api.py

import sqlite3, time
from pathlib import Path

SIM_DB = str(Path(__file__).parent.parent / "simulation.db")
# services/broker_api.py

from services.etrade_service import fetch_etrade_quote

# alias for backward compatibility
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

def sell_stock(symbol):
    # record a SELL
    conn = sqlite3.connect(SIMULATION_DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO trades(symbol, action, qty, price, timestamp) VALUES (?,?,?, ?,datetime('now'))",
                (symbol, 'SELL', get_qty(symbol), get_price(symbol)))
    conn.commit()
    conn.close()

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
