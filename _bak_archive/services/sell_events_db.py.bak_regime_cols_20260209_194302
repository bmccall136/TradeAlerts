# services/sell_events_db.py
# DB-backed sell lifecycle logging for Sell Analytics (LIVE_DB is source of truth)

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

LIVE_DB_FILENAME = "live.db"

def _resolve_db_path(db_path: Optional[str] = None) -> str:
    if db_path:
        return str(db_path)
    # Default: live.db at project root
    here = Path(__file__).resolve()
    return str(here.parent.parent / LIVE_DB_FILENAME)

def ensure_sell_events_table(db_path: Optional[str] = None) -> None:
    p = _resolve_db_path(db_path)
    con = sqlite3.connect(p, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sell_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                event TEXT NOT NULL,
                reason TEXT,
                detail TEXT,
                order_id TEXT,
                price REAL,
                qty INTEGER,
                mode TEXT
            )
            """
        )
        con.commit()
    finally:
        con.close()

def log_sell_event(
    *,
    db_path: Optional[str] = None,
    symbol: str,
    event: str,
    reason: Optional[str] = None,
    detail: Optional[str] = None,
    order_id: Optional[str] = None,
    price: Optional[float] = None,
    qty: Optional[int] = None,
    mode: Optional[str] = None,
    ts_utc: Optional[int] = None,
) -> None:
    p = _resolve_db_path(db_path)
    con = sqlite3.connect(p, timeout=30)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        if ts_utc is None:
            ts_utc = int(time.time())
        con.execute(
            """
            INSERT INTO sell_events (
                ts_utc, symbol, event, reason, detail,
                order_id, price, qty, mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (int(ts_utc), str(symbol), str(event), reason, detail, order_id, price, qty, mode),
        )
        con.commit()
    finally:
        con.close()
