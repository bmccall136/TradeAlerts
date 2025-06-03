import sqlite3
import os

# This filename must match what your service code is using:
SIM_DB = "simulation.db"

# Delete any existing file so we start fresh:
if os.path.exists(SIM_DB):
    os.remove(SIM_DB)

conn = sqlite3.connect(SIM_DB)
c = conn.cursor()

# 1) Create 'account' table and seed with $10,000
c.execute('''
    CREATE TABLE IF NOT EXISTS account (
        id INTEGER PRIMARY KEY,
        cash_balance REAL NOT NULL
    );
''')
c.execute("INSERT INTO account (id, cash_balance) VALUES (1, 10000.00);")

# 2) Create 'holdings' table
c.execute('''
    CREATE TABLE IF NOT EXISTS holdings (
        symbol TEXT PRIMARY KEY,
        qty INTEGER NOT NULL,
        avg_cost REAL NOT NULL,
        last_price REAL NOT NULL
    );
''')

# 3) Create 'state' table (for storing realized P/L)
c.execute('''
    CREATE TABLE IF NOT EXISTS state (
        id INTEGER PRIMARY KEY,
        realized_pl REAL NOT NULL
    );
''')
c.execute("INSERT INTO state (id, realized_pl) VALUES (1, 0.0);")

# 4) Create 'trades' table
c.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        symbol TEXT,
        action TEXT,
        quantity INTEGER,
        price REAL,
        pl REAL
    );
''')
UPDATE state SET realized_pl = 0.0 WHERE id = 1;
conn.commit()
conn.close()
print("✅ simulation.db has been initialized (account, holdings, state, trades).")
