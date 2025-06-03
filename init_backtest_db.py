# File: init_backtest_db.py
import sqlite3

BACKTEST_DB = "backtest.db"

ddl = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    config_json TEXT  NOT NULL,
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER  NOT NULL,
    symbol     TEXT     NOT NULL,
    action     TEXT     NOT NULL,
    price      REAL     NOT NULL,
    qty        INTEGER  NOT NULL,
    trade_time TEXT     NOT NULL,
    pnl        REAL     NULL,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
"""

conn = sqlite3.connect(BACKTEST_DB)
conn.executescript(ddl)
conn.commit()
conn.close()

print(f"Initialized {BACKTEST_DB} with the required tables.")
