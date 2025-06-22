import sqlite3
import os

def _get_db_path():
    return os.path.join(os.getcwd(), 'simulation.db')

SIM_DB = _get_db_path()

# ── CORE DB CONNECTION ────────────────────────────────────────

def _connect():
    """Return a SQLite connection to the simulation DB."""
    return sqlite3.connect(SIM_DB, detect_types=sqlite3.PARSE_DECLTYPES)

# alias for older calls
def get_db_connection():
    return _connect()

# ── SCHEMA MANAGEMENT ─────────────────────────────────────────

def nuke_simulation_db():
    conn = _connect()
    cur  = conn.cursor()

    # drop any old tables first
    cur.execute("DROP TABLE IF EXISTS state")
    cur.execute("DROP TABLE IF EXISTS holdings")
    cur.execute("DROP TABLE IF EXISTS trades")

    # now recreate them
    cur.execute("""
      CREATE TABLE state (
        key   TEXT PRIMARY KEY,
        value REAL
      )
    """)
    cur.execute("""
      CREATE TABLE holdings (
        symbol     TEXT,
        qty        INTEGER,
        price_paid REAL
      )
    """)
    cur.execute("""
      CREATE TABLE trades (
        symbol     TEXT,
        action     TEXT,
        price      REAL,
        qty        INTEGER,
        trade_time TEXT,
        pnl        REAL
      )
    """)

    conn.commit()
    conn.close()

# ── STATE GET/SET ────────────────────────────────────────────

def set_cash(amount):
    """
    Insert or update the 'cash' key in the state table.
    Assumes state table already exists (see nuke_simulation_db).
    """
    conn = _connect()
    cur  = conn.cursor()

    # ensure state table exists
    cur.execute("""CREATE TABLE IF NOT EXISTS state (
                     key TEXT PRIMARY KEY, value REAL
                   )""")
    # upsert
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
    # if table missing, return 0
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='state'")
    if not cur.fetchone():
        conn.close()
        return 0.0

    cur.execute("SELECT value FROM state WHERE key='cash'")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

# ── HOLDING/TRADES CRUD ───────────────────────────────────────

def buy_stock(symbol, qty, price, trade_time=None):
    """
    Record a buy: insert into holdings and trades.
    """
    conn = _connect()
    cur  = conn.cursor()
    # update holdings
    cur.execute("""
      SELECT qty, price_paid FROM holdings WHERE symbol=?
    """, (symbol,))
    existing = cur.fetchone()
    if existing:
        old_qty, old_pp   = existing
        new_qty           = old_qty + qty
        avg_price_paid    = ((old_qty * old_pp) + (qty * price)) / new_qty
        cur.execute("""
          UPDATE holdings SET qty=?, price_paid=? WHERE symbol=?
        """, (new_qty, avg_price_paid, symbol))
    else:
        cur.execute("""
          INSERT INTO holdings (symbol, qty, price_paid)
            VALUES (?, ?, ?)
        """, (symbol, qty, price))

    # record trade
    cur.execute("""
      INSERT INTO trades (symbol, action, price, qty, trade_time, pnl)
        VALUES (?, 'BUY', ?, ?, ?, NULL)
    """, (symbol, price, qty, trade_time))
    conn.commit()
    conn.close()

def sell_stock(symbol, qty, price, trade_time=None):
    """
    Record a sell: update holdings, compute P&L, insert into trades.
    """
    conn = _connect()
    cur  = conn.cursor()
    # fetch existing
    cur.execute("SELECT qty, price_paid FROM holdings WHERE symbol=?", (symbol,))
    row = cur.fetchone()
    if not row or row[0] < qty:
        raise ValueError("Not enough shares")
    old_qty, price_paid = row
    new_qty = old_qty - qty
    if new_qty > 0:
        cur.execute("""
          UPDATE holdings SET qty=? WHERE symbol=?
        """, (new_qty, symbol))
    else:
        cur.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))

    # compute P&L
    pnl = (price - price_paid) * qty

    # record
    cur.execute("""
      INSERT INTO trades (symbol, action, price, qty, trade_time, pnl)
        VALUES (?, 'SELL', ?, ?, ?, ?)
    """, (symbol, price, qty, trade_time, pnl))

    conn.commit()
    conn.close()

def get_holdings():
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT symbol, qty, price_paid FROM holdings")
    rows = cur.fetchall()
    conn.close()
    # return list of tuples
    return rows

def get_trades():
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT symbol, action, price, qty, trade_time, pnl FROM trades ORDER BY trade_time ASC")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_realized_pl():
    """
    Sum of all SELL P&L.
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT SUM(pnl) FROM trades WHERE action='SELL'")
    total = cur.fetchone()[0]
    conn.close()
    return float(total or 0.0)
