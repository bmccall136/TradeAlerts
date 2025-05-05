import sqlite3

conn = sqlite3.connect("alerts.db")
cur = conn.cursor()

# Add 'history' column if it doesn't already exist
try:
    cur.execute("ALTER TABLE alerts ADD COLUMN history TEXT")
    print("✅ 'history' column added to alerts table.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("ℹ️ 'history' column already exists — you're good.")
    else:
        raise

conn.commit()
conn.close()
