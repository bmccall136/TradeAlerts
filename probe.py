import sqlite3

db = r"C:\TradeAlerts\live.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]

print("TABLES:")
for t in tables:
    print(" -", t)

targets = ["trades", "realized_trades", "trigger_fires", "buy_events", "sell_events", "position_opened"]

for t in targets:
    if t not in tables:
        continue

    print(f"\n=== {t} ===")
    cols = cur.execute(f"PRAGMA table_info({t})").fetchall()

    print("COLUMNS:")
    for c in cols:
        print(f" - {c[1]} ({c[2]})")

    try:
        rows = cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 3").fetchall()
        print("SAMPLE ROWS:")
        for r in rows:
            print(r)
    except Exception as e:
        print("SAMPLE ERROR:", e)

conn.close()