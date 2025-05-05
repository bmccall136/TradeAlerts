import sqlite3

DB = 'alerts_clean.db'
conn = sqlite3.connect(DB)
c = conn.cursor()

# Add the 'type' column if missing
c.execute("PRAGMA table_info(alerts)")
cols = [row[1] for row in c.fetchall()]
if 'type' not in cols:
    c.execute("ALTER TABLE alerts ADD COLUMN type TEXT DEFAULT 'sell'")
    conn.commit()
    print("✅ Added 'type' column")
else:
    print("ℹ️ 'type' column already exists")

conn.close()
