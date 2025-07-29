import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# Database path (project root)
DB_PATH = Path(__file__).resolve().parent.parent / "simulation.db"

# Timezone and market calendar
ET = ZoneInfo("America/New_York")
nyse = mcal.get_calendar("NYSE")

# ─── Internal connect ─────────────────────────────────────
def _connect():
    """
    Return a sqlite3 connection to the simulation database.
    """
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)

# Print DB path on import for verification
print(f"▶︎ TradingHelpers loaded; simulation DB path is {DB_PATH.resolve()}")

# ─── Initialization ────────────────────────────────────────
def setup_simulation_db():
    """
    Create and seed the simulation database with:
      - state: singleton row for cash & realized P/L
      - holdings: current positions
      - simulation_trades: audit trail
    Seeds starting cash from simulation_config.json on first DB creation.
    """
    from pathlib import Path
    import json

    # detect initial run by absence of file
    first_run = not DB_PATH.exists()

    conn = _connect()
    cur = conn.cursor()

    # state table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id           INTEGER PRIMARY KEY CHECK(id = 1),
            cash         REAL    NOT NULL,
            realized_pl  REAL    NOT NULL DEFAULT 0.0
        );
    """)
    # holdings table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            symbol     TEXT    PRIMARY KEY,
            qty        INTEGER NOT NULL,
            avg_cost   REAL    NOT NULL,
            last_price REAL    NOT NULL
        );
    """)
    # simulation_trades table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simulation_trades (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT    NOT NULL,
            action     TEXT    NOT NULL CHECK(action IN ('BUY','SELL')),
            price      REAL    NOT NULL,
            qty        INTEGER NOT NULL,
            trade_time TEXT    NOT NULL,
            pnl        REAL
        );
    """)

    # seed starting cash from JSON on first creation
    if first_run:
        cfg_path = Path(__file__).resolve().parent.parent / "simulation_config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            starting = cfg.get("starting_cash", 0.0)
            cur.execute(
                "INSERT OR IGNORE INTO state(id, cash, realized_pl) VALUES (1, ?, 0.0);",
                (starting,)
            )
            print(f"▶︎ Seeded new simulation.db with starting cash = ${starting:.2f}")

    conn.commit()
    conn.close()

# ─── Cash accessors ────────────────────────────────────────
def _ensure_state():
    """
    Ensure the state table has its singleton row.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO state (id, cash, realized_pl) VALUES (1, 0.0, 0.0);")
    conn.commit()
    conn.close()


def set_cash(amount: float):
    _ensure_state()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (amount,))
    conn.commit()
    conn.close()


def get_cash() -> float:
    _ensure_state()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

# ─── Trade recording ──────────────────────────────────────
def insert_trade(symbol: str, action: str, price: float, qty: int,
                 pnl: float = None, trade_time: str = None):
    """
    Record a BUY or SELL event into simulation_trades.
    """
    ts = trade_time or datetime.now(timezone.utc).isoformat()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time, pnl) VALUES (?,?,?,?,?,?);",
        (symbol, action.upper(), price, qty, ts, pnl)
    )
    conn.commit()
    conn.close()

# ─── Holdings management ─────────────────────────────────
def insert_or_update_holding(symbol: str, qty: int, avg_cost: float, last_price: float):
    """
    Upsert into holdings: adjust qty and recompute avg_cost for buys.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?;", (symbol,))
    row = cur.fetchone()
    if row:
        old_qty, old_avg = row
        new_qty = old_qty + qty
        if new_qty > 0:
            total_cost = old_avg * old_qty + avg_cost * qty
            new_avg = total_cost / new_qty
            cur.execute(
                "UPDATE holdings SET qty=?, avg_cost=?, last_price=? WHERE symbol=?;",
                (new_qty, new_avg, last_price, symbol)
            )
        else:
            cur.execute("DELETE FROM holdings WHERE symbol=?;", (symbol,))
    else:
        cur.execute(
            "INSERT INTO holdings(symbol, qty, avg_cost, last_price) VALUES (?,?,?,?);",
            (symbol, qty, avg_cost, last_price)
        )
    conn.commit()
    conn.close()

# ─── Quantity computation ─────────────────────────────────
def compute_qty(settings, price: float) -> int:
    """
    Determine shares to buy, limited by max_per_trade and available cash.
    """
    if price <= 0:
        return 0
    max_by_size = int(settings.max_per_trade / price)
    max_by_cash = int(get_cash() / price)
    return min(max_by_size, max_by_cash)

# ─── Order execution helpers ───────────────────────────────
def buy_stock(symbol: str, qty: int, price: float, trade_time: str = None):
    cost = qty * price
    cash = get_cash()
    if cost > cash:
        raise RuntimeError(f"Not enough cash: need {cost:.2f}, have {cash:.2f}")
    set_cash(cash - cost)
    insert_trade(symbol, 'BUY', price, qty, None, trade_time)
    insert_or_update_holding(symbol, qty, avg_cost=price, last_price=price)


def sell_stock(symbol: str, qty: int, price: float, trade_time: str = None):
    proceeds = qty * price
    set_cash(get_cash() + proceeds)
    avg = get_avg_cost(symbol)
    pnl = (price - avg) * qty
    insert_trade(symbol, 'SELL', price, qty, pnl, trade_time)
    insert_or_update_holding(symbol, qty=-qty, avg_cost=avg, last_price=price)

# ─── Backtest helpers ─────────────────────────────────────
def init_backtest_db():
    """
    Initialize backtest database using BACKTEST_SCHEMA.
    """
    from settings import BACKTEST_DB
    from config import BACKTEST_SCHEMA
    conn = sqlite3.connect(BACKTEST_DB)
    conn.executescript(BACKTEST_SCHEMA)
    conn.commit()
    conn.close()


def enter_trade(symbol: str, price: float, time, trigger: str,
                alert_type: str, name: str, vwap: float,
                vwap_diff: float, qty: int, buy: int):
    """
    Record a backtest trade into the trades table.
    """
    conn = sqlite3.connect(BACKTEST_DB)
    cur = conn.cursor()
    ts = time.isoformat() if hasattr(time, 'isoformat') else str(time)
    cur.execute(
        "INSERT INTO trades"
        "  (symbol, name, price, time, trigger, alert_type, vwap, vwap_diff, qty, buy)"
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        (symbol, name, price, ts, trigger, alert_type, vwap, vwap_diff, qty, buy)
    )
    conn.commit()
    conn.close()

# ─── Queries & metrics ───────────────────────────────────
def get_holdings():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings;")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_trades(limit: int = 100):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT trade_time, symbol, action, qty, price, pnl"
        " FROM simulation_trades"
        " ORDER BY trade_time DESC LIMIT ?;",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_positions():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, SUM(CASE WHEN action='BUY' THEN qty ELSE -qty END)"
        " FROM simulation_trades GROUP BY symbol;"
    )
    data = {sym: net for sym, net in cur.fetchall()}
    conn.close()
    return data


def get_avg_cost(symbol: str) -> float:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT avg_cost FROM holdings WHERE symbol=?;", (symbol,))
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_position_qty(symbol: str) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT qty FROM holdings WHERE symbol=?;", (symbol,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_unrealized_pl() -> float:
    """Sum of (current_price – avg_cost)×qty for all open positions."""
    total = 0.0
    for symbol, qty, avg_cost, last_price in get_holdings():
        total += (last_price - avg_cost) * qty
    return total

def get_realized_pl() -> float:
    """Sum of all closed‐trade P/L stored in state.realized_pl."""
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT realized_pl FROM state WHERE id=1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

# ─── Exit logic ──────────────────────────────────────────
def check_exit_orders(settings) -> None:
    from services.broker_api import sell_stock as broker_sell
    for symbol, qty, avg_cost, _ in get_holdings():
        try:
            current = fetch_etrade_quote(symbol)
        except Exception:
            continue
        pnl_pct = ((current - avg_cost) / avg_cost * 100) if avg_cost else 0.0
        if settings.stop_loss_pct and pnl_pct <= -settings.stop_loss_pct:
            broker_sell(symbol, qty, current)
            continue
        if settings.take_profit_pct and pnl_pct >= settings.take_profit_pct:
            broker_sell(symbol, qty, current)
            continue
        if settings.sell_after_days:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT trade_time FROM simulation_trades WHERE symbol=? AND action='BUY' ORDER BY trade_time ASC LIMIT 1;",
                (symbol,)
            )
            first_time = cur.fetchone()[0]
            conn.close()
            entry = datetime.fromisoformat(first_time)
            if datetime.utcnow() - entry >= timedelta(days=settings.sell_after_days):
                broker_sell(symbol, qty, current)

from datetime import timedelta

POST_OPEN_BUFFER = timedelta(minutes=0)

def market_is_open() -> bool:
    now = datetime.now(ET)
    sched = nyse.schedule(start_date=now.date(), end_date=now.date())
    if sched.empty:
        return False

    row = sched.iloc[0]
    # shift the official open by your buffer
    open_dt     = row['market_open'].tz_convert(ET) + POST_OPEN_BUFFER
    close_dt    = row['market_close'].tz_convert(ET)
    return open_dt <= now < close_dt


def seconds_until_open() -> float:
    now   = datetime.now(ET)
    sched = nyse.schedule(
        start_date=now.date(),
        end_date=now.date() + timedelta(days=7),
    )
    for _, row in sched.iterrows():
        # buffer your next-open by 30m as well
        open_dt = row['market_open'].tz_convert(ET) + POST_OPEN_BUFFER
        if open_dt > now:
            return (open_dt - now).total_seconds()
    # if we fall out of the loop, next open is >7 days away—just wait a day
    return 24 * 3600

    # ─── Position check ──────────────────────────────────────
    setup_simulation_db()
    raw = get_holdings()
    cash           = round(get_cash(), 2)
    # use the live total_gain we just calculated, not the DB
    unrealized_pnl = round(sum(h["total_gain"] for h in holdings), 2)
def check_if_position_open(symbol: str) -> bool:
    return get_position_qty(symbol) > 0
def refresh_holdings_prices():
    """Fetch live prices for each symbol in holdings and write them to the DB."""
    from services.etrade_service import fetch_etrade_quote
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT symbol FROM holdings;")
    for (symbol,) in cur.fetchall():
        try:
            px = fetch_etrade_quote(symbol)
            if px > 0:
                cur.execute(
                   "UPDATE holdings SET last_price = ? WHERE symbol = ?;",
                   (px, symbol)
                )
        except Exception:
            pass
    conn.commit()
    conn.close()
