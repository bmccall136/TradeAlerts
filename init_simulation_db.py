
import sqlite3
from datetime import datetime

SIM_DB = "simulation_state.db"

conn = sqlite3.connect(SIM_DB)
cursor = conn.cursor()

# Drop old tables (if needed)
cursor.execute("DROP TABLE IF EXISTS simulation_state")
cursor.execute("DROP TABLE IF EXISTS positions")
cursor.execute("DROP TABLE IF EXISTS simulation_trades")

# Create fresh simulation_state with $10,000 cash
cursor.execute("""
    CREATE TABLE simulation_state (
        cash REAL,
        open_value REAL,
        realized_pnl REAL
    )
""")
cursor.execute("INSERT INTO simulation_state VALUES (?, ?, ?)", (10000.0, 0.0, 0.0))

# Create open positions table
cursor.execute("""
    CREATE TABLE positions (
        symbol TEXT PRIMARY KEY,
        quantity REAL,
        price REAL
    )
""")
# Create trade history table
cursor.execute("""
    CREATE TABLE simulation_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        quantity REAL,
        price REAL,
        timestamp TEXT
    )
""")
conn.commit()
conn.close()

print("✅ simulation_state.db initialized with $10,000 starting cash.")
