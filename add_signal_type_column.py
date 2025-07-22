import sqlite3

conn = sqlite3.connect("alerts_clean.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE alerts ADD COLUMN signal_type TEXT DEFAULT 'BUY'")
    print("✅ 'signal_type' column added successfully.")
except sqlite3.OperationalError as e:
    print("⚠️ Error:", e)

conn.commit()
conn.close()
