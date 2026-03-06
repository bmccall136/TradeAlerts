import sqlite3

DB=r"C:\TradeAlerts\live.db"
TID=424

def cols(con, table):
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []

def first_present(all_cols, candidates):
    for c in candidates:
        if c in all_cols:
            return c
    return None

con=sqlite3.connect(DB); con.row_factory=sqlite3.Row

r=con.execute("SELECT * FROM trades WHERE id=?", (TID,)).fetchone()
print("trade_row:", dict(r) if r else None)

sym = (r["symbol"] if r else None)
buy_ts = None
if r:
    # trade_time looks like epoch string in your row
    for k in ("trade_time","ts_utc_epoch","opened_ts_utc","ts_utc"):
        if k in r.keys() and r[k]:
            v = r[k]
            # ts_utc may be ISO; trade_time is epoch string
            try:
                buy_ts = int(float(v))
                break
            except Exception:
                pass

print("sym:", sym, "buy_ts_guess:", buy_ts)

# --- realized_trades schema + query (schema-adaptive) ---
rt_cols = cols(con, "realized_trades")
print("realized_trades_cols:", rt_cols)

if sym and buy_ts and rt_cols:
    c_sym   = first_present(rt_cols, ["symbol","sym","ticker"])
    c_close = first_present(rt_cols, ["close_ts_utc","close_ts","closed_ts_utc","ts_utc","close_time","closed_epoch"])
    c_gain  = first_present(rt_cols, ["gain","pnl","gain_loss","profit","pl"])
    c_qty   = first_present(rt_cols, ["qty","quantity","shares"])
    c_price = first_present(rt_cols, ["price","close_px","close_price","exit_price","sell_price"])

    # build SELECT list safely
    sel = ["id"]
    if c_sym: sel.append(c_sym)
    if c_close: sel.append(c_close)
    if c_gain: sel.append(c_gain)
    if c_price: sel.append(c_price)
    if c_qty: sel.append(c_qty)

    if c_sym and c_close:
        q = f"""
        SELECT {", ".join(sel)}
        FROM realized_trades
        WHERE {c_sym}=? AND {c_close}>=?
        ORDER BY {c_close} ASC
        LIMIT 20
        """
        rt = con.execute(q, (sym, buy_ts)).fetchall()
        print("realized_trades_after_buy:", [tuple(x) for x in rt])
    else:
        print("realized_trades_after_buy: SKIP (missing symbol/close_ts column)")

# --- sell_events schema + query ---
se_cols = cols(con, "sell_events")
print("sell_events_cols:", se_cols)

if sym and buy_ts and se_cols:
    c_sym   = first_present(se_cols, ["symbol","sym","ticker"])
    c_ts    = first_present(se_cols, ["ts_utc","ts","ts_utc_epoch","epoch","created_ts_utc"])
    c_act   = first_present(se_cols, ["action","event","status","type"])
    c_reason= first_present(se_cols, ["reason","detail","message"])
    c_price = first_present(se_cols, ["price","px","fill_price","limit_price"])

    sel = ["id"]
    if c_ts: sel.append(c_ts)
    if c_act: sel.append(c_act)
    if c_reason: sel.append(c_reason)
    if c_price: sel.append(c_price)

    if c_sym and c_ts:
        q = f"""
        SELECT {", ".join(sel)}
        FROM sell_events
        WHERE {c_sym}=? AND {c_ts}>=?
        ORDER BY {c_ts} ASC
        LIMIT 50
        """
        se = con.execute(q, (sym, buy_ts)).fetchall()
        print("sell_events_after_buy:", [tuple(x) for x in se])
    else:
        print("sell_events_after_buy: SKIP (missing symbol/ts column)")

con.close()
