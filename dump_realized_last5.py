import sqlite3
db = r"C:\TradeAlerts\live.db"
con = sqlite3.connect(db)
cur = con.cursor()
rows = cur.execute("select symbol, action, qty, price_paid, price_sold, gain, close_date from realized_trades order by id desc limit 5").fetchall()
con.close()
print(rows)
