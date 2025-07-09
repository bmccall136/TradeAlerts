import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / 'alerts.db'
print("🔧 Recreating", db_path.resolve())

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("DROP TABLE IF EXISTS alerts")
c.execute("""
    CREATE TABLE alerts (
        symbol       TEXT PRIMARY KEY,
        name         TEXT,
        price        REAL,
        time         TEXT,
        trigger      TEXT,
        alert_type   TEXT,
        vwap         REAL,
        vwap_diff    REAL,
        qty          INTEGER,
        buy          BOOLEAN
    )
""")
conn.commit()
conn.close()
print("✅ Table created with 'time' column.")
