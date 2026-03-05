import sqlite3
c=sqlite3.connect(r"C:\TradeAlerts\live.db")
r=c.execute("select id,symbol,action,ts_et,ts_utc,trade_time,price from trades where id=424").fetchone()
print(r)
