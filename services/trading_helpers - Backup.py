import logging
import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal
from settings import SIMULATION_DB, BACKTEST_DB

# -- Paths & DB setup ----------------------------------------------------------------
ET = ZoneInfo("America/New_York")
DB_PATH = Path(__file__).parent / "simulation.db"

logger = logging.getLogger(__name__)


def _connect(path: Path = DB_PATH):
    return sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)


def setup_simulation_db():
    """
    Create (if necessary) and seed the simulation database with:
      - state (cash, realized_pl)
      - holdings
      - simulation_trades
    """
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            cash REAL NOT NULL,
            realized_pl REAL NOT NULL DEFAULT 0.0
        );
    """)
    cur.execute(
        "INSERT OR IGNORE INTO state(id, cash, realized_pl) VALUES (1, 0.0, 0.0);"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            symbol TEXT PRIMARY KEY,
            qty INTEGER NOT NULL,
            avg_cost REAL NOT NULL,
            last_price REAL NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS simulation_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('BUY','SELL')),
            price REAL NOT NULL,
            qty INTEGER NOT NULL,
            trade_time TEXT NOT NULL,
            pnl REAL
        );
    """)
    conn.commit()
    conn.close()


# -- Market calendar / timing ---------------------------------------------------------
nyse = mcal.get_calendar("NYSE")

def market_is_open() -> bool:
    now = datetime.now(ET)
    today = now.date()
    sched = nyse.schedule(start_date=today, end_date=today)
    if sched.empty:
        return False
    row = sched.iloc[0]
    open_dt = row.market_open.tz_convert(ET)
    close_dt = row.market_close.tz_convert(ET)
    return open_dt <= now < close_dt


def seconds_until_open() -> float:
    now = datetime.now(ET)
    today = now.date()
    sched = nyse.schedule(start_date=today, end_date=today + timedelta(days=7))
    for _, row in sched.iterrows():
        open_dt = row.market_open.tz_convert(ET)
        if open_dt > now:
            return (open_dt - now).total_seconds()
    return 24 * 3600


# -- Cash management ------------------------------------------------------------------

def set_cash(amount: float):
    setup_simulation_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (amount,))
    conn.commit()
    conn.close()


def get_cash() -> float:
    setup_simulation_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    (cash,) = cur.fetchone()
    conn.close()
    return cash


# -- Holdings & positions -------------------------------------------------------------

def insert_or_update_holding(symbol: str, qty: int, avg_cost: float, last_price: float):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    if row:
        old_qty, old_avg = row
        new_qty = old_qty + qty
        if new_qty > 0:
            total_cost = old_avg * old_qty + avg_cost * qty
            new_avg = total_cost / new_qty
            cur.execute(
                "UPDATE holdings SET qty=?, avg_cost=?, last_price=? WHERE symbol=?",
                (new_qty, new_avg, last_price, symbol)
            )
        else:
            cur.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))
    else:
        cur.execute(
            "INSERT INTO holdings(symbol, qty, avg_cost, last_price) VALUES (?, ?, ?, ?)",
            (symbol, qty, avg_cost, last_price)
        )
    conn.commit()
    conn.close()


def get_holdings() -> list[tuple[str,int,float,float]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings;")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_position_qty(symbol: str) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT qty FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def check_if_position_open(symbol: str) -> bool:
    return get_position_qty(symbol) > 0


# -- Trade logging --------------------------------------------------------------------

def insert_trade(symbol: str, action: str, price: float, qty: int, pnl: float = None, trade_time: datetime = None):
    setup_simulation_db()
    ts = (trade_time or datetime.utcnow()).isoformat()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO simulation_trades(symbol, action, price, qty, trade_time, pnl) VALUES (?,?,?,?,?,?)",
        (symbol, action.upper(), price, qty, ts, pnl)
    )
    conn.commit()
    conn.close()


def get_trades(limit: int = 100) -> list[tuple[str,...]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT trade_time, symbol, action, qty, price, pnl FROM simulation_trades ORDER BY trade_time DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_positions() -> dict[str,int]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, SUM(CASE WHEN action='BUY' THEN qty ELSE -qty END) FROM simulation_trades GROUP BY symbol"
    )
    positions = {sym: net for sym, net in cur.fetchall()}
    conn.close()
    return positions


def get_avg_cost(symbol: str) -> float:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


# -- P/L -------------------------------------------------------------------------------

def get_realized_pl() -> float:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT realized_pl FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_unrealized_pl() -> float:
    total = 0.0
    for qty, avg_cost, last_price in [(h[1], h[2], h[3]) for h in get_holdings()]:
        total += (last_price - avg_cost) * qty
    return total


# -- Sizing ---------------------------------------------------------------------------

def compute_qty(settings, price: float) -> int:
    if price <= 0:
        return 0
    max_by_size = int(settings.max_per_trade / price)
    max_by_cash = int(get_cash() / price)
    return min(max_by_size, max_by_cash)


# -- Execution helpers ----------------------------------------------------------------

def buy_stock(symbol: str, qty: int, price: float, trade_time: datetime = None):
    cost = price * qty
    current_cash = get_cash()
    if cost > current_cash:
        raise RuntimeError(f"Not enough cash: need {cost:.2f}, have {current_cash:.2f}")
    set_cash(current_cash - cost)
    insert_trade(symbol, 'BUY', price, qty, pnl=None, trade_time=trade_time)
    insert_or_update_holding(symbol, qty, price, price)
    logger.info(f"✅ BUY {symbol} x{qty} @ {price:.2f} (cash → {get_cash():.2f})")


def sell_stock(symbol: str, qty: int, price: float, trade_time: datetime = None) -> None:
    proceeds = qty * price
    set_cash(get_cash() + proceeds)
    avg_cost = get_avg_cost(symbol)
    pnl = (price - avg_cost) * qty
    insert_trade(symbol, 'SELL', price, qty, pnl=pnl, trade_time=trade_time)
    insert_or_update_holding(symbol, -qty, avg_cost, price)
    logger.info(f"💲 SELL {symbol} x{qty} @ {price:.2f} (P/L → {pnl:.2f})")


def check_exit_orders(settings) -> None:
    from services.broker_api import sell_stock as live_sell
    for symbol, qty, avg_cost, _lp in get_holdings():
        current = None
        try:
            current = fetch_etrade_quote(symbol)
        except Exception:
            continue
        pnl_pct = ((current - avg_cost) / avg_cost * 100) if avg_cost else 0.0
        if settings.stop_loss_pct and pnl_pct <= -settings.stop_loss_pct:
            live_sell(symbol, qty, current)
            continue
        if settings.take_profit_pct and pnl_pct >= settings.take_profit_pct:
            live_sell(symbol, qty, current)
            continue
        if settings.sell_after_days:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT trade_time FROM simulation_trades WHERE symbol=? AND action='BUY' ORDER BY trade_time ASC LIMIT 1;",
                (symbol,)
            )
            first_ts = cur.fetchone()[0]
            conn.close()
            entry_dt = datetime.fromisoformat(first_ts)
            if datetime.utcnow() - entry_dt >= timedelta(days=settings.sell_after_days):
                live_sell(symbol, qty, current)
