import sqlite3
import os
from datetime import datetime

# Path to your simulation database file; adjust as needed
SIM_DB = os.path.join(os.getcwd(), 'simulation.db')


def init_simulation_db():
    print("🔧 initializing simulation.db schema…")
    conn = sqlite3.connect(SIM_DB, detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()

    # drop tables if they exist
    cur.execute("DROP TABLE IF EXISTS state;")
    cur.execute("DROP TABLE IF EXISTS holdings;")
    cur.execute("DROP TABLE IF EXISTS simulation_trades;")

    # recreate state with cash & realized_pl
    cur.execute("""
      CREATE TABLE state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        cash REAL DEFAULT 0,
        realized_pl REAL DEFAULT 0
      );
    """)

    # recreate holdings
    cur.execute("""
      CREATE TABLE holdings (
        symbol TEXT PRIMARY KEY,
        qty INTEGER NOT NULL,
        avg_cost REAL NOT NULL,
        last_price REAL NOT NULL
      );
    """)

    # recreate simulation_trades
    cur.execute("""
      CREATE TABLE simulation_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        action TEXT CHECK (action IN ('BUY','SELL')) NOT NULL,
        price REAL NOT NULL,
        qty INTEGER NOT NULL,
        trade_time TEXT NOT NULL,
        pnl REAL
      );
    """)

    # initialize the one row of state
    cur.execute("INSERT INTO state (id, cash, realized_pl) VALUES (1, 10000, 0);")

    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_simulation_db()
