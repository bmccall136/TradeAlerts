import sqlite3, shutil, datetime
from datetime import timezone
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

DB = r"C:\TradeAlerts\live.db"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = DB + f".bak_trade_time_backfill_{ts}"
shutil.copy2(DB, bak)
print("Backup ->", bak)

def parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    # Try ISO first (ts_utc often looks like 2026-03-05T09:53:55-05:00)
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
        return dt
    except Exception:
        pass
    # Try ET naive format (ts_et: 2026-03-05 09:53:55)
    try:
        dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        if ET:
            dt = dt.replace(tzinfo=ET)
        else:
            # fallback: treat as local time, but still produce a value
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

con = sqlite3.connect(DB)
cur = con.cursor()

rows = cur.execute("""
SELECT id, ts_utc, ts_et, trade_time
FROM trades
WHERE trade_time IS NULL OR trade_time=0 OR trade_time=''
ORDER BY id ASC
""").fetchall()

print("Need backfill:", len(rows))

updated = 0
for _id, ts_utc, ts_et, trade_time in rows:
    dt = parse_dt(ts_utc) or parse_dt(ts_et)
    if not dt:
        continue
    # normalize to UTC epoch seconds
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch = int(dt.astimezone(timezone.utc).timestamp())
    cur.execute("UPDATE trades SET trade_time=? WHERE id=?", (epoch, _id))
    updated += 1

con.commit()
con.close()
print("Updated:", updated)
