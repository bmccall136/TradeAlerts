import sqlite3

conn = sqlite3.connect("alerts.db")  # or whatever path you use
cur = conn.cursor()

# List columns for the 'positions' table
cur.execute("PRAGMA table_info(positions)")
for col in cur.fetchall():
    print(col)

conn.close()
