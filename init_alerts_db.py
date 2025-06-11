import sqlite3
import os

DB_FILE = "alerts.db"

# Delete existing DB file (optional)
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print(f"Deleted existing {DB_FILE}")

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Create alerts table
c.execute("""
CREATE TABLE alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT,
    timestamp TEXT,
    name      TEXT,
    price     REAL,
    vwap      REAL,
    vwap_diff REAL,
    sparkline TEXT,
    triggers  TEXT,
    qty       INTEGER,
    buy       INTEGER DEFAULT 0,
    volume    REAL,
    cleared   INTEGER DEFAULT 0,
    sma_on    INTEGER DEFAULT 0,
    rsi_on    INTEGER DEFAULT 0,
    macd_on   INTEGER DEFAULT 0,
    bb_on     INTEGER DEFAULT 0,
    vol_on    INTEGER DEFAULT 0,
    vwap_on   INTEGER DEFAULT 0,
    news_on   INTEGER DEFAULT 0
);
""")

# Create indicator_settings table (includes match_count now)
c.execute("""
CREATE TABLE indicator_settings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sma_on             INTEGER DEFAULT 1,
    rsi_on             INTEGER DEFAULT 1,
    macd_on            INTEGER DEFAULT 1,
    bb_on              INTEGER DEFAULT 1,
    vol_on             INTEGER DEFAULT 1,
    vwap_on            INTEGER DEFAULT 1,
    news_on            INTEGER DEFAULT 0,
    sma_length         INTEGER DEFAULT 20,
    rsi_len            INTEGER DEFAULT 14,
    rsi_overbought     INTEGER DEFAULT 70,
    rsi_oversold       INTEGER DEFAULT 30,
    macd_fast          INTEGER DEFAULT 12,
    macd_slow          INTEGER DEFAULT 26,
    macd_signal        INTEGER DEFAULT 9,
    bb_length          INTEGER DEFAULT 20,
    bb_std             REAL    DEFAULT 2.0,
    vol_multiplier     REAL    DEFAULT 1.5,
    vwap_threshold     REAL    DEFAULT 1.0,
    match_count        INTEGER DEFAULT 2,
    max_cash           REAL    DEFAULT 10000.0,
    max_trade_amount   REAL    DEFAULT 1000.0,
    timeframe          TEXT    DEFAULT '1d',
    rsi_slope_on       INTEGER DEFAULT 0,
    macd_hist_on       INTEGER DEFAULT 0,
    bb_breakout_on     INTEGER DEFAULT 0
);
""")


# Insert default row
c.execute("INSERT INTO indicator_settings (id) VALUES (1);")

conn.commit()
conn.close()
print("alerts.db initialized with alerts and indicator_settings tables.")
