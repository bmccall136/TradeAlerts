import sqlite3
from datetime import datetime

DB = "live.db"

def cols(cur, table):
    return [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]

def first_existing(name_list, colset):
    for n in name_list:
        if n in colset:
            return n
    return None

con = sqlite3.connect(DB)
cur = con.cursor()

# Ensure trades exists (safe if already there)
cur.execute("""
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_time TEXT NOT NULL,
  symbol TEXT NOT NULL,
  action TEXT NOT NULL,
  qty REAL NOT NULL,
  price REAL NOT NULL,
  pnl REAL DEFAULT 0
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_time   ON trades(trade_time)")
cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")

rt_cols = cols(cur, "realized_trades")
rt_set  = set(rt_cols)

# Pick best columns available in your realized_trades schema
c_symbol = first_existing(["symbol", "SYM", "ticker"], rt_set)
c_action = first_existing(["action", "side", "transactionType"], rt_set)
c_qty    = first_existing(["qty", "quantity", "shares"], rt_set)

# date/time-ish
c_time   = first_existing(["trade_time", "close_time", "close_datetime", "close_date", "date", "sold_date"], rt_set)

# price-ish (prefer explicit sold/fill price)
c_price  = first_existing(["price_sold", "fill_price", "price", "sold_price", "close_price"], rt_set)

# pnl-ish (prefer realized gain)
c_pnl    = first_existing(["gain", "pnl", "gainLoss", "gain_loss"], rt_set)

# proceeds/total can be used if price is missing
c_proceeds = first_existing(["proceeds", "total_proceeds", "amount"], rt_set)

if not all([c_symbol, c_action, c_qty, c_time]):
    raise SystemExit(f"Missing required cols in realized_trades. Have: {rt_cols}")

# Build SELECT list dynamically
sel = [c_time, c_symbol, c_action, c_qty]
if c_price:   sel.append(c_price)
if c_pnl:     sel.append(c_pnl)
if c_proceeds: sel.append(c_proceeds)

sql = f"SELECT {', '.join(sel)} FROM realized_trades ORDER BY rowid DESC LIMIT 200"
rows = cur.execute(sql).fetchall()

inserted = 0
for r in rows[::-1]:  # oldest -> newest for nicer ordering
    d = dict(zip(sel, r))

    sym = str(d[c_symbol]).strip().upper()
    act = str(d[c_action]).strip().upper()
    qty = float(d[c_qty] or 0)

    # normalize time
    t = d[c_time]
    if t is None:
        continue
    t = str(t).strip()
    # If it's only YYYY-MM-DD, keep it as-is (dashboard usually just prints it)
    trade_time = t

    # price
    price = None
    if c_price and d.get(c_price) is not None:
        try:
            price = float(d[c_price])
        except:
            price = None
    if price is None and c_proceeds and d.get(c_proceeds) is not None and qty:
        try:
            price = float(d[c_proceeds]) / qty
        except:
            price = None
    if price is None:
        # can't write trades row without a price
        continue

    pnl = 0.0
    if c_pnl and d.get(c_pnl) is not None:
        try:
            pnl = float(d[c_pnl])
        except:
            pnl = 0.0

    # Avoid duplicate backfill rows: simple check
    exists = cur.execute(
        "SELECT 1 FROM trades WHERE trade_time=? AND symbol=? AND action=? AND qty=? AND price=? LIMIT 1",
        (trade_time, sym, act, qty, price)
    ).fetchone()
    if exists:
        continue

    cur.execute(
        "INSERT INTO trades (trade_time, symbol, action, qty, price, pnl) VALUES (?,?,?,?,?,?)",
        (trade_time, sym, act, qty, price, pnl)
    )
    inserted += 1

con.commit()

count = cur.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
print(f"OK: backfilled {inserted} rows. trades now has {count} rows.")

con.close()
