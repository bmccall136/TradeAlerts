import sqlite3

conn = sqlite3.connect('alerts.db')
c = conn.cursor()
# Add vwap column if it doesn't exist
try:
    c.execute("ALTER TABLE alerts ADD COLUMN vwap REAL DEFAULT NULL;")
except sqlite3.OperationalError:
    pass  # already exists
# Add sparkline column
try:
    c.execute("ALTER TABLE alerts ADD COLUMN sparkline TEXT DEFAULT NULL;")
except sqlite3.OperationalError:
    pass
conn.commit()
conn.close()
print("Schema updated.")
