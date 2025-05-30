import sqlite3

conn = sqlite3.connect("alerts.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    timestamp TEXT,
    name TEXT,
    price REAL,
    time TEXT,
    triggers TEXT,
    sparkline TEXT,
    vwap REAL,
    vwap_diff REAL,
    cleared INTEGER DEFAULT 0
)
""")
conn.commit()
conn.close()
print("✅ alerts.db schema initialized.")
