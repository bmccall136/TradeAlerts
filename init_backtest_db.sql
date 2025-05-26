CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    config_json TEXT,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    run_id INTEGER,
    symbol TEXT,
    action TEXT,
    price REAL,
    qty INTEGER,
    trade_time TEXT,
    pnl REAL
);
