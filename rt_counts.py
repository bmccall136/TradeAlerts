import sqlite3
DB = r"C:\TradeAlerts\live.db"
con = sqlite3.connect(DB)
cur = con.cursor()
rows = cur.execute("""
select close_date, count(*)
from realized_trades
group by close_date
order by close_date desc
limit 15
""").fetchall()
print(rows)
con.close()
