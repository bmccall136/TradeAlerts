import sqlite3

DB = "live.db"

def cols(cur, table):
    return [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]

def pick(rt_cols, *names):
    for n in names:
        if n in rt_cols:
            return n
    return None

con = sqlite3.connect(DB)
cur = con.cursor()

# Ensure trades exists
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

# Print schema so we can see reality
print("realized_trades columns:", rt_cols)

# Your historical rows looked like: (id, symbol, action, qty, ..., close_date, ..., total_cost?, ..., price_sold, gain, ...)
c_symbol = pick(rt_set, "symbol", "SYM", "ticker")
c_action = pick(rt_set, "action", "side", "transactionType")
c_qty    = pick(rt_set, "qty", "quantity", "shares")
c_time   = pick(rt_set, "trade_time", "close_time", "close_datetime", "close_date", "date", "sold_date")
c_price  = pick(rt_set, "price_sold", "sold_price", "fill_price", "price", "close_price")
c_pnl    = pick(rt_set, "gain", "pnl", "gainLoss", "gain_loss")

# Some schemas store proceeds/total and not price_sold
c_proceeds = pick(rt_set, "proceeds", "total_proceeds", "amount")

print("picked:",
      {"symbol": c_symbol, "action": c_action, "qty": c_qty, "time": c_time,
       "price": c_price, "pnl": c_pnl, "proceeds": c_proceeds})

need = [c_symbol, c_qty, c_time]
missing = [n for n in ["symbol","qty","time"] if {"symbol":c_symbol,"qty":c_qty,"time":c_time}[n] is None]
if missing:
    raise SystemExit(f"ERROR: realized_trades missing required cols: {missing}")

# Build SELECT list
sel = [c_time, c_symbol, c_qty]
if c_action:   sel.append(c_action)
if c_price:    sel.append(c_price)
if c_pnl:      sel.append(c_pnl)
if c_proceeds: sel.append(c_proceeds)

sql = f"SELECT {', '.join(sel)} FROM realized_trades ORDER BY rowid DESC LIMIT 500"
rows = cur.execute(sql).fetchall()

inserted = 0
skipped_no_price = 0

for r in rows[::-1]:
    d = dict(zip(sel, r))

    sym = str(d[c_symbol]).strip().upper()
    qty = float(d[c_qty] or 0)

    # time (close_date is fine; we’ll store it as-is)
    t = d[c_time]
    if t is None:
        continue
    trade_time = str(t).strip()

    # action
    act = "SELL"
    if c_action and d.get(c_action) is not None:
        act = str(d[c_action]).strip().upper()

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
        skipped_no_price += 1
        continue

    # pnl
    pnl = 0.0
    if c_pnl and d.get(c_pnl) is not None:
        try:
            pnl = float(d[c_pnl])
        except:
            pnl = 0.0

    # dedupe
    exists = cur.execute(
        "SELECT 1 FROM trades WHERE trade_time=? AND symbol=? AND action=? AND qty=? AND price=? LIMIT 1",
        (trade_time, sym, act, qty, price),
    ).fetchone()
    if exists:
        continue

    cur.execute(
        "INSERT INTO trades (trade_time, symbol, action, qty, price, pnl) VALUES (?,?,?,?,?,?)",
        (trade_time, sym, act, qty, price, pnl),
    )
    inserted += 1

con.commit()
count = cur.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
print(f"OK: inserted {inserted} rows. skipped_no_price={skipped_no_price}. trades now has {count} rows.")

# Show last 10 trades so you can confirm immediately
rows = cur.execute(
    "SELECT trade_time, symbol, action, qty, price, pnl FROM trades ORDER BY rowid DESC LIMIT 10"
).fetchall()
print("last 10 trades:")
for rr in rows:
    print(" ", rr)

con.close()
