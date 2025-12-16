# live_peek_realized.py
import sqlite3
from datetime import date

DB = r"C:\TradeAlerts\live.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

print("=== realized_trades schema ===")
for row in cur.execute("PRAGMA table_info(realized_trades)"):
    print(row)

today = date.today().isoformat()  # e.g. '2025-11-24'
print("\n=== rows with today's date in close_date ===")
rows = list(cur.execute(
    """
    SELECT symbol, action, qty, gain, close_date
    FROM realized_trades
    WHERE date(close_date) = ?
    ORDER BY close_date DESC
    """,
    (today,),
))
for r in rows:
    print(r)

print("\nTotal realized gain today:", sum(r[3] for r in rows))
