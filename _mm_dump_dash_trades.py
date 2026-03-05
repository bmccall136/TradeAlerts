import sqlite3
db=r"C:\TradeAlerts\live.db"
c=sqlite3.connect(db)
c.row_factory=sqlite3.Row
rows=c.execute("""
select id, symbol, action, qty, price, ts_utc, ts_et, trade_time
from trades
where upper(symbol)='DASH'
order by id desc
limit 25
""").fetchall()
print("rows:", len(rows))
for r in rows:
    print(dict(r))
