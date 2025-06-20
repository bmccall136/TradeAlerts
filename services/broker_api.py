# services/broker_api.py

import sqlite3, time
from pathlib import Path

SIM_DB = str(Path(__file__).parent.parent / "simulation.db")

def buy_stock(symbol, qty):
    # record a BUY in your simulation DB
    conn = sqlite3.connect(SIM_DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO trades(symbol, action, qty, price, timestamp) VALUES (?,?,?, ?,datetime('now'))",
                (symbol, 'BUY', qty, get_price(symbol)))
    conn.commit()
    conn.close()

def sell_stock(symbol):
    # record a SELL
    conn = sqlite3.connect(SIM_DB)
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
