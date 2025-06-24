# services/trading_helpers.py

import os
import sqlite3
from pathlib import Path

SIM_DB = os.path.join(os.getcwd(), 'simulation.db')

from services.market_service import fetch_data_with_timeout

def buy_stock(symbol, qty, price, trade_time=None):
    """
    Record a buy: update holdings (avg cost) and append to trades.
    """
    conn = _connect()
    cur  = conn.cursor()
    # … your existing logic from before …
    conn.commit()
    conn.close()

def sell_stock(symbol, qty, price, trade_time=None):
    """
    Record a sell: deduct holdings, compute P&L, and append to trades.
    """
    conn = _connect()
    cur  = conn.cursor()
    # … your existing logic from before …
    conn.commit()
    conn.close()

def get_unrealized_pl():
    """
    Compute P&L on open positions by fetching the latest price.
    """
    total = 0.0
    for symbol, qty, price_paid in get_holdings():
        df = fetch_data_with_timeout(symbol)
        if df is not None and not df.empty:
            last_price = float(df["Close"].iloc[-1])
        else:
            last_price = price_paid
        total += (last_price - price_paid) * qty
    return total

def _connect():
    return sqlite3.connect(SIM_DB, detect_types=sqlite3.PARSE_DECLTYPES)

def init_simulation_db():
    """
    Drops any old simulation.db and recreates it from scratch with the right tables.
    """
    # ensure the file is gone
    f = Path(SIM_DB)
    if f.exists():
        f.unlink()

    conn = _connect()
    cur  = conn.cursor()

    # Create all three tables with the exact columns you use below:
    cur.execute("""
      CREATE TABLE state (
        key   TEXT PRIMARY KEY,
        value REAL
      );
    """)
    cur.execute("""
      CREATE TABLE holdings (
        symbol     TEXT PRIMARY KEY,
        qty        INTEGER,
        price_paid REAL
      );
    """)
    cur.execute("""
      CREATE TABLE trades (
        symbol     TEXT,
        action     TEXT,
        price      REAL,
        qty        INTEGER,
        trade_time TEXT,
        pnl        REAL
      );
    """)
    conn.commit()
    conn.close()

def nuke_simulation_db():
    """
    User-land routine to wipe & rebuild the DB.
    """
    init_simulation_db()

def set_cash(amount):
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value REAL)")
    cur.execute("""
      INSERT INTO state (key, value)
        VALUES ('cash', ?)
      ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (amount,))
    conn.commit()
    conn.close()

def get_cash():
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT value FROM state WHERE key='cash'")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def get_holdings():
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT symbol, qty, price_paid FROM holdings")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_trades():
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
      SELECT symbol, action, price, qty, trade_time, pnl
        FROM trades
       ORDER BY trade_time ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return [
      (r['symbol'], r['action'], r['price'], r['qty'], r['trade_time'], r['pnl'])
      for r in rows
    ]

def get_realized_pl():
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT SUM(pnl) FROM trades WHERE action='SELL'")
    total = cur.fetchone()[0] or 0.0
    conn.close()
    return float(total)

# As soon as this module is imported, ensure the DB exists:
if not Path(SIM_DB).exists():
    init_simulation_db()
