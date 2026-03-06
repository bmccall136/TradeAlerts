import sqlite3, time

DB=r"C:\TradeAlerts\live.db"
TID=424

con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
r=con.execute("SELECT * FROM trades WHERE id=?", (TID,)).fetchone()
print("trade_row:", dict(r) if r else None)

sym = (r["symbol"] if r else None)
buy_ts = None
if r:
    # try a few likely timestamp columns
    for k in ("ts_utc","ts_utc_epoch","trade_time","time_utc","opened_ts_utc"):
        if k in r.keys() and r[k]:
            try:
                buy_ts = int(float(r[k]))
                break
            except Exception:
                pass
print("sym:", sym, "buy_ts_guess:", buy_ts)

if sym and buy_ts:
    # 1) any realized close for this symbol AFTER the buy timestamp?
    rt = con.execute("""
        SELECT id, symbol, close_ts_utc, gain, close_price, qty
        FROM realized_trades
        WHERE symbol=? AND close_ts_utc>=?
        ORDER BY close_ts_utc ASC
        LIMIT 5
    """, (sym, buy_ts)).fetchall()
    print("realized_trades_after_buy:", [tuple(x) for x in rt])

    # 2) any sell_events AFTER buy timestamp?
    se = con.execute("""
        SELECT id, ts_utc, action, reason, price
        FROM sell_events
        WHERE symbol=? AND ts_utc>=?
        ORDER BY ts_utc ASC
        LIMIT 20
    """, (sym, buy_ts)).fetchall()
    print("sell_events_after_buy:", [tuple(x) for x in se])

con.close()
