import sqlite3

DB = "alerts.db"

conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    alert_type TEXT,
    price REAL,
    confidence REAL,
    timestamp TEXT,
    triggers TEXT,
    sparkline TEXT,
    cleared INTEGER DEFAULT 0
)
''')
conn.commit()
conn.close()
print("alerts table ensured.")
