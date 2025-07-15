import logging
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from settings import SIMULATION_DB, BACKTEST_DB
import pandas as pd
import pandas_market_calendars as mcal

ET   = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")


def market_is_open() -> bool:
    now   = datetime.now(ET)
    today = now.date()

    # fetch just today's schedule
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        # not a trading day
        return False

    # grab the only row
    row     = sched.iloc[0]
    open_dt = row["market_open"].tz_convert(ET)
    close_dt= row["market_close"].tz_convert(ET)

    return open_dt <= now < close_dt


def seconds_until_open() -> float:
    now   = datetime.now(ET)
    today = now.date()

    # look out 7 days for the next open
    sched = nyse.schedule(
        start_date=today,
        end_date=today + timedelta(days=7)
    )
    # iterate rows in order
    for _, row in sched.iterrows():
        open_dt = row["market_open"].tz_convert(ET)
        if open_dt > now:
            return (open_dt - now).total_seconds()

    # fallback: wait one full day
    return 24 * 3600


def _connect():
    return sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)

def insert_or_update_holding(symbol: str, qty: int, avg_cost: float, last_price: float):
    """
    Upsert into the holdings table: if the symbol exists, update its qty, avg_cost, last_price;
    otherwise insert a new row.
    """
    conn = _connect()
    cur  = conn.cursor()

    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()

    if row:
        old_qty, old_avg = row
        total_cost = old_avg * old_qty + avg_cost * qty
        new_qty    = old_qty + qty
        new_avg    = total_cost / new_qty
        cur.execute("""
            UPDATE holdings
               SET qty = ?, avg_cost = ?, last_price = ?
             WHERE symbol = ?
        """, (new_qty, new_avg, last_price, symbol))
    else:
        cur.execute("""
            INSERT INTO holdings(symbol, qty, avg_cost, last_price)
            VALUES (?, ?, ?, ?)
        """, (symbol, qty, avg_cost, last_price))

    conn.commit()
    conn.close()

def record_trade(symbol: str, price: float, qty: int, action: str, pnl: float = None):
    """
    Insert one trade into simulation_trades for your simulation run.
    """
    ts   = datetime.now(ET).isoformat()
    conn = sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    cur  = conn.cursor()
    cur.execute(
      "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time, pnl) "
      "VALUES (?, ?, ?, ?, ?, ?)",
      (symbol, action.upper(), price, qty, ts, pnl)
    )
    conn.commit()
    conn.close()


def get_positions() -> dict:
    """
    Return a dict of net position sizes by symbol.
    """
    conn = sqlite3.connect(SIMULATION_DB)
    cur  = conn.cursor()
    cur.execute(
      "SELECT symbol, SUM(CASE WHEN action='BUY' THEN qty ELSE -qty END) "
      "FROM simulation_trades GROUP BY symbol"
    )
    positions = {sym: net for sym, net in cur.fetchall()}
    conn.close()
    return positions

def get_avg_cost(symbol: str) -> float:
    """
    Fetch the current average cost per share for `symbol` from holdings.
    Returns 0.0 if you don’t hold any.
    """
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0
    
def buy_stock(symbol: str, qty: int, price: float, trade_time=None):
    """
    Simulate buying `qty` shares of `symbol` @ `price`.
    Deducts cash, logs the trade, and updates holdings.
    """
    # 1) Deduct cash
    cost = price * qty
    current_cash = get_cash()
    set_cash(current_cash - cost)

    # 2) Record the trade
    insert_trade(symbol, 'BUY', price, qty)

    # 3) Upsert the position
    #    avg_cost here is the price you just paid
    insert_or_update_holding(symbol, qty, price, price)


def sell_stock(symbol: str, qty: int, price: float, trade_time=None):
    """
    Simulate selling `qty` shares of `symbol` @ `price`.
    Credits cash, logs the trade (with PnL), and updates holdings.
    """
    # 1) Credit cash
    proceeds = price * qty
    current_cash = get_cash()
    set_cash(current_cash + proceeds)

    # 2) Compute P/L against your avg cost
    avg_cost = get_avg_cost(symbol)
    pnl      = (price - avg_cost) * qty

    # 3) Record the trade
    insert_trade(symbol, 'SELL', price, qty, pnl)

    # 4) Reduce your position, keeping avg_cost the same for remaining shares
    insert_or_update_holding(symbol, -qty, avg_cost, price)

def insert_trade(symbol: str, action: str, price: float, qty: int, pnl: float = None):
    """
    Record a simulated trade in the simulation_trades table.
    """
    conn = sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO simulation_trades
          (symbol, action, price, qty, trade_time, pnl)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        symbol,
        action.upper(),                     # 'BUY' or 'SELL'
        price,
        qty,
        datetime.utcnow().isoformat(),      # ISO timestamp
        pnl
    ))
    conn.commit()
    conn.close()


def _connect():
    return sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
def setup_simulation_db():
    """
    Create core simulation tables (state, holdings, positions,
    trades, alerts, wash sales) if they don’t already exist.
    """
    conn = sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    cur  = conn.cursor()

    # ── State ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id           INTEGER PRIMARY KEY CHECK (id = 1),
            cash         REAL DEFAULT 0,
            realized_pl  REAL DEFAULT 0
        )
    """)

    # ── Holdings ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            symbol     TEXT PRIMARY KEY,
            qty        INTEGER NOT NULL,
            avg_cost   REAL NOT NULL,
            last_price REAL NOT NULL
        )
    """)

    # ── Open positions ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol     TEXT,
            entry_ts   TIMESTAMP,
            entry_px   REAL,
            qty        INTEGER,
            stop_px    REAL,
            target_px  REAL
        )
    """)

    # ── Trade history ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simulation_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            action      TEXT CHECK(action IN ('BUY','SELL')) NOT NULL,
            price       REAL NOT NULL,
            qty         INTEGER NOT NULL,
            trade_time  TEXT NOT NULL,
            pnl         REAL
        )
    """)

    # ── Wash sale log ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wash_sales (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            time   TEXT,
            qty    INTEGER,
            price  REAL,
            p_l    REAL
        )
    """)

    # ── Alerts (wipe and recreate for timestamp precision) ──
    cur.execute("DROP TABLE IF EXISTS alerts")
    cur.execute("""
        CREATE TABLE alerts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT    NOT NULL,
            price      REAL    NOT NULL,
            timestamp  TEXT    NOT NULL,
            cleared    TEXT,
            name       TEXT,
            vwap       REAL,
            vwap_diff  REAL,
            triggers   TEXT,
            sparkline  BLOB
        )
    """)

    # ── Ensure singleton state row ──
    cur.execute("INSERT OR IGNORE INTO state (id, cash, realized_pl) VALUES (1, 10000, 0);")

    conn.commit()
    conn.close()


# ——— Cash accessors —————————————————————————————
def get_cash():
    conn = sqlite3.connect(SIMULATION_DB)
    cur = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1")
    return cur.fetchone()[0]


def set_cash(amount: float):
    """Overwrite cash balance (used by dashboard reset etc)."""
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (amount,))
    conn.commit()
    conn.close()
# ─── Internal connect helper ────────────────────────────────
def _connect(db: str = 'SIMULATION_DB'):
    return sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)

from datetime import datetime, timedelta

def was_recent_loss_sale(symbol, buy_date, trade_log, days=30):
    """
    Check if this symbol had a loss-sale in the past `days` before `buy_date`.
    """
    cutoff = buy_date - timedelta(days=days)
    for trade in reversed(trade_log):  # assumes newest trades are last
        if trade['symbol'] == symbol and trade['action'] == 'SELL':
            if trade['time'] >= cutoff and trade['p_l'] < 0:
                return True
    return False

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
    Returns 0 if price is zero or negative.
    """
    if price <= 0:
        # avoid division-by-zero or weird negative prices
        return 0
    return max(1, int(settings.max_per_trade / price))

import logging
logger = logging.getLogger(__name__)

def enter_trade(symbol, price, qty, timestamp, settings):
    conn = _connect()
    cur  = conn.cursor()

    # 1) record the trade
    cur.execute(
        "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time) VALUES (?,?,?,?,?)",
        (symbol, 'BUY', price, qty, timestamp)
    )

    # 2) deduct cash
    cur.execute("SELECT cash FROM state WHERE id = 1")
    cash = cur.fetchone()[0]
    cost = price * qty
    new_cash = cash - cost
    cur.execute("UPDATE state SET cash = ? WHERE id = 1", (new_cash,))

    # 3) update holdings
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    if row:
        old_qty, old_avg = row
        total_cost = old_avg * old_qty + cost
        new_qty = old_qty + qty
        new_avg  = total_cost / new_qty
        cur.execute("""
            UPDATE holdings
               SET qty = ?, avg_cost = ?, last_price = ?
             WHERE symbol = ?
        """, (new_qty, new_avg, price, symbol))
    else:
        cur.execute("""
            INSERT INTO holdings(symbol, qty, avg_cost, last_price)
            VALUES (?, ?, ?, ?)
        """, (symbol, qty, price, price))

    conn.commit()
    conn.close()

    logger.info(f"ENTER  {symbol}  qty={qty} @ {price:.2f}, cash left=${new_cash:.2f}")

def log_trade_for_wash_sale(symbol, trade_time, qty, price, p_l):
    conn = sqlite3.connect(SIMULATION_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    c    = conn.cursor()
    c.execute(
        "INSERT INTO wash_sales (symbol, time, qty, price, p_l) VALUES (?, ?, ?, ?, ?)",
        (symbol, trade_time.isoformat(), qty, price, p_l)
    )
    conn.commit()
    conn.close()



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
