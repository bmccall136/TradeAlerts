import os, sqlite3

db = "live.db"
print("DB:", os.path.abspath(db))

con = sqlite3.connect(db)
cur = con.cursor()

tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("tables:", tables)

try:
    print("trades rows:", cur.execute("SELECT COUNT(*) FROM trades").fetchone()[0])
    print("trades schema:", cur.execute("PRAGMA table_info(trades)").fetchall())
    rows = cur.execute("SELECT rowid, trade_time, symbol, action, qty, price, pnl FROM trades ORDER BY rowid DESC LIMIT 10").fetchall()
    print("last 10 trades:")
    for r in rows:
        print(" ", r)
except Exception as e:
    print("ERROR reading trades:", repr(e))

con.close()
