import sqlite3

conn = sqlite3.connect("alerts.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS alerts (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    price REAL,
    vwap REAL,
    vwap_diff REAL,
    qty INTEGER,
    sparkline TEXT,
    triggers TEXT,
    timestamp TEXT
)
""")
conn.commit()
conn.close()

print("✅ alerts table created in alerts.db")
