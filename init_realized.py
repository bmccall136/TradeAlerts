import sqlite3

db = r"C:\TradeAlerts\live.db"
con = sqlite3.connect(db)
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS realized_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  qty REAL NOT NULL,
  entry_price REAL NOT NULL,
  exit_price REAL NOT NULL,
  gain REAL NOT NULL,
  gain_pct REAL NOT NULL,
  open_date TEXT,
  close_date TEXT NOT NULL,
  order_id TEXT,
  notes TEXT
)
""")

cur.execute("CREATE INDEX IF NOT EXISTS idx_realized_close_date ON realized_trades(close_date)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_realized_symbol ON realized_trades(symbol)")

con.commit()

cols = [r[1] for r in cur.execute("PRAGMA table_info(realized_trades)").fetchall()]
con.close()

print("OK realized_trades ensured. cols=", cols)
