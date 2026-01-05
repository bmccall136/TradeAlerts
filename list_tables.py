import sqlite3

db = r"C:\TradeAlerts\live.db"
con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print(rows)
con.close()
