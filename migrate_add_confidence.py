import sqlite3

DB = 'alerts.db'

conn = sqlite3.connect(DB)
c = conn.cursor()

# Add 'confidence' column if it doesn't already exist
# Note: SQLite's ALTER TABLE only allows adding simple columns.
try:
    c.execute("ALTER TABLE alerts ADD COLUMN confidence REAL DEFAULT NULL;")
    print("✅ Added 'confidence' column.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ️  'confidence' column already exists; skipping.")
    else:
        raise

conn.commit()
conn.close()
