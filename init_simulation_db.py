import sqlite3
import os

SIM_DB = "simulation.db"

if os.path.exists(SIM_DB):
    os.remove(SIM_DB)

conn = sqlite3.connect(SIM_DB)
c = conn.cursor()

c.execute('''
    CREATE TABLE account (
        id INTEGER PRIMARY KEY,
        cash_balance REAL NOT NULL
    )
''')
c.execute("INSERT INTO account (id, cash_balance) VALUES (1, 10000.00)")

c.execute('''
    CREATE TABLE holdings (
        symbol TEXT PRIMARY KEY,
        qty INTEGER NOT NULL,
        avg_cost REAL NOT NULL
    )
''')

c.execute('''
    CREATE TABLE trade_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        symbol TEXT,
        action TEXT,
        qty INTEGER,
        price REAL
    )
''')

conn.commit()
conn.close()
print("✅ Recreated simulation.db with account, holdings, and trade_history.")