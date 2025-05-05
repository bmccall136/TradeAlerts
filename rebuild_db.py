import sqlite3
import os

# Backup original DB just in case
if os.path.exists("alerts.db"):
    os.rename("alerts.db", "alerts_backup.db")

# Reconnect using backup
conn = sqlite3.connect("alerts_backup.db")
cur = conn.cursor()

# Rename the old alerts table
cur.execute("ALTER TABLE alerts RENAME TO alerts_old")

# Create the new alerts table
cur.execute("""
    CREATE TABLE alerts (
        symbol TEXT,
        name TEXT,
        signal TEXT,
        timestamp TEXT,
        confidence TEXT,
        price TEXT,
        sparkline TEXT,
        chart_url TEXT
    )
""")

# Migrate data from alerts_old
cur.execute("""
    INSERT INTO alerts (symbol, name, signal, timestamp, confidence, price, sparkline, chart_url)
    SELECT symbol, name, signal, timestamp, confidence, price, sparkline, '' FROM alerts_old
""")

# Finalize changes
conn.commit()
conn.close()

print("✅ Database rebuilt and migrated successfully.")