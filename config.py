# config.py

DB_PATH = "/path/to/your/app.db"
SIM_DB = "simulation.db"
BACKTEST_DB = "backtest.db"

# <<< add this >>>
BACKTEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  start_date TEXT,
  end_date TEXT,
  starting_cash REAL,
  ending_cash REAL,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES backtest_runs(id),
  symbol TEXT NOT NULL,
  action TEXT NOT NULL,
  price REAL NOT NULL,
  qty INTEGER NOT NULL,
  time TEXT NOT NULL,
  pnl REAL,
  FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
);
"""
