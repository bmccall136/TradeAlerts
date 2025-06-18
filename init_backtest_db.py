import sqlite3

DB = 'backtest.db'

schema = """
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS backtest_trades;
DROP TABLE IF EXISTS backtest_runs;

CREATE TABLE backtest_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,
    config_json  TEXT    NOT NULL,
    summary_json TEXT    NOT NULL
);

CREATE TABLE backtest_trades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    symbol     TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    price      REAL    NOT NULL,
    qty        INTEGER NOT NULL,
    trade_time TEXT    NOT NULL,
    pnl        REAL,
    FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
);
"""

if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print(f"Initialized {DB} with backtest_runs & backtest_trades")
