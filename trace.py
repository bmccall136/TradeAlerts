import sqlite3

conn = sqlite3.connect("alerts_clean.db")
c = conn.cursor()
c.execute("SELECT * FROM alerts")
rows = c.fetchall()

for row in rows:
    print(row)

conn.close()
