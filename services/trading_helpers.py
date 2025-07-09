import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from settings import SIMULATION_DB, BACKTEST_DB
import logging

# a module‐level logger for trading_helpers:
logger = logging.getLogger(__name__)
 
# at the top of services/trading_helpers.py
from services.broker_api import buy_stock, sell_stock


def _connect():
    return sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
def setup_simulation_db():
    """
    Create our core simulation tables (state, holdings, positions,
    simulation_trades, alerts) if they don’t already exist.
    """
    conn = sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    cur  = conn.cursor()

    # state table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id           INTEGER PRIMARY KEY CHECK (id = 1),
            cash         REAL DEFAULT 0,
            realized_pl  REAL DEFAULT 0
        )
    """)

    # holdings table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            symbol     TEXT PRIMARY KEY,
            qty        INTEGER NOT NULL,
            avg_cost   REAL NOT NULL,
            last_price REAL NOT NULL
        )
    """)

    # open positions (for exit logic)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol    TEXT,
            entry_ts  TIMESTAMP,
            entry_px  REAL,
            qty       INTEGER,
            stop_px   REAL,
            target_px REAL
        )
    """)

    # trade history
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simulation_trades (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT NOT NULL,
            action     TEXT CHECK(action IN ('BUY','SELL')) NOT NULL,
            price      REAL NOT NULL,
            qty        INTEGER NOT NULL,
            trade_time TEXT NOT NULL,
            pnl        REAL
        )
    """)

    # ── ALERTS: drop old and recreate with `timestamp` ──
    cur.execute("DROP TABLE IF EXISTS alerts;")
    cur.execute("""
        CREATE TABLE alerts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT    NOT NULL,
            price      REAL    NOT NULL,
            timestamp  TEXT    NOT NULL,    -- renamed from `time`
            cleared    TEXT,
            name       TEXT,
            vwap       REAL,
            vwap_diff  REAL,
            triggers   TEXT,
            sparkline  BLOB
        )
    """)

    # ensure we have one row in state
    cur.execute("INSERT OR IGNORE INTO state (id, cash, realized_pl) VALUES (1, 10000, 0);")

    conn.commit()
    conn.close()

# ——— Cash accessors —————————————————————————————
def get_cash() -> float:
    """Return current cash balance."""
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def set_cash(amount: float):
    """Overwrite cash balance (used by dashboard reset etc)."""
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (amount,))
    conn.commit()
    conn.close()
# ─── Internal connect helper ────────────────────────────────
def _connect(db: str = 'simulation'):
    return sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)

# ─── Portfolio accessors ────────────────────────────────────
def check_if_position_open(symbol: str) -> bool:
    """
    Return True if there's any net long position for the symbol.
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT qty FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return (row[0] if row else 0) > 0

def compute_qty(settings, price: float) -> int:
    """
    Compute shares to buy based on max_per_trade.
    """
    return max(1, int(settings.max_per_trade / price))

# ——— New ENTER/EXIT logic —————————————————————————————
def enter_trade(symbol, price, qty, timestamp, settings):
    conn = _connect()
    cur  = conn.cursor()

    # 1) Record the trade
    cur.execute(
        "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time) "
        "VALUES (?, 'BUY', ?, ?, ?)",
        (symbol, price, qty, timestamp)
    )

    # 2) Deduct cash
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    cash = cur.fetchone()[0]
    new_cash = cash - price * qty
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (new_cash,))

    # 3) Upsert holdings
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?;", (symbol,))
    row = cur.fetchone()
    if row:
        old_qty, old_cost = row
        combined_qty = old_qty + qty
        # new avg_cost = weighted average
        new_avg = (old_cost * old_qty + price * qty) / combined_qty
        cur.execute(
            "UPDATE holdings SET qty = ?, avg_cost = ?, last_price = ? "
            "WHERE symbol = ?;",
            (combined_qty, new_avg, price, symbol)
        )
    else:
        cur.execute(
            "INSERT INTO holdings (symbol, qty, avg_cost, last_price) "
            "VALUES (?, ?, ?, ?)",
            (symbol, qty, price, price)
        )

    conn.commit()
    conn.close()

    logger.info(f"ENTER  {symbol}  qty={qty} @ {price:.2f}, cash left=${new_cash:.2f}")

def check_exit_orders(settings) -> None:
    """
    Scan open positions and execute sells based on stop-loss, take-profit, and time-based exits.
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT symbol, qty, avg_cost FROM holdings;")
    positions = cur.fetchall()
    conn.close()

    from services.broker_api import sell_stock

    for symbol, qty, avg_cost in positions:
        try:
            current = fetch_etrade_quote(symbol)
        except Exception:
            continue

        pnl_pct = ((current - avg_cost) / avg_cost * 100) if avg_cost else 0.0

        # stop-loss
        if settings.stop_loss_pct and pnl_pct <= -settings.stop_loss_pct:
            sell_stock(symbol, qty, current)
            continue

        # take-profit
        if settings.take_profit_pct and pnl_pct >= settings.take_profit_pct:
            sell_stock(symbol, qty, current)
            continue

        # time-based exit
        if settings.sell_after_days:
            conn2 = _connect()
            c2    = conn2.cursor()
            c2.execute(
                "SELECT trade_time FROM simulation_trades "
                "WHERE symbol=? AND action='BUY' "
                "ORDER BY trade_time ASC LIMIT 1;",
                (symbol,)
            )
            first_time = c2.fetchone()[0]
            conn2.close()
            # if held longer than configured days
            from datetime import datetime, timedelta
            entry_dt = datetime.fromisoformat(first_time)
            if datetime.utcnow() - entry_dt >= timedelta(days=settings.sell_after_days):
                sell_stock(symbol, qty, current)

def exit_trade(symbol: str, price: float, qty: int, trade_time: str):
    conn = _connect()
    c    = conn.cursor()

    # 1) record the SELL
    c.execute("""
      INSERT INTO simulation_trades(symbol, action, price, qty, trade_time)
      VALUES (?, 'SELL', ?, ?, ?)
    """, (symbol, price, qty, trade_time))

    # 2) credit cash
    c.execute("UPDATE state SET cash = cash + ? WHERE id = 1;", (price * qty,))

    # 3) realized P/L
    c.execute("SELECT avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    avg_cost = c.fetchone()[0]
    pl = (price - avg_cost) * qty
    c.execute("UPDATE state SET realized_pl = realized_pl + ? WHERE id = 1;", (pl,))

    # 4) shrink or delete holdings
    c.execute("SELECT qty FROM holdings WHERE symbol = ?", (symbol,))
    current_qty = c.fetchone()[0]
    if qty < current_qty:
        new_qty = current_qty - qty
        c.execute("""
          UPDATE holdings
             SET qty = ?, last_price = ?
           WHERE symbol = ?
        """, (new_qty, price, symbol))
    else:
        c.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))

    conn.commit()
    conn.close()
# ─── Portfolio overview ─────────────────────────────────────────
def get_holdings() -> list:
    """
    Return a list of current holdings as tuples:
      (symbol:str, qty:int, avg_cost:float, last_price:float)
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings;")
    rows = cur.fetchall()
    conn.close()
    return rows

# ─── Trade history ─────────────────────────────────────────
def get_trades(limit: int = 100) -> list:
    """
    Return the most recent simulated trades as:
      [(trade_time, symbol, action, qty, price, pnl), ...]
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("""
      SELECT trade_time, symbol, action, qty, price, pnl
        FROM simulation_trades
       ORDER BY trade_time DESC
       LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ─── P/L metrics ────────────────────────────────────────────
def get_realized_pl() -> float:
    """Return total realized P/L from your simulation state."""
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT realized_pl FROM state WHERE id = 1;")
    row = cur .fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def get_unrealized_pl() -> float:
    """
    Sum up (last_price - avg_cost) * qty for all open holdings.
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT qty, avg_cost, last_price FROM holdings;")
    total = 0.0
    for qty, avg_cost, last_price in cur.fetchall():
        total += (last_price - avg_cost) * qty
    conn.close()
    return total
def init_backtest_db():
    """
    Create the backtest database schema (independent of simulation).
    """
    from settings import BACKTEST_DB
    # You may already have BACKTEST_SCHEMA defined somewhere
    from config import BACKTEST_SCHEMA  

    conn = sqlite3.connect(BACKTEST_DB)
    conn.executescript(BACKTEST_SCHEMA)
    conn.commit()
    conn.close()
