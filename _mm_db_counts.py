import sqlite3
DB=r'C:\TradeAlerts\live.db'
con=sqlite3.connect(DB); cur=con.cursor()
print('DB',DB)
for name in ['signal_fires','trigger_fires','buy_events','sell_events','trades']:
  r=cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
  if not r: print(name,'MISSING'); continue
  n=cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
  print(name,'rows',n)
con.close()
