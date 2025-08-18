
# services/trading_helpers.py  — cleaned & consolidated
from __future__ import annotations

import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict, Any, List

import pandas_market_calendars as mcal

logger = logging.getLogger("sim")

# ─── Timezones ──────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    try:
        import pytz
        ET = pytz.timezone("America/New_York")
    except Exception:
        ET = timezone.utc

# ─── DB paths ──────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "simulation.db"
print(f"▶︎ TradingHelpers loaded; simulation DB path is {DB_PATH.resolve()}")

# Some modules expect a SIMULATION_DB from settings. We keep compatibility.
try:
    from settings import SIMULATION_DB as _SIM_DB_FROM_SETTINGS
except Exception:
    _SIM_DB_FROM_SETTINGS = None

# ─── Trailing stop persistence (canonical) ─────────────────────────────
from datetime import timezone

def _utcnow_iso() -> str:
    # UTC ISO8601 with Z, consistent everywhere
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def _ensure_trail_table() -> None:
    """
    Ensure trail_state exists with columns:
      symbol TEXT PK, peak REAL NOT NULL, since TEXT NOT NULL DEFAULT now
    If an older table is missing 'since', add and backfill.
    """
    conn = _connect()
    # Create (idempotent) with DEFAULT on since
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trail_state (
            symbol TEXT PRIMARY KEY,
            peak   REAL NOT NULL,
            since  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
    """)
    # Migrate older schema that lacked 'since'
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trail_state);").fetchall()]
    if "since" not in cols:
        conn.execute("""
            ALTER TABLE trail_state
            ADD COLUMN since TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'));
        """)
        # Backfill any rows that may still be NULL (paranoia)
        conn.execute("UPDATE trail_state SET since = COALESCE(since, strftime('%Y-%m-%dT%H:%M:%SZ','now'));")
    conn.commit()
    conn.close()

def _trail_get(symbol: str):
    """Return (peak, since) for trailing stop, or (None, None) if absent."""
    _ensure_trail_table()
    conn = _connect()
    row = conn.execute(
        "SELECT peak, since FROM trail_state WHERE symbol=?;",
        (symbol,)
    ).fetchone()
    conn.close()
    return (float(row[0]), row[1]) if row else (None, None)

def _trail_set(symbol: str, new_peak: float) -> None:
    """
    Upsert the peak; if the peak increases, refresh 'since' to now.
    Safe if row doesn't exist yet.
    """
    _ensure_trail_table()
    now = _utcnow_iso()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO trail_state(symbol, peak, since)
        VALUES(?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            peak  = CASE WHEN excluded.peak > trail_state.peak
                         THEN excluded.peak ELSE trail_state.peak END,
            since = CASE WHEN excluded.peak > trail_state.peak
                         THEN excluded.since ELSE trail_state.since END;
        """,
        (symbol, float(new_peak), now)
    )
    conn.commit()
    conn.close()

def _trail_clear(symbol: str) -> None:
    """Remove trail row after position is closed."""
    _ensure_trail_table()
    conn = _connect()
    conn.execute("DELETE FROM trail_state WHERE symbol=?;", (symbol,))
    conn.commit()
    conn.close()

# ─── Backtest DB initializer (restored) ────────────────────────────────────────
def init_backtest_db():
    """
    Initialize the backtest database.

    If config schema is available (config.BACKTEST_SCHEMA), use it.
    Otherwise, create a minimal schema with `backtest_runs` and `backtest_trades`.
    """
    try:
        # Preferred: take the path from your settings module
        from settings import BACKTEST_DB as _BACKTEST_DB
        BACKTEST_DB = _BACKTEST_DB
    except Exception:
        # Fallback to a file next to simulation.db in project root
        BACKTEST_DB = str(Path(__file__).resolve().parent.parent / "backtest.db")

    # Try to import a full schema if you have one
    schema = None
    try:
        from config import BACKTEST_SCHEMA as _SCHEMA
        schema = _SCHEMA
    except Exception:
        # Minimal schema fallback
        schema = """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS backtest_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT NOT NULL,
            settings_json TEXT
        );

        CREATE TABLE IF NOT EXISTS backtest_trades (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id   INTEGER NOT NULL,
            symbol   TEXT NOT NULL,
            date     TEXT NOT NULL,
            action   TEXT NOT NULL,
            price    REAL NOT NULL,
            qty      INTEGER NOT NULL,
            pnl      REAL,
            FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
        );
        """

    conn = sqlite3.connect(BACKTEST_DB)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
# --- Backtest logging shim (back-compat): enter_trade ----------------
from pathlib import Path
import sqlite3

try:
    # Prefer centralized path if you have it
    from settings import BACKTEST_DB  # e.g., "C:/TradeAlerts/backtest.db"
except Exception:
    # Fallback to project root/backtest.db
    BACKTEST_DB = str((Path(__file__).resolve().parent.parent / "backtest.db"))
from datetime import datetime, timezone

# put near your other imports at the top of this file
from datetime import datetime, timezone

def _migrate_trail_table() -> None:
    """Ensure trail_state exists and has (symbol PK, peak, since with DEFAULT)."""
    conn = _connect()
    # Create with DEFAULT on since so inserts without 'since' don't fail
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trail_state (
            symbol TEXT PRIMARY KEY,
            peak   REAL NOT NULL,
            since  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
    """)
    # If table existed without 'since', add it
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trail_state);").fetchall()]
    if "since" not in cols:
        conn.execute("""
            ALTER TABLE trail_state
            ADD COLUMN since TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'));
        """)
    # Backfill any legacy NULLs (from pre-constraint rows)
    conn.execute("UPDATE trail_state SET since = ? WHERE since IS NULL;", (_utcnow_iso(),))
    conn.commit()
    conn.close()

def enter_trade(
    symbol: str,
    price: float,
    time,
    trigger: str = "",
    alert_type: str = "",
    name: str = "",
    vwap: float = 0.0,
    vwap_diff: float = 0.0,
    qty: int = 0,
    buy: int = 1,
) -> None:
    """
    Back-compat helper used by dashboard/backtest code.
    Writes a single row into backtest 'trades' table.
    Safe even if the table doesn't exist yet — it will be created.
    """
    ts = time.isoformat() if hasattr(time, "isoformat") else str(time)

    conn = sqlite3.connect(BACKTEST_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT    NOT NULL,
            name       TEXT,
            price      REAL    NOT NULL,
            time       TEXT    NOT NULL,
            trigger    TEXT,
            alert_type TEXT,
            vwap       REAL,
            vwap_diff  REAL,
            qty        INTEGER,
            buy        INTEGER
        );
    """)
    cur.execute("""
        INSERT INTO trades
          (symbol, name, price, time, trigger, alert_type, vwap, vwap_diff, qty, buy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        symbol,
        name,
        float(price or 0.0),
        ts,
        trigger,
        alert_type,
        float(vwap or 0.0),
        float(vwap_diff or 0.0),
        int(qty or 0),
        int(buy or 0),
    ))
    conn.commit()
    conn.close()

# --- Position helpers (back-compat) ---------------------------------
def check_if_position_open(symbol: str) -> bool:
    """
    Returns True if we currently hold >0 shares of `symbol`.
    Keeps the old API that dashboard.py imports.
    """
    try:
        return int(get_position_qty(symbol) or 0) > 0
    except Exception:
        # ultra-safe fallback if get_position_qty isn't available for any reason
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT qty FROM holdings WHERE symbol=?;", (symbol,))
        row = cur.fetchone()
        conn.close()
        return bool(row and (row[0] or 0) > 0)

# Back-compat: expose fetch_intraday_vwap via trading_helpers
def fetch_intraday_vwap(symbol: str, date=None, tz=None, retries: int = 2, timeout: int = 10):
    try:
        from services.data_fetch import fetch_intraday_vwap as _fiw
    except Exception as e:
        raise ImportError(f"services.data_fetch.fetch_intraday_vwap not available: {e}")
    return _fiw(symbol, date=date, tz=tz, retries=retries, timeout=timeout)

def _resolve_sim_db() -> Path:
    if _SIM_DB_FROM_SETTINGS and Path(_SIM_DB_FROM_SETTINGS).exists():
        return Path(_SIM_DB_FROM_SETTINGS)
    return DB_PATH

# ─── Market calendar ───────────────────────────────────────────────────────
nyse = mcal.get_calendar("NYSE")

# ─── SQLite helpers ────────────────────────────────────────────────────────
def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_resolve_sim_db(), detect_types=sqlite3.PARSE_DECLTYPES)

# ─── Init schema ───────────────────────────────────────────────────────────
def setup_simulation_db() -> None:
    """Create core tables if missing and seed starting cash on first run."""
    from pathlib import Path
    import json

    db_file = _resolve_sim_db()
    first_run = not db_file.exists()

    conn = _connect()
    cur = conn.cursor()

    cur.execute(
        """CREATE TABLE IF NOT EXISTS state (
                id           INTEGER PRIMARY KEY CHECK(id = 1),
                cash         REAL    NOT NULL,
                realized_pl  REAL    NOT NULL DEFAULT 0.0
            );"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS holdings (
                symbol     TEXT    PRIMARY KEY,
                qty        INTEGER NOT NULL,
                avg_cost   REAL    NOT NULL,
                last_price REAL    NOT NULL
            );"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS simulation_trades (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol     TEXT    NOT NULL,
                action     TEXT    NOT NULL CHECK(action IN ('BUY','SELL')),
                price      REAL    NOT NULL,
                qty        INTEGER NOT NULL,
                trade_time TEXT    NOT NULL,
                pnl        REAL
            );"""
    )

    cur.execute(
        """CREATE TABLE IF NOT EXISTS trail_state (
                symbol TEXT PRIMARY KEY,
                peak   REAL NOT NULL,
                since  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );"""
    )

    if first_run:
        # Seed starting cash from simulation_config.json (if present)
        cfg_path = Path(__file__).resolve().parent.parent / "simulation_config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text())
                starting = float(cfg.get("starting_cash", 0.0) or 0.0)
            except Exception:
                starting = 0.0
            cur.execute(
                "INSERT OR IGNORE INTO state(id, cash, realized_pl) VALUES (1, ?, 0.0);",
                (starting,),
            )
            print(f"▶︎ Seeded simulation.db with starting cash = ${starting:.2f}")
        else:
            cur.execute("INSERT OR IGNORE INTO state(id, cash, realized_pl) VALUES (1, 0.0, 0.0);")

    conn.commit()
    conn.close()

# near your other helpers
# near your quote helpers in dashboard.py
SYMBOL_ALIASES = {
    "PARA": "PSKY",       # Paramount Global -> Paramount Skydance (Class B)
    "PARAA": "PSKY",
}

def _alias(sym: str) -> str:
    return SYMBOL_ALIASES.get(sym, sym)

def _is_bad_quote(x):
    try:
        return x is None or float(x) <= 0
    except Exception:
        return True

def get_last_and_prev(symbol: str, fallback_price: float):
    qsym = _alias(symbol)

    last = prev = None
    q = fetch_etrade_quote(qsym)

    if isinstance(q, dict):
        # same keys as you already had…
        for k in ("lastTrade","lastPrice","intradayLast","close","closePrice"):
            v = q.get(k)
            if not _is_bad_quote(v):
                last = float(v); break
        for k in ("previousClose","prevClose","priorClose","closePrevDay","closePricePrev"):
            v = q.get(k)
            if not _is_bad_quote(v):
                prev = float(v); break
    else:
        try:
            last = float(q)
            if _is_bad_quote(last):
                last = None
        except Exception:
            last = None

    # Fallback history also uses aliased ticker
    if prev is None or last is None:
        try:
            df = fetch_data_with_timeout(qsym, "2d")
            if df is not None:
                close_col = next((c for c in df.columns if str(c).lower() == "close"), None)
                if close_col is not None:
                    if last is None and len(df) >= 1:
                        last = float(df[close_col].iloc[-1])
                    if prev is None and len(df) >= 2:
                        prev = float(df[close_col].iloc[-2])
        except Exception:
            pass

    if _is_bad_quote(last):
        last = float(fallback_price or 0.0)

    return float(last), (None if prev is None else float(prev))

# Make sure trail_state has the 'since' column even on old installs
try:
    _ensure_trail_table()
except Exception:
    pass
 
# ─── State accessors ───────────────────────────────────────────────────────
def _ensure_state() -> None:
    conn = _connect()
    conn.execute("INSERT OR IGNORE INTO state (id, cash, realized_pl) VALUES (1, 0.0, 0.0);")
    conn.commit()
    conn.close()

def set_cash(amount: float) -> None:
    _ensure_state()
    conn = _connect()
    conn.execute("UPDATE state SET cash=? WHERE id=1;", (float(amount),))
    conn.commit()
    conn.close()

def get_stored_cash() -> float:
    _ensure_state()
    conn = _connect()
    row = conn.execute("SELECT cash FROM state WHERE id=1;").fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

# ─── Trades I/O ────────────────────────────────────────────────────────────
def insert_trade(symbol: str, action: str, price: float, qty: int,
                 pnl: float | None = None, trade_time: str | None = None) -> None:
    ts = trade_time or datetime.now(timezone.utc).isoformat()
    conn = _connect()
    conn.execute(
        "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time, pnl) VALUES (?,?,?,?,?,?);",
        (symbol, action.upper(), float(price), int(qty), ts, pnl),
    )
    conn.commit()
    conn.close()

def get_trades(limit: int = 100) -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT trade_time, symbol, action, qty, price, pnl "
        "FROM simulation_trades ORDER BY trade_time DESC LIMIT ?;",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    cols = ["trade_time", "symbol", "action", "qty", "price", "pnl"]
    return [dict(zip(cols, r)) for r in rows]

# ─── Holdings I/O ─────────────────────────────────────────────────────────
def insert_or_update_holding(symbol: str, qty: int, avg_cost: float, last_price: float) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol=?;", (symbol,))
    row = cur.fetchone()
    if row:
        old_qty, old_avg = row
        new_qty = int(old_qty) + int(qty)
        if new_qty > 0:
            total_cost = float(old_avg) * int(old_qty) + float(avg_cost) * int(qty)
            new_avg = total_cost / new_qty
            cur.execute(
                "UPDATE holdings SET qty=?, avg_cost=?, last_price=? WHERE symbol=?;",
                (new_qty, new_avg, float(last_price), symbol),
            )
        else:
            cur.execute("DELETE FROM holdings WHERE symbol=?;", (symbol,))
    else:
        if qty > 0:
            cur.execute(
                "INSERT INTO holdings(symbol, qty, avg_cost, last_price) VALUES (?,?,?,?);",
                (symbol, int(qty), float(avg_cost), float(last_price)),
            )
    conn.commit()
    conn.close()

def get_holdings() -> List[tuple]:
    conn = _connect()
    rows = conn.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings;").fetchall()
    conn.close()
    return rows

def get_position(symbol: str) -> Optional[Dict[str, Any]]:
    """Compatibility: try settings.SIMULATION_DB first, then our DB_PATH."""
    path = Path(_SIM_DB_FROM_SETTINGS) if _SIM_DB_FROM_SETTINGS else _resolve_sim_db()
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT qty, last_price FROM holdings WHERE symbol=?;", (symbol,)).fetchone()
    conn.close()
    if row:
        return {"qty": int(row[0]), "last_price": float(row[1])}
    return None

def get_position_qty(symbol: str) -> int:
    conn = _connect()
    row = conn.execute("SELECT qty FROM holdings WHERE symbol=?;", (symbol,)).fetchone()
    conn.close()
    return int(row[0]) if row else 0

def get_avg_cost(symbol: str) -> float:
    conn = _connect()
    row = conn.execute("SELECT avg_cost FROM holdings WHERE symbol=?;", (symbol,)).fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

# ─── Cash (ledger-first) ──────────────────────────────────────────────────
def get_cash_ledger() -> float:
    """Cash = starting_cash - Σ(BUY) + Σ(SELL)."""
    try:
        from services.simulation_service import load_simulation_settings
        starting_cash = float(getattr(load_simulation_settings(), "starting_cash", 0.0) or 0.0)
    except Exception:
        starting_cash = 0.0

    trades = get_trades(limit=100000)
    buy_total = sell_total = 0.0
    for t in trades:
        side = (t.get("action") or "").upper()
        qty  = float(t.get("qty") or 0.0)
        px   = float(t.get("price") or 0.0)
        if side == "BUY":
            buy_total  += qty * px
        elif side == "SELL":
            sell_total += qty * px
    return round(starting_cash - buy_total + sell_total, 2)

def get_cash() -> float:
    return get_cash_ledger()

# ─── Metrics ──────────────────────────────────────────────────────────────
def get_unrealized_pl() -> float:
    total = 0.0
    for symbol, qty, avg_cost, last_price in get_holdings():
        total += (float(last_price) - float(avg_cost)) * int(qty)
    return round(total, 2)

def get_realized_pl() -> float:
    conn = _connect()
    row = conn.execute("SELECT realized_pl FROM state WHERE id=1;").fetchone()
    conn.close()
    return float(row[0]) if row else 0.0

def get_realized_pl_sum() -> float:
    """Sum P/L from SELL rows in trades."""
    total = 0.0
    for t in get_trades(limit=100000):
        if (t.get("action") or "").upper() == "SELL":
            try:
                total += float(t.get("pnl") or 0.0)
            except Exception:
                pass
    return round(total, 2)

# ─── Utility time helpers ────────────────────────────────────────────────
def _as_utc(dt_like) -> datetime:
    if isinstance(dt_like, datetime):
        dt = dt_like
    else:
        try:
            dt = datetime.fromisoformat(str(dt_like))
        except Exception:
            dt = datetime.utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt

# ─── Risk management helpers ─────────────────────────────────────────────
def enforce_settlement_on_buy(symbol: str, qty: int, price: float, now=None,
                              account_type: str = "CASH") -> Tuple[bool, str]:
    """Basic T+N guard for CASH accounts: if you need unsettled proceeds to fund
    this BUY and your most recent SELL is within T+N, block.
    """
    if (account_type or "CASH").upper() != "CASH":
        return True, ""

    n = int(os.getenv("T_PLUS_N_DAYS", "2"))
    cost = float(qty) * float(price)
    if get_cash() >= cost:
        return True, ""  # You have enough "settled" cash to cover (approximation).

    now_utc = _as_utc(now or datetime.utcnow())
    conn = _connect()
    row = conn.execute(
        "SELECT trade_time FROM simulation_trades WHERE action='SELL' ORDER BY trade_time DESC LIMIT 1;"
    ).fetchone()
    conn.close()

    if not row:
        return True, ""

    last_sell = _as_utc(row[0])
    settle_at = last_sell + timedelta(days=n)
    if now_utc < settle_at:
        return False, (f"Unsettled funds (T+{n}). Last SELL {last_sell.date()} settles "
                       f"{settle_at.date()}. Need ${cost:.2f}, available cash ${get_cash():.2f}.")
    return True, ""

def enforce_wash_sale(symbol: str, qty: int, price: float, now=None) -> Optional[str]:
    """Advisory: if a SELL at a loss occurred within 30 days, this BUY may be wash-sale affected."""
    try:
        now_utc = _as_utc(now or datetime.utcnow())
        cutoff = now_utc - timedelta(days=30)
        # Find any SELL at loss in last 30d for this symbol
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT price, qty, trade_time FROM simulation_trades "
            "WHERE symbol=? AND action='SELL' ORDER BY trade_time DESC LIMIT 100;",
            (symbol,)
        )
        rows = cur.fetchall()
        conn.close()

        # We need avg cost around each SELL date; approximate with current avg
        avg = get_avg_cost(symbol)
        for px, q, ts in rows:
            ts_utc = _as_utc(ts)
            if ts_utc >= cutoff and float(px) < float(avg):
                return (f"Wash-sale advisory: recent SELL at a loss on {ts_utc.date()} "
                        f"and this BUY may disallow some loss deduction.")
    except Exception:
        pass
    return None

def enforce_pdt_on_sell(symbol: str, qty: int, now=None, account_type: str = "CASH") -> Tuple[bool, str]:
    """Simple PDT guard (margin only): block if this would be the 4th+ day-trade in 5 calendar days."""
    if (account_type or "CASH").upper() != "MARGIN":
        return True, ""

    now_utc = _as_utc(now or datetime.utcnow())
    five_days_ago = now_utc - timedelta(days=5)

    # Pull recent trades
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT trade_time, symbol, action FROM simulation_trades "
        "WHERE trade_time >= ? ORDER BY trade_time ASC;",
        (five_days_ago.isoformat(),)
    )
    rows = cur.fetchall()
    conn.close()

    # Count day-trades = buy/sell same day (any symbol)
    day_trades_by_date = {}
    intraday_map: Dict[str, Dict[str, set]] = {}

    for ts, sym, act in rows:
        ts_dt = _as_utc(ts).astimezone(ET)
        dkey = ts_dt.date().isoformat()
        intraday_map.setdefault(dkey, {"BUY": set(), "SELL": set()})
        intraday_map[dkey][(act or "").upper()].add(sym)

    for dkey, sides in intraday_map.items():
        # A crude approximation: if any symbol appears on both sides same day
        common = sides.get("BUY", set()) & sides.get("SELL", set())
        if common:
            day_trades_by_date[dkey] = day_trades_by_date.get(dkey, 0) + len(common)

    total_dt = sum(day_trades_by_date.values())
    if total_dt >= 3:
        return False, f"PDT: would exceed 3 day-trades in 5 days (have {total_dt})."
    return True, ""

# ─── Order helpers ───────────────────────────────────────────────────────
def compute_qty(settings, price: float) -> int:
    if price <= 0:
        return 0
    max_by_size = int(float(getattr(settings, "max_per_trade", 0.0)) / float(price))
    max_by_cash = int(get_cash() / float(price))
    return max(0, min(max_by_size, max_by_cash))

def buy_stock(symbol: str, qty: int, price: float, trade_time: str | None = None) -> bool:
    # Settlement guard (CASH accounts)
    acct_type = os.getenv("ACCOUNT_TYPE", "CASH")
    ok, reason = enforce_settlement_on_buy(symbol, qty, price, now=trade_time, account_type=acct_type)
    if not ok:
        raise RuntimeError(f"[SETTLEMENT] {reason}")

    # Optional wash-sale advisory (does not block)
    advisory = enforce_wash_sale(symbol, qty, price, now=trade_time)
    if advisory:
        logger.info(advisory)

    cost = float(qty) * float(price)
    cash = get_cash()
    if cost > cash:
        raise RuntimeError(f"Not enough cash: need {cost:.2f}, have {cash:.2f}")

    set_cash(cash - cost)
    insert_trade(symbol, "BUY", float(price), int(qty), None, trade_time)
    insert_or_update_holding(symbol, int(qty), avg_cost=float(price), last_price=float(price))
    return True

def _get_live_price(symbol: str) -> float:
    try:
        from services.etrade_service import fetch_etrade_quote
        px = fetch_etrade_quote(symbol)
        return float(px.get("lastTrade") if isinstance(px, dict) else px or 0.0)
    except Exception:
        return 0.0

def sell_stock(symbol: str, qty: int | None = None, price: float | None = None,
               trade_time: str | None = None) -> bool:
    # PDT guard (margin only)
    acct_type = os.getenv("ACCOUNT_TYPE", "CASH")
    ok, reason = enforce_pdt_on_sell(symbol, qty or 0, now=trade_time, account_type=acct_type)
    if not ok:
        raise RuntimeError(f"[PDT] {reason}")

    holding = get_position(symbol)
    if not holding or int(holding.get("qty") or 0) <= 0:
        raise RuntimeError(f"No holdings to sell for {symbol}!")

    if qty is None or qty <= 0:
        qty = int(holding["qty"])
    if price is None or float(price) <= 0:
        last = holding.get("last_price") or 0.0
        live = _get_live_price(symbol)
        price = float(live or last or 0.0)

    proceeds = float(qty) * float(price)
    set_cash(get_cash() + proceeds)

    avg = get_avg_cost(symbol)
    pnl = (float(price) - float(avg)) * int(qty)

    insert_trade(symbol, "SELL", float(price), int(qty), float(pnl), trade_time)
    insert_or_update_holding(symbol, qty=-int(qty), avg_cost=float(avg), last_price=float(price))

    # If closed, clear trail peak
    try:
        if get_position_qty(symbol) <= 0:
            _trail_clear(symbol)
    except Exception:
        pass
    return True

# ─── Exit logic (SL/TP/Max days/Trailing stop) ───────────────────────────
def check_exit_orders(settings) -> None:
    from services.broker_api import sell_stock as broker_sell
    try:
        from services.etrade_service import fetch_etrade_quote
    except Exception:
        fetch_etrade_quote = None  # type: ignore

    logger.info(">>> Entered check_exit_orders() <<<")

    for symbol, qty, avg_cost, last_price in get_holdings():
        qty = int(qty)
        if qty <= 0:
            continue

        # --- live price (fallback to last_price) ---
        try:
            val = fetch_etrade_quote(symbol) if fetch_etrade_quote else last_price
            current = float(val.get("lastTrade") if isinstance(val, dict) else val or 0.0)
        except Exception:
            current = float(last_price or 0.0)

        pnl_pct = ((current - float(avg_cost)) / float(avg_cost) * 100.0) if float(avg_cost) else 0.0

        # --- STOP LOSS ---
        sl = float(getattr(settings, "stop_loss_pct", 0.0) or 0.0)
        if sl and pnl_pct <= -sl:
            logger.info(f"[SIM-SELL] {symbol} STOP LOSS qty={qty} px=${current:.2f} P/L={pnl_pct:.2f}%")
            broker_sell(symbol, qty, current)
            _trail_clear(symbol)
            continue

        # --- TAKE PROFIT ---
        tp = float(getattr(settings, "take_profit_pct", 0.0) or 0.0)
        if tp and pnl_pct >= tp:
            logger.info(f"[SIM-SELL] {symbol} TAKE PROFIT qty={qty} px=${current:.2f} P/L={pnl_pct:.2f}%")
            broker_sell(symbol, qty, current)
            _trail_clear(symbol)
            continue

        # --- MAX HOLD DAYS ---
        sell_after_days = getattr(settings, "sell_after_days", None)
        if sell_after_days:
            conn = _connect()
            row = conn.execute(
                "SELECT trade_time FROM simulation_trades "
                "WHERE symbol=? AND action='BUY' ORDER BY trade_time ASC LIMIT 1;",
                (symbol,)
            ).fetchone()
            conn.close()
            if row:
                entry_utc = _as_utc(row[0])
                now_utc = datetime.now(timezone.utc)
                hours = (now_utc - entry_utc).total_seconds() / 3600.0
                logger.debug(f"[SELL-DAYS] {symbol}: held {hours:.2f}h")
                if now_utc - entry_utc >= timedelta(days=int(sell_after_days)):
                    logger.info(f"[SIM-SELL] {symbol} MAX HOLD DAYS {sell_after_days}d qty={qty} px=${current:.2f}")
                    broker_sell(symbol, qty, current)
                    _trail_clear(symbol)
                    continue

        # --- TRAILING STOP (per-position) ---
        pct = float(getattr(settings, "trailing_stop_pct", 0.0) or 0.0)
        if getattr(settings, "use_trailing_stop", False) and pct > 0:
            peak, _since = _trail_get(symbol)
            if peak is None or current > peak:
                peak = current
                _trail_set(symbol, peak)

            trigger = peak * (1.0 - pct / 100.0)
            if current > 0 and current <= trigger:
                logger.info(
                    f"[SIM-SELL] {symbol} TRAILING STOP peak=${peak:.2f} "
                    f"trigger=${trigger:.2f} now=${current:.2f} ({pct:.2f}% trail)"
                )
                broker_sell(symbol, qty, current)
                _trail_clear(symbol)
                continue
# ─── Market hours helpers ────────────────────────────────────────────────
POST_OPEN_BUFFER = timedelta(minutes=0)

def market_is_open() -> bool:
    try:
        now = datetime.now(ET)
        sched = nyse.schedule(start_date=now.date(), end_date=now.date())
        if getattr(sched, "empty", True):
            return False
        row = sched.iloc[0]
        open_dt  = row["market_open"].tz_convert(ET) + POST_OPEN_BUFFER
        close_dt = row["market_close"].tz_convert(ET)
        return open_dt <= now < close_dt
    except Exception:
        return False

def seconds_until_open() -> float:
    try:
        now = datetime.now(ET)
        sched = nyse.schedule(start_date=now.date(), end_date=now.date() + timedelta(days=7))
        for _, row in sched.iterrows():
            open_dt = row["market_open"].tz_convert(ET) + POST_OPEN_BUFFER
            if open_dt > now:
                return float((open_dt - now).total_seconds())
        return 24 * 3600.0
    except Exception:
        return 24 * 3600.0

# ─── Price refresh ───────────────────────────────────────────────────────
def refresh_holdings_prices() -> None:
    try:
        from services.etrade_service import fetch_etrade_quote
    except Exception:
        fetch_etrade_quote = None  # type: ignore
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM holdings;")
    for (symbol,) in cur.fetchall():
        try:
            px = None
            if fetch_etrade_quote:
                val = fetch_etrade_quote(symbol)
                px = float(val.get("lastTrade") if isinstance(val, dict) else val or 0.0)
            if px and px > 0:
                conn.execute("UPDATE holdings SET last_price=? WHERE symbol=?;", (px, symbol))
        except Exception:
            pass
    conn.commit()
    conn.close()
