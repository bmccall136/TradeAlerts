import sqlite3

conn = sqlite3.connect("alerts.db")
cur = conn.cursor()
cur.execute("ALTER TABLE alerts ADD COLUMN news_url TEXT;")
conn.commit()
conn.close()
