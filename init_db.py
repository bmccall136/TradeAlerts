
import sqlite3

conn = sqlite3.connect("alerts_clean.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS alerts (
    symbol TEXT,
    name TEXT,
    signal TEXT,
    time TEXT,
    confidence INTEGER,
    price REAL,
    sparkline TEXT
)
""")
conn.commit()
conn.close()
print("✅ alerts_clean.db schema initialized.")
