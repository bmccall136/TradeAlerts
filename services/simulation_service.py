# File: services/simulation_service.py

import sqlite3
from services.market_service import get_realtime_price
from datetime import datetime
import yfinance as yf

# Make sure this matches exactly where your SQLite file lives:
SIM_DB = 'C:/TradeAlerts/simulation.db'

import yfinance as yf

def get_previous_close(symbol):
    """
    Return the previous trading session’s close price for `symbol`.
    Uses yfinance to grab the last two daily bars and returns yesterday’s close.
    If something goes wrong, returns 0.0.
    """
    try:
        # Request 2 days of daily data; the older bar is “yesterday”
        df = yf.download(symbol, period="2d", interval="1d", progress=False)
        if len(df) >= 2:
            val = df['Close'].iloc[-2]
            return float(val.item()) if hasattr(val, "item") else float(val)
        else:
            return 0.0
    except Exception:
        return 0.0

def build_holdings_list():
    holdings = []
    with sqlite3.connect(SIM_DB) as conn:
        rows = conn.execute("SELECT symbol, qty, avg_cost FROM holdings").fetchall()
        for symbol, qty, avg_cost in rows:
            # 1) fetch the current (realtime) market price
            last_price = get_realtime_price(symbol)
            print(f"[SIM HOLDINGS] {symbol}: last_price={last_price}")

            # 2) fetch “yesterday’s close” instead of zero
            prev_price = get_previous_close(symbol)
            if prev_price > 0:
                change = last_price - prev_price
                change_percent = (change / prev_price) * 100
            else:
                # if we couldn’t fetch a real previous close, just default to zero
                change = 0.0
                change_percent = 0.0

            # 3) Build whatever dict/tuple/list you need for rendering
            holdings.append({
                'symbol': symbol,
                'qty': qty,
                'avg_cost': avg_cost,
                'last_price': last_price,
                'prev_price': prev_price,
                'change': change,
                'change_percent': change_percent
            })

    return holdings

def get_cash():
    """
    Return the current cash_balance from the 'account' table (or 0.0 if missing).
    """
    with sqlite3.connect(SIM_DB) as conn:
        row = conn.execute("SELECT cash_balance FROM account WHERE id = 1").fetchone()
        return float(row[0]) if row else 0.0


def get_realized_pl():
    """
    Return the current realized P/L stored in state.realized_pl (or 0.0 if missing).
    """
    with sqlite3.connect(SIM_DB) as conn:
        row = conn.execute("SELECT realized_pl FROM state WHERE id = 1").fetchone()
        return float(row[0]) if row else 0.0


def get_holdings():
    """
    Return a list of dicts for each holding with its live last_price + computed gains.
    All numeric fields are raw floats (no formatting).
    Each dict has these keys:
      'symbol', 'qty', 'avg_cost', 'last_price',
      'change', 'change_percent', 'value',
      'day_gain', 'total_gain', 'total_gain_percent'
    """
    holdings = []
    with sqlite3.connect(SIM_DB) as conn:
        rows = conn.execute("SELECT symbol, qty, avg_cost FROM holdings").fetchall()
        for symbol, qty, avg_cost in rows:
            # 1) fetch the current (realtime) market price
            last_price = get_realtime_price(symbol)
            print(f"[SIM HOLDINGS] {symbol}: last_price={last_price}")

            # 2) fetch yesterday’s close instead of hard‐coding zero
            prev_price = get_previous_close(symbol)
            if prev_price > 0:
                change = last_price - prev_price
                change_percent = (change / prev_price) * 100
            else:
                change = 0.0
                change_percent = 0.0

            # 3) Compute “paper” gains
            value = float(qty) * last_price
            day_gain = change * qty
            total_gain = (last_price - avg_cost) * qty
            total_gain_percent = ((last_price - avg_cost) / avg_cost * 100) if avg_cost else 0.0

            holdings.append({
                'symbol': symbol,
                'qty': qty,
                'avg_cost': avg_cost,
                'last_price': last_price,
                'change': change,
                'change_percent': change_percent,
                'value': value,
                'day_gain': day_gain,
                'total_gain': total_gain,
                'total_gain_percent': total_gain_percent
            })
    return holdings



def get_trades():
    """
    Return a list of dicts for each trade (newest first).  
    Each dict has keys: 'timestamp', 'symbol', 'action', 'quantity', 'price', 'pl'.
    """
    trades = []
    with sqlite3.connect(SIM_DB) as conn:
        rows = conn.execute("""
            SELECT timestamp, symbol, action, quantity, price, pl
            FROM trades
            ORDER BY id DESC
        """).fetchall()

        for ts, sym, action, qty, price, pl in rows:
            pl_val = float(pl) if pl is not None else None
            trades.append({
                'timestamp': ts,
                'symbol': sym,
                'action': action,
                'quantity': qty,
                'price': price,
                'pl': pl_val
            })
    return trades


def buy_stock(symbol, qty, price):
    """
    1) Subtract (price * qty) from account.cash_balance.
    2) Insert or update `holdings` for that symbol (re‐compute avg_cost if it already exists).
    3) Insert a new BUY row into `trades` with pl=NULL.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    total_cost = float(price) * int(qty)

    conn = sqlite3.connect(SIM_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) Verify enough cash in account
    row = cur.execute("SELECT cash_balance FROM account WHERE id = 1").fetchone()
    cash = float(row['cash_balance']) if row else 0.0
    if total_cost > cash:
        conn.close()
        raise ValueError("Not enough cash to complete purchase.")

    # 2) Insert or update into holdings
    existing = cur.execute(
        "SELECT qty, avg_cost FROM holdings WHERE symbol = ?",
        (symbol,)
    ).fetchone()

    if existing:
        old_qty = int(existing['qty'])
        old_cost = float(existing['avg_cost'])
        new_qty = old_qty + qty
        # Weighted average cost:
        new_avg_cost = ((old_cost * old_qty) + (float(price) * qty)) / new_qty
        cur.execute(
            "UPDATE holdings SET qty = ?, avg_cost = ?, last_price = ? WHERE symbol = ?",
            (new_qty, new_avg_cost, price, symbol)
        )
    else:
        # New holding record:
        cur.execute(
            "INSERT INTO holdings (symbol, qty, avg_cost, last_price) VALUES (?, ?, ?, ?)",
            (symbol, qty, price, price)
        )

    # 3) Subtract from cash balance
    new_cash = cash - total_cost
    cur.execute(
        "UPDATE account SET cash_balance = ? WHERE id = 1",
        (new_cash,)
    )

    # 4) Insert BUY into trades (pl = NULL)
    cur.execute(
        """
        INSERT INTO trades (timestamp, symbol, action, quantity, price, pl)
        VALUES (?, ?, 'BUY', ?, ?, NULL)
        """,
        (timestamp, symbol, qty, price)
    )

    conn.commit()
    conn.close()


def sell_stock(symbol, qty, price):
    """
    1) Look up existing holding (symbol, qty, avg_cost). Error if not enough.
    2) Compute proceeds = price * qty, realized_pl = (price - avg_cost) * qty.
    3) Subtract that qty from holdings (or delete if qty → 0).
    4) Add proceeds to account.cash_balance.
    5) Accumulate realized_pl into state.realized_pl.
    6) Insert a new row into trades with action='SELL' and pl=realized_pl.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    conn = sqlite3.connect(SIM_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) Fetch current cash_balance
    acct_row = cur.execute("SELECT cash_balance FROM account WHERE id = 1").fetchone()
    if not acct_row:
        conn.close()
        raise Exception("Account row not found in `account`.")
    cash = float(acct_row['cash_balance'])

    # 2) Fetch existing holding
    hold_row = cur.execute(
        "SELECT qty, avg_cost FROM holdings WHERE symbol = ?",
        (symbol,)
    ).fetchone()
    if not hold_row:
        conn.close()
        raise Exception(f"No holdings found for symbol '{symbol}'.")

    existing_qty = int(hold_row['qty'])
    avg_cost = float(hold_row['avg_cost'])
    if qty > existing_qty:
        conn.close()
        raise Exception(f"Cannot sell {qty} of {symbol}; only {existing_qty} held.")

    # 3) Compute proceeds and realized profits
    proceeds = float(price) * int(qty)
    realized_pl = (float(price) - avg_cost) * int(qty)

    # 4) Update or delete holdings row
    new_qty = existing_qty - qty
    if new_qty > 0:
        cur.execute(
            "UPDATE holdings SET qty = ?, last_price = ? WHERE symbol = ?",
            (new_qty, price, symbol)
        )
    else:
        cur.execute(
            "DELETE FROM holdings WHERE symbol = ?",
            (symbol,)
        )

    # 5) Add proceeds back into cash_balance
    new_cash = cash + proceeds
    cur.execute(
        "UPDATE account SET cash_balance = ? WHERE id = 1",
        (new_cash,)
    )

    # 6) Accumulate realized_pl into state.realized_pl
    state_row = cur.execute("SELECT realized_pl FROM state WHERE id = 1").fetchone()
    if not state_row:
        # If the `state` table is empty, insert initial row:
        cur.execute(
            "INSERT INTO state (id, realized_pl) VALUES (1, ?)",
            (realized_pl,)
        )
    else:
        current_realized = float(state_row['realized_pl'] or 0.0)
        updated_realized = current_realized + realized_pl
        cur.execute(
            "UPDATE state SET realized_pl = ? WHERE id = 1",
            (updated_realized,)
        )

    # 7) Insert a new SELL row into trades (pl = realized_pl)
    cur.execute(
        """
        INSERT INTO trades (timestamp, symbol, action, quantity, price, pl)
        VALUES (?, ?, 'SELL', ?, ?, ?)
        """,
        (timestamp, symbol, qty, price, realized_pl)
    )

    conn.commit()
    conn.close()
