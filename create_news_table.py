import os
import sqlite3

DB_PATH = os.environ.get("LIVE_DB", r"C:\TradeAlerts\live.db")

DDL = """
CREATE TABLE IF NOT EXISTS news_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,        -- ISO8601 UTC timestamp / publishedAt
    symbol TEXT NOT NULL,    -- e.g. 'AAPL'
    headline TEXT,           -- news title
    source TEXT,             -- publisher name
    url TEXT,                -- article URL
    raw_json TEXT            -- full JSON blob from API
);

CREATE INDEX IF NOT EXISTS idx_news_symbol_ts
    ON news_events(symbol, ts DESC);
"""

def main() -> None:
    print(f"[news] Using DB_PATH = {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(DDL)
    conn.commit()
    conn.close()
    print("[news] news_events table and index are ready.")

if __name__ == "__main__":
    main()
