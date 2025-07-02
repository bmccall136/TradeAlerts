# init_backtest_db.py
import sqlite3

conn = sqlite3.connect('backtest.db')
c = conn.cursor()

# drop old tables if they exist
c.execute("DROP TABLE IF EXISTS backtest_runs;")
c.execute("DROP TABLE IF EXISTS backtest_trades;")

# create backtest_runs with started_at & settings_json
c.execute("""
CREATE TABLE backtest_runs (
    id            INTEGER PRIMARY KEY,
    started_at    TEXT    NOT NULL,
    settings_json TEXT    NOT NULL
);
""")

# create backtest_trades
c.execute("""
CREATE TABLE backtest_trades (
    id        INTEGER PRIMARY KEY,
    run_id    INTEGER NOT NULL,
    symbol    TEXT    NOT NULL,
    date      TEXT,
    action    TEXT,
    price     REAL,
    qty       INTEGER,
    pnl       REAL,
    FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
);
""")

conn.commit()
conn.close()
print("Initialized backtest.db with backtest_runs & backtest_trades")
