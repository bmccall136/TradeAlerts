import sqlite3, sys
from datetime import datetime, timezone, timedelta

ET_OFFSET_HOURS = -5  # naive ET offset; adjust if you store ET-naive timestamps during DST

def _parse_trade_time(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        ts = float(v)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    s = str(v).strip()
    if s.isdigit():
        ts = float(s)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        # 'YYYY-MM-DD HH:MM:SS' (assume ET-naive)
        if "T" not in s and "+" not in s and "Z" not in s:
            dt = datetime.fromisoformat(s)
            et = timezone(timedelta(hours=ET_OFFSET_HOURS))
            return dt.replace(tzinfo=et).astimezone(timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            et = timezone(timedelta(hours=ET_OFFSET_HOURS))
            dt = dt.replace(tzinfo=et).astimezone(timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def fifo_realized(trades):
    lots = {}  # symbol -> list of [qty_remaining, cost_per_share, open_time_utc]
    realized = []
    trades_sorted = sorted(trades, key=lambda x: x["time_utc"] or datetime.min.replace(tzinfo=timezone.utc))

    for t in trades_sorted:
        sym = t["symbol"]
        act = (t["action"] or "").upper()
        qty = float(t["qty"] or 0.0)
        px  = float(t["price"] or 0.0)
        tm  = t["time_utc"]
        if qty <= 0 or px <= 0 or not sym or tm is None:
            continue

        if act == "BUY":
            lots.setdefault(sym, []).append([qty, px, tm])

        elif act == "SELL":
            remaining = qty
            while remaining > 1e-9 and lots.get(sym):
                lot_qty, lot_cost, lot_tm = lots[sym][0]
                take = min(remaining, lot_qty)

                total_cost = take * lot_cost
                proceeds = take * px
                gain = proceeds - total_cost

                realized.append({
                    "symbol": sym,
                    "close_time_utc": tm,
                    "qty": take,
                    "cost_share": lot_cost,
                    "total_cost": total_cost,
                    "close_price": px,
                    "proceeds": proceeds,
                    "gain": gain,
                    "open_time_utc": lot_tm,
                })

                lot_qty -= take
                remaining -= take
                if lot_qty <= 1e-9:
                    lots[sym].pop(0)
                else:
                    lots[sym][0][0] = lot_qty

    return realized

def buckets(realized_rows, now_utc):
    et = timezone(timedelta(hours=ET_OFFSET_HOURS))
    now_et = now_utc.astimezone(et)

    start_day_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    start_week_et = start_day_et - timedelta(days=start_day_et.weekday())  # Monday
    start_month_et = start_day_et.replace(day=1)

    def sum_since(start_et):
        start_utc = start_et.astimezone(timezone.utc)
        g = 0.0
        for r in realized_rows:
            if r["close_time_utc"] >= start_utc:
                g += float(r["gain"] or 0.0)
        return g

    return sum_since(start_day_et), sum_since(start_week_et), sum_since(start_month_et)

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "live.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    if "trades" not in tables:
        print("ERROR: trades table not found in", db_path)
        sys.exit(2)

    cur.execute("PRAGMA table_info(trades)")
    cols = [r[1] for r in cur.fetchall()]

    time_col = "trade_time" if "trade_time" in cols else ("time" if "time" in cols else cols[0])
    sym_col  = "symbol" if "symbol" in cols else None
    act_col  = "action" if "action" in cols else ("side" if "side" in cols else None)
    qty_col  = "qty" if "qty" in cols else ("quantity" if "quantity" in cols else None)
    px_col   = "price" if "price" in cols else ("fill_price" if "fill_price" in cols else None)

    missing = [n for n,v in [("symbol",sym_col),("action/side",act_col),("qty/quantity",qty_col),("price/fill_price",px_col)] if v is None]
    if missing:
        print("ERROR: trades schema missing columns:", ", ".join(missing))
        print("Columns:", cols)
        sys.exit(3)

    cur.execute(f"SELECT {time_col},{sym_col},{act_col},{qty_col},{px_col} FROM trades ORDER BY {time_col} ASC")
    trades=[]
    for r in cur.fetchall():
        t=_parse_trade_time(r[0])
        trades.append({
            "time_utc": t,
            "symbol": (r[1] or "").strip().upper(),
            "action": (r[2] or "").strip().upper(),
            "qty": r[3],
            "price": r[4],
        })

    realized_rows = fifo_realized(trades)
    now_utc = datetime.now(timezone.utc)
    day, week, month = buckets(realized_rows, now_utc)

    print("Realized (computed from trades, FIFO):")
    print(f"  Day:   {day:,.2f}")
    print(f"  Week:  {week:,.2f}")
    print(f"  Month: {month:,.2f}")
    print(f"  Rows realized: {len(realized_rows)} from trades={len(trades)}")

    if "--write" in sys.argv:
        if "realized_trades" not in tables:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS realized_trades ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "symbol TEXT,"
                "close_date TEXT,"
                "qty REAL,"
                "cost_share REAL,"
                "total_cost REAL,"
                "close_price REAL,"
                "proceeds REAL,"
                "gain REAL,"
                "open_date TEXT"
                ")"
            )
            conn.commit()

        cur.execute("DELETE FROM realized_trades")
        for r in realized_rows:
            cur.execute(
                "INSERT INTO realized_trades(symbol, close_date, qty, cost_share, total_cost, close_price, proceeds, gain, open_date) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    r["symbol"],
                    r["close_time_utc"].isoformat(),
                    float(r["qty"]),
                    float(r["cost_share"]),
                    float(r["total_cost"]),
                    float(r["close_price"]),
                    float(r["proceeds"]),
                    float(r["gain"]),
                    r["open_time_utc"].isoformat(),
                ),
            )
        conn.commit()
        print("WROTE realized_trades table (rebuilt from trades).")

    conn.close()

if __name__ == "__main__":
    main()
