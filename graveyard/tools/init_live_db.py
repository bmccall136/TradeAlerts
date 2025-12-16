# init_live_db.py
import os
import sqlite3

DB = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

schema = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS realized_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    action      TEXT    NOT NULL,           -- "SELL", "BUY TO COVER", etc.
    qty         REAL    NOT NULL,
    open_date   TEXT,                        -- YYYY-MM-DD
    close_date  TEXT    NOT NULL,            -- YYYY-MM-DD
    price_share REAL,
    proceeds    REAL,
    cost_share  REAL,
    total_cost  REAL,
    gain        REAL,
    term        TEXT                         -- "Short", "Long"
);

CREATE INDEX IF NOT EXISTS ix_rt_close_date ON realized_trades(close_date);
CREATE INDEX IF NOT EXISTS ix_rt_symbol     ON realized_trades(symbol);
"""

os.makedirs(os.path.dirname(DB), exist_ok=True)
conn = sqlite3.connect(DB)
conn.executescript(schema)
conn.commit()
conn.close()
print(f"✔ live DB initialized at {DB}")
