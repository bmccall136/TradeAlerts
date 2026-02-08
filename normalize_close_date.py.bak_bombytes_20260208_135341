import sqlite3

DB = r"C:\TradeAlerts\live.db"

con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute("""
UPDATE realized_trades
SET close_date = substr(close_date, 1, 10)
WHERE close_date LIKE '____-__-__ %'
""")

con.commit()
print("normalized rows =", cur.rowcount)

rows = cur.execute("""
SELECT close_date, COUNT(*)
FROM realized_trades
GROUP BY close_date
ORDER BY close_date DESC
LIMIT 15
""").fetchall()

print(rows)
con.close()
