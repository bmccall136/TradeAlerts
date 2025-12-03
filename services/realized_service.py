# services/realized_service.py

import sqlite3
from datetime import datetime, timezone

def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS realized_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            qty         INTEGER NOT NULL,
            price_paid  REAL NOT NULL,
            price_sold  REAL NOT NULL,
            gain        REAL NOT NULL,
            open_date   TEXT,
            close_date  TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_realized_unique
        ON realized_trades(symbol, qty, close_date)
        """
    )
    conn.commit()


def insert_realized_trade(
    db_path: str,
    symbol: str,
    qty: int,
    price_paid: float,
    price_sold: float,
    open_ts=None,
    close_ts=None,
) -> float:
    """
    Insert a single realized trade row and return the dollar gain.

    qty          : positive integer (shares sold)
    price_paid   : cost basis per share
    price_sold   : sale price per share
    open_ts      : datetime when position opened (or first opened); optional
    close_ts     : datetime when this leg closed; defaults to now (UTC)
    """
    if close_ts is None:
        close_ts = datetime.now(timezone.utc)

    gain = (price_sold - price_paid) * qty

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO realized_trades
                (symbol, qty, price_paid, price_sold, gain, open_date, close_date)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                symbol,
                int(qty),
                float(price_paid),
                float(price_sold),
                float(gain),
                open_ts.isoformat() if hasattr(open_ts, "isoformat") else open_ts,
                close_ts.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return gain
