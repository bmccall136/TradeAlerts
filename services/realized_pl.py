# services/realized_pl.py
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
LIVE_DB = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS realized_trades (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  time        TEXT    NOT NULL,        -- ISO like 2025-08-22T10:31:00-04:00
  symbol      TEXT    NOT NULL,
  side        TEXT    NOT NULL CHECK(side IN ('BUY','SELL')),
  qty         INTEGER NOT NULL,
  price       REAL    NOT NULL,
  price_paid  REAL,                    -- average cost basis if you have it
  pnl         REAL    NOT NULL         -- realized P&L of this execution (+/-)
);
"""


def _conn():
    con = sqlite3.connect(LIVE_DB)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute(SCHEMA)
    return con


def summarize():
    """
    Returns dict with totals for: this_week, last_week, month, all
    (week = Mon–Sun in ET; month = calendar month in ET)
    """
    now = datetime.now(ET)

    # week ranges
    this_monday = (now - timedelta(days=(now.weekday()))).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(seconds=1)

    # month ranges
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # SQL helpers
    def _sum_between(start: datetime, end: datetime | None):
        q = "SELECT ROUND(COALESCE(SUM(pnl),0), 2) FROM realized_trades WHERE time >= ?"
        args = [start.isoformat()]
        if end:
            q += " AND time <= ?"
            args.append(end.isoformat())
        with _conn() as con:
            (val,) = con.execute(q, args).fetchone()
        return float(val)

    def _sum_all():
        with _conn() as con:
            (val,) = con.execute(
                "SELECT ROUND(COALESCE(SUM(pnl),0), 2) FROM realized_trades"
            ).fetchone()
        return float(val)

    return {
        "this_week": _sum_between(this_monday, None),
        "last_week": _sum_between(last_monday, last_sunday),
        "month": _sum_between(month_start, None),
        "all": _sum_all(),
    }


def recent_trades(limit: int = 50):
    with _conn() as con:
        rows = con.execute(
            "SELECT time, symbol, side, qty, price, price_paid, pnl "
            "FROM realized_trades ORDER BY time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    cols = ["time", "symbol", "side", "qty", "price", "price_paid", "pnl"]
    return [dict(zip(cols, r, strict=False)) for r in rows]
