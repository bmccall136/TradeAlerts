# rebuild_alerts_db.py
import sqlite3

conn = sqlite3.connect("alerts_clean.db")
cur = conn.cursor()

# Drop old table if it exists
cur.execute("DROP TABLE IF EXISTS alerts")

# Recreate the alerts table with correct schema
cur.execute("""
CREATE TABLE alerts (
    symbol TEXT,
    name TEXT,
    signal TEXT,
    time TEXT,
    confidence INTEGER,
    price REAL,
    sparkline TEXT,
    signal_type TEXT
)
""")

conn.commit()
conn.close()

print("✅ alerts_clean.db has been reset with correct schema.")
