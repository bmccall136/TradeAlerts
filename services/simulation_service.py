import sqlite3
from datetime import datetime, date
import yfinance as yf

SIM_DB = "simulation.db"   # Or the correct path to your SQLite file

def get_trades():
    """
    Fetch all historical trades (both BUY and SELL) from the simulation_trades table.
    Returns a list of dicts:
      [
        {
          'id': 1,
          'symbol': 'AAPL',
          'action': 'BUY',
          'price': 150.0,
          'qty': 10.0,
          'trade_time': '2025-06-03 14:35:00',
          'pnl': None           # p/l is only set on SELL trades
        },
        { … },
        …
      ]
    """
    conn = sqlite3.connect(SIM_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Adjust "simulation_trades" to match your actual table name if different
    c.execute("SELECT id, symbol, action, price, qty, trade_time, pnl FROM simulation_trades ORDER BY trade_time DESC")
    rows = c.fetchall()
    conn.close()

    trades = []
    for row in rows:
        trades.append({
            'id': row['id'],
            'symbol': row['symbol'],
            'action': row['action'],
            'price': float(row['price']),
            'qty': float(row['qty']),
            'trade_time': row['trade_time'],   # e.g. "2025-06-03 14:35:00"
            'pnl': float(row['pnl']) if row['pnl'] is not None else None
        })
    return trades


def get_realized_pl():
    """
    Return the sum of P/L from all closed (SELL) trades in the simulation_trades table.
    If your table stores 'pnl' on each SELL row, simply sum that column. 
    """
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("""
        SELECT SUM(pnl) 
          FROM simulation_trades 
         WHERE action = 'SELL'
    """)
    row = c.fetchone()
    conn.close()

    if row and row[0] is not None:
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def get_cash():
    with sqlite3.connect(SIM_DB) as conn:
        c = conn.cursor()
        c.execute("SELECT cash FROM state WHERE id = 1")
        row = c.fetchone()
        return row[0] if row else 0.0

def get_previous_close(symbol):
    """
    (Optional) If you ever need yesterday's close,
    you could implement this with yfinance as well. 
    We only need today's open for our logic below.
    """
    # For now, we don't use this for "Day Gain"—we use today's open instead.
    return 0.0


def get_today_open(symbol):
    """
    Fetch today's opening price for `symbol` via yfinance.
    We'll download just the last 1 day of data at 1d resolution,
    then pull the 'Open' column for today.
    If we can't get it, return None.
    """
    try:
        # period="1d" with interval="1d" returns a single-row DataFrame for today
        df = yf.download(symbol, period="1d", interval="1d", progress=False)
        if df is None or df.empty:
            return None
        # The index is today's date; .iloc[0]['Open'] is the open price
        today_open = df["Open"].iloc[0]
        return float(today_open)
    except Exception:
        return None


def get_first_buy_timestamp(symbol):
    """
    Look in the 'simulation_trades' (or however you named your trades table)
    for the earliest BUY for this symbol. Return a datetime object.
    If no BUYs exist, return None.
    """
    conn = sqlite3.connect(SIM_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT trade_time 
          FROM simulation_trades 
         WHERE symbol = ? AND action = 'BUY'
         ORDER BY trade_time ASC
         LIMIT 1
    """, (symbol,))
    row = c.fetchone()
    conn.close()

    if not row or row["trade_time"] is None:
        return None

    # Assuming you stored trade_time as a text like "YYYY-MM-DD HH:MM:SS"
    ts_str = row["trade_time"]
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

import sqlite3
from datetime import datetime

SIM_DB = "simulation.db"   # adjust if your DB file has a different name or path

def buy_stock(symbol, quantity, price):
    """
    Record a BUY trade in the simulation database and update holdings.
    - Inserts a new row into `simulation_trades` with action='BUY'
    - Increases (or creates) the row in `holdings` for this symbol.
    """
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()

    # 1) Insert a new BUY trade
    trade_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO simulation_trades (symbol, action, price, qty, trade_time, pnl)
        VALUES (?, 'BUY', ?, ?, ?, NULL)
    """, (symbol, price, quantity, trade_time))

    # 2) Update holdings table: if symbol exists, adjust qty and average cost; otherwise insert new
    #    We assume `holdings` has columns: symbol (TEXT PRIMARY KEY), qty (REAL), avg_cost (REAL)
    c.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,))
    row = c.fetchone()
    if row:
        old_qty, old_avg = row
        # new total quantity
        new_qty = old_qty + quantity
        # new average cost = (old_avg*old_qty + price*quantity) / new_qty
        new_avg = ((old_avg * old_qty) + (price * quantity)) / new_qty
        c.execute("""
            UPDATE holdings
               SET qty = ?, avg_cost = ?
             WHERE symbol = ?
        """, (new_qty, new_avg, symbol))
    else:
        # no existing row, so insert brand-new holding
        c.execute("""
            INSERT INTO holdings (symbol, qty, avg_cost)
            VALUES (?, ?, ?)
        """, (symbol, quantity, price))

    conn.commit()
    conn.close()

def get_holdings():
    """
    Return a list of dicts for each holding with its live last_price + computed gains.
    All numeric fields are floats.  
    Each dict has keys:
      'symbol', 'qty', 'avg_cost', 'last_price',
      'day_gain', 'total_gain', 'value'
    """
    holdings = []
    today = date.today()   # today’s date (to compare to buy timestamp)

    with sqlite3.connect(SIM_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT symbol, qty, avg_cost FROM holdings").fetchall()
        for row in rows:
            symbol = row["symbol"]
            qty = float(row["qty"])
            avg_cost = float(row["avg_cost"])

            # 1) Get the real-time (last) price; cast it to float
            raw_price = get_realtime_price(symbol)
            try:
                last_price = float(raw_price)
            except (TypeError, ValueError):
                last_price = 0.0

            # 2) Determine whether our first BUY for this symbol was before today's open
            first_buy_ts = get_first_buy_timestamp(symbol)
            held_at_open = False
            if first_buy_ts:
                held_at_open = (first_buy_ts.date() < today) or (first_buy_ts.date() == today and first_buy_ts.time() < datetime.strptime("09:30:00", "%H:%M:%S").time())
                # In other words: if the first BUY was on an earlier date, OR if it was today but before 9:30 AM, we consider "held_at_open=True".

            # 3) Fetch today's actual open price if needed
            if held_at_open:
                # We only fetch yfinance once per symbol per call
                open_price = get_today_open(symbol) or avg_cost
                # If we can't fetch today's open, we fallback to avg_cost (so day_gain = 0)
            else:
                # Bought after the market opened today, so open_for_day = purchase price
                open_price = avg_cost

            # 4) Compute Day Gain: (last_price - open_price) * qty
            day_gain = (last_price - open_price) * qty

            # 5) Compute Total Gain: (last_price - avg_cost) * qty
            total_gain = (last_price - avg_cost) * qty

            # 6) Current value (market value) = last_price * qty
            value = last_price * qty

            holdings.append({
                "symbol": symbol,
                "qty": qty,
                "avg_cost": avg_cost,
                "last_price": last_price,
                "day_gain": day_gain,
                "total_gain": total_gain,
                "value": value
            })

    return holdings
