import sqlite3, json

DB_PATH = r"C:\TradeAlerts\live.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("""
    SELECT ts, symbol, headline, source, url
    FROM news_events
    ORDER BY ts DESC
    LIMIT 50
""")
rows = cur.fetchall()
conn.close()

data = [
    {
        "ts": ts,
        "symbol": sym,
        "headline": head,
        "source": src,
        "url": url,
    }
    for (ts, sym, head, src, url) in rows
]

print(json.dumps(data, indent=2))
