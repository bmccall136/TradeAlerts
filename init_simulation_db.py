# init_simulation_db.py

import sqlite3
import os

SIM_DB = "simulation.db"
if os.path.exists(SIM_DB):
    os.remove(SIM_DB)

conn = sqlite3.connect(SIM_DB)
c = conn.cursor()

# 1) state table
c.execute("""
    CREATE TABLE IF NOT EXISTS state (
      id           INTEGER PRIMARY KEY,
      cash         REAL    NOT NULL DEFAULT 10000,
      realized_pl  REAL    NOT NULL DEFAULT 0.0
    );
""")
c.execute("INSERT OR IGNORE INTO state (id, cash, realized_pl) VALUES (1, 10000, 0.0);")

# 2) holdings table
c.execute("""
    CREATE TABLE IF NOT EXISTS holdings (
      symbol     TEXT    PRIMARY KEY,
      qty        INTEGER NOT NULL,
      avg_cost   REAL    NOT NULL,
      last_price REAL    NOT NULL
    );
""")

# 3) simulation_trades table
c.execute("""
    CREATE TABLE IF NOT EXISTS simulation_trades (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol     TEXT    NOT NULL,
      action     TEXT    NOT NULL,
      price      REAL    NOT NULL,
      qty        INTEGER NOT NULL,
      trade_time TEXT    NOT NULL,
      pnl        REAL
    );
""")

conn.commit()
conn.close()
print("✅ simulation.db initialized with state, holdings, and simulation_trades.")
