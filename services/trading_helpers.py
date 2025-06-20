import sqlite3
from datetime import datetime
from pathlib import Path
import yfinance as yf

# point to your simulation.db
SIM_DB = str(Path(__file__).resolve().parent.parent / "simulation.db")

# ── CORE DB HELPERS ────────────────────────────────────────────

def _connect():
    return sqlite3.connect(SIM_DB, detect_types=sqlite3.PARSE_DECLTYPES)


def nuke_simulation_db():
    """Wipe and recreate the simulation schema."""
    conn = _connect()
    cur = conn.cursor()
    # drop tables if they exist
    cur.execute("DROP TABLE IF EXISTS state;")
    cur.execute("DROP TABLE IF EXISTS holdings;")
    cur.execute("DROP TABLE IF EXISTS simulation_trades;")
    # recreate
    cur.execute("""
      CREATE TABLE state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        cash REAL DEFAULT 0,
        realized_pl REAL DEFAULT 0
      );
    """)
    cur.execute("""
      CREATE TABLE holdings (
        symbol TEXT PRIMARY KEY,
        qty INTEGER NOT NULL,
        avg_cost REAL NOT NULL,
        last_price REAL NOT NULL
      );
    """)
    cur.execute("""
      CREATE TABLE simulation_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        action TEXT CHECK (action IN ('BUY','SELL')) NOT NULL,
        price REAL NOT NULL,
        qty INTEGER NOT NULL,
        trade_time TEXT NOT NULL,
        pnl REAL
      );
    """)
    # initialize cash row
    cur.execute("INSERT INTO state (id, cash, realized_pl) VALUES (1, 10000, 0);")
    conn.commit()
    conn.close()


def get_symbols():
    """Return the list of symbols to simulate. Replace with your universe."""
    return ["AAPL", "MSFT", "GOOG"]


def get_cash():
    """Return current cash."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_holdings():
    """Return all current holdings as (symbol, qty, avg_cost, last_price)."""
    conn = _connect()
    cur = conn.cursor()
    rows = cur.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings").fetchall()
    conn.close()
    return rows


def get_realized_pl():
    """Return total realized P/L so far."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT realized_pl FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_trades():
    """Return all simulation trades."""
    conn = _connect()
    cur = conn.cursor()
    rows = cur.execute("""
      SELECT symbol, action, price, qty, trade_time, pnl
      FROM simulation_trades
      ORDER BY trade_time
    """).fetchall()
    conn.close()
    return rows


# ── MARKET DATA ────────────────────────────────────────────────

def fetch_live_data(symbol: str) -> dict:
    """
    Pull the latest minute‐bar quote via yfinance.
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="1d", interval="1m")
    last = df.iloc[-1]
    return {
        "symbol":   symbol,
        "price":    float(last["Close"]),
        "volume":   int(last["Volume"]),
        "datetime": last.name.to_pydatetime()
    }


# ── TRADING OPS ───────────────────────────────────────────────

def buy_stock(symbol: str, quantity: int, price: float):
    """Execute a BUY in the simulation DB."""
    conn = _connect()
    cur  = conn.cursor()
    total_cost = price * quantity

    # check cash
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    if not row or float(row[0]) < total_cost:
        conn.close()
        raise ValueError("Insufficient cash to buy.")

    now = datetime.utcnow().isoformat(sep=' ')

    # record trade
    cur.execute("""
      INSERT INTO simulation_trades
        (symbol, action, price, qty, trade_time, pnl)
      VALUES (?, 'BUY', ?, ?, ?, NULL);
    """, (symbol, price, quantity, now))

    # update cash
    new_cash = float(row[0]) - total_cost
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (new_cash,))

    # upsert holdings
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?;", (symbol,))
    hold = cur.fetchone()
    if hold:
        old_qty, old_avg = hold
        new_qty = old_qty + quantity
        new_avg = ((old_avg * old_qty) + total_cost) / new_qty
        cur.execute("""
          UPDATE holdings
             SET qty = ?, avg_cost = ?, last_price = ?
           WHERE symbol = ?;
        """, (new_qty, new_avg, price, symbol))
    else:
        cur.execute("""
          INSERT INTO holdings (symbol, qty, avg_cost, last_price)
          VALUES (?, ?, ?, ?);
        """, (symbol, quantity, price, price))

    conn.commit()
    conn.close()


def sell_stock(symbol: str, quantity: int, price: float):
    """Execute a SELL in the simulation DB."""
    conn = _connect()
    cur  = conn.cursor()

    # state
    cur.execute("SELECT cash, realized_pl FROM state WHERE id = 1;")
    cash_now, realized = cur.fetchone()

    # holding
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?;", (symbol,))
    hold = cur.fetchone()
    if not hold or quantity > hold[0]:
        conn.close()
        raise ValueError("Not enough shares to sell.")
    old_qty, avg_cost = hold

    # compute
    proceeds    = price * quantity
    realized_pl = (price - avg_cost) * quantity
    now = datetime.utcnow().isoformat(sep=' ')

    # record trade
    cur.execute("""
      INSERT INTO simulation_trades
        (symbol, action, price, qty, trade_time, pnl)
      VALUES (?, 'SELL', ?, ?, ?, ?);
    """, (symbol, price, quantity, now, realized_pl))

    # update holdings
    new_qty = old_qty - quantity
    if new_qty > 0:
        cur.execute("""
          UPDATE holdings
             SET qty = ?, last_price = ?
           WHERE symbol = ?;
        """, (new_qty, price, symbol))
    else:
        cur.execute("DELETE FROM holdings WHERE symbol = ?;", (symbol,))

    # credit cash & P/L
    cur.execute("UPDATE state SET cash = ?, realized_pl = ? WHERE id = 1;",
                (cash_now + proceeds, realized + realized_pl))

    conn.commit()
    conn.close()


# ── CONTROL LOOP FLAG ────────────────────────────────────────

_sim_stop = False

def stop_simulation():
    """Signal the background loop to exit."""
    global _sim_stop
    _sim_stop = True
