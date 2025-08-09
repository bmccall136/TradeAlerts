from datetime import datetime, timedelta, timezone

# Cross-version safe Eastern Time zone (ET)
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    try:
        import pytz
        ET = pytz.timezone("US/Eastern")
    except ImportError:
        ET = timezone.utc  # fallback, UTC

import pandas_market_calendars as mcal
import pandas as pd
import sqlite3
import logging
from pathlib import Path
from services.data_fetch import fetch_data_with_timeout, fetch_intraday_vwap
from services.etrade_service import fetch_etrade_quote
from settings import SIMULATION_DB

logger = logging.getLogger("sim")

# Database path (project root)
DB_PATH = Path(__file__).resolve().parent.parent / "simulation.db"

# Market calendar (NYSE)
nyse = mcal.get_calendar("NYSE")


def _has_headlines(src):
    if hasattr(src, "empty"):
        return not src.empty
    try:
        return len(src) > 0
    except Exception:
        return False

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


# --- Keep the old DB snapshot function (rename it) -----------------
def get_stored_cash() -> float:
    _ensure_state()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

# in services/trading_helpers.py
import sqlite3

# services/trading_helpers.py

def get_cash_ledger() -> float:
    """
    Cash = starting_cash - sum(BUY qty*price) + sum(SELL qty*price).
    Purely derived from trades + settings; never falls back to the stored snapshot.
    """
    from services.simulation_service import load_simulation_settings

    starting_cash = float(load_simulation_settings().starting_cash)

    trades = get_trades(limit=10_000)  # big enough ceiling
    buy_total = sell_total = 0.0
    for t in trades:
        if isinstance(t, dict):
            side  = t.get("action")
            qty   = float(t.get("qty")   or 0)
            price = float(t.get("price") or 0)
        else:
            # (trade_time, symbol, action, qty, price, pnl, ...)
            _, _, side, qty, price, *_ = t
            qty   = float(qty   or 0)
            price = float(price or 0)

        if side == "BUY":
            buy_total  += qty * price
        elif side == "SELL":
            sell_total += qty * price

    return round(starting_cash - buy_total + sell_total, 2)

# --- New: compute cash from the trade ledger -----------------------
# --- Make get_cash() use the ledger by default ---------------------
def get_cash() -> float:
    return get_cash_ledger()

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

def get_trades(limit: int = 100):
    """
    Fetches trades as a list of dicts for easier use.
    """
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
    columns = ["trade_time", "symbol", "action", "qty", "price", "pnl"]
    # Return list of dicts:
    return [dict(zip(columns, row)) for row in rows]

# ─── Holdings management ─────────────────────────────────
def insert_or_update_holding(symbol: str, qty: int, avg_cost: float, last_price: float):
    """
    Upsert into holdings: adjust qty and recompute avg_cost for buys. Delete if qty is zero or less.
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
        if qty > 0:
            cur.execute(
                "INSERT INTO holdings(symbol, qty, avg_cost, last_price) VALUES (?,?,?,?);",
                (symbol, qty, avg_cost, last_price)
            )
        # If qty <= 0 and not in DB, do nothing.
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


def sell_stock(symbol: str, qty: int = None, price: float = None, trade_time: str = None):
    """
    Sells 'qty' shares of 'symbol' at 'price'. If qty or price not provided, sells all at last price.
    """
    holding = get_position(symbol)  # Should return a dict like {'qty': ..., 'last_price': ...}
    if not holding or holding.get("qty", 0) <= 0:
        raise RuntimeError(f"No holdings to sell for {symbol}!")

    if qty is None or qty <= 0:
        qty = holding["qty"]
    if price is None:
        price = holding.get("last_price") or get_etrade_price(symbol) or 0.0

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


def get_position(symbol):
    """
    Return holding info for 'symbol' from SIM DB as {'qty': ..., 'last_price': ...}
    """
    import sqlite3
    conn = sqlite3.connect(SIMULATION_DB)
    cur = conn.cursor()
    cur.execute("SELECT qty, last_price FROM holdings WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"qty": row[0], "last_price": row[1]}
    return None


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
    logger.info(">>> Entered check_exit_orders() <<<")
    for symbol, qty, avg_cost, _ in get_holdings():
        try:
            current = fetch_etrade_quote(symbol)
        except Exception:
            logger.warning(f"[CHECK-EXITS] Could not fetch quote for {symbol}")
            continue
        pnl_pct = ((current - avg_cost) / avg_cost * 100) if avg_cost else 0.0

        # STOP LOSS logic
        if settings.stop_loss_pct and pnl_pct <= -settings.stop_loss_pct:
            logger.info(f"[SIM-SELL] {symbol} STOP LOSS: qty={qty}, px=${current:.2f}, P/L={pnl_pct:.2f}%")
            broker_sell(symbol, qty, current)
            continue

        # TAKE PROFIT logic
        if settings.take_profit_pct and pnl_pct >= settings.take_profit_pct:
            logger.info(f"[SIM-SELL] {symbol} TAKE PROFIT: qty={qty}, px=${current:.2f}, P/L={pnl_pct:.2f}%")
            broker_sell(symbol, qty, current)
            continue

        # SELL AFTER DAYS logic
        if settings.sell_after_days:
            logger.info(f"[SELL-AFTER-DAYS] settings.sell_after_days={settings.sell_after_days} (type: {type(settings.sell_after_days)})")
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT trade_time FROM simulation_trades WHERE symbol=? AND action='BUY' ORDER BY trade_time ASC LIMIT 1;",
                (symbol,)
            )
            row = cur.fetchone()
            logger.debug(f"[SELL-DAYS] {symbol}: row={row}")
            conn.close()
            if row:
                entry = datetime.fromisoformat(row[0])
                now = datetime.utcnow()
                logger.debug(f"[SELL-DAYS] {symbol}: entry={entry}, now={now}, delta={(now-entry).total_seconds()/3600:.2f}h")
                if now - entry >= timedelta(days=settings.sell_after_days):
                    logger.info(f"[SIM-SELL] {symbol} MAX HOLD DAYS: qty={qty}, px=${current:.2f}, held={settings.sell_after_days}d")
                    broker_sell(symbol, qty, current)
            else:
                logger.info(f"[SELL-DAYS] {symbol}: No buy entry found")
        else:
            logger.info(f"NOT checking sell-after-days for: {symbol} (setting false or skipped)")
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
    holdings = get_holdings()
    cash = round(get_cash(), 2)

# Safely sum total_gain (for dicts) or dollar gain (for tuples)
def extract_total_gain(h):
    if isinstance(h, dict):
        return h.get("total_gain") or 0
    if isinstance(h, (tuple, list)) and len(h) >= 4:
        qty = h[1]
        price_paid = h[2]
        last_price = h[3]
        return (last_price - price_paid) * qty
    return 0

def extract_cost_basis(h):
    if isinstance(h, dict):
        return (h.get("qty") or 0) * (h.get("price_paid") or 0)
    if isinstance(h, (tuple, list)) and len(h) >= 3:
        return h[1] * h[2]
    return 0

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
