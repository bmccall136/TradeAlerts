import sqlite3
from datetime import datetime
import yfinance as yf
from pathlib import Path

SIM_DB = str(Path(__file__).resolve().parent.parent / "simulation.db")

def _connect():
    return sqlite3.connect(SIM_DB, detect_types=sqlite3.PARSE_DECLTYPES)

def _connect():
    return sqlite3.connect(SIM_DB, detect_types=sqlite3.PARSE_DECLTYPES)

# … rest of get_holdings(), buy_stock(), sell_stock(), etc. …

def get_cash():
    """Return the single row `state.cash` (or 0.0 if missing)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_realized_pl():
    """Return state.realized_pl (or 0.0)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT realized_pl FROM state WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_trades():
    """
    Return a list of all trades (newest first).
    Each trade is a dict with keys:
      id, symbol, action, price, qty, trade_time, pnl
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
      SELECT id, symbol, action, price, qty, trade_time, pnl
        FROM simulation_trades
       ORDER BY id DESC;
    """)
    rows = cur.fetchall()
    conn.close()

    trades = []
    for r in rows:
        trades.append({
            "id":         r["id"],
            "symbol":     r["symbol"],
            "action":     r["action"],
            "price":      float(r["price"]),
            "qty":        int(r["qty"]),
            "trade_time": r["trade_time"],
            "pnl":        float(r["pnl"]) if r["pnl"] is not None else None
        })
    return trades


def get_holdings():
    """
    Return a list of holdings dictionaries. Each one has keys matching the template:
      symbol, qty, price_paid, last_price, change, change_pct, day_gain, total_gain, value
    """
    holdings = []
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1) Grab symbol, qty, avg_cost from the SQLite table
    cur.execute("SELECT symbol, qty, avg_cost FROM holdings;")
    rows = cur.fetchall()
    conn.close()

    for r in rows:
        symbol   = r["symbol"]
        qty      = int(r["qty"])
        avg_cost = float(r["avg_cost"])

        # 2) Fetch the live price (using yfinance); if it fails, fall back to avg_cost
        try:
            df = yf.download(symbol, period="1d", interval="1d", progress=False)
            last_price = float(df["Open"].iloc[0]) if not df.empty else avg_cost
        except Exception:
            last_price = avg_cost

        # 3) Calculate change from cost and percent
        change_amount  = last_price - avg_cost
        change_pct     = (change_amount / avg_cost * 100) if avg_cost != 0 else 0.0

        # 4) Calculate day_gain and total_gain
        #    (Here we approximate day_gain = total_gain since we don't track previous_close separately)
        day_gain       = change_amount * qty
        total_gain     = change_amount * qty
        value          = last_price * qty

        # 5) Build the exact dict your template needs:
        holdings.append({
            "symbol":      symbol,
            "qty":         qty,
            "price_paid":  avg_cost,        # TEMPLATE uses {{ h.price_paid }}
            "last_price":  last_price,      # TEMPLATE uses {{ h.last_price }}
            "change":      change_amount,   # TEMPLATE uses {{ h.change }}
            "change_pct":  change_pct,      # TEMPLATE uses {{ h.change_pct }}
            "day_gain":    day_gain,        # TEMPLATE uses {{ h.day_gain }}
            "total_gain":  total_gain,      # TEMPLATE uses {{ h.total_gain }}
            "value":       value            # TEMPLATE uses {{ h.value }}
        })

    return holdings


def buy_stock(symbol: str, quantity: int, price: float):
    """
    1) Insert a new BUY into simulation_trades (pnl=NULL)
    2) Deduct cash = price * quantity from state.cash
    3) Add or update holdings (recompute avg_cost)
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    cur = conn.cursor()

    total_cost = price * quantity

    # 1) Check current cash
    cur.execute("SELECT cash FROM state WHERE id = 1;")
    row = cur.fetchone()
    if not row or float(row[0]) < total_cost:
        conn.close()
        raise ValueError("Insufficient cash to buy.")

    # 2) Insert trade
    cur.execute(
        "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time, pnl) "
        "VALUES (?, 'BUY', ?, ?, ?, NULL);",
        (symbol, price, quantity, timestamp)
    )

    # 3) Subtract cash
    new_cash = float(row[0]) - total_cost
    cur.execute("UPDATE state SET cash = ? WHERE id = 1;", (new_cash,))

    # 4) Update / insert holding
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?;", (symbol,))
    hold = cur.fetchone()
    if hold:
        old_qty, old_avg = int(hold[0]), float(hold[1])
        new_qty = old_qty + quantity
        new_avg = ((old_avg * old_qty) + (price * quantity)) / new_qty
        cur.execute(
            "UPDATE holdings SET qty = ?, avg_cost = ?, last_price = ? WHERE symbol = ?;",
            (new_qty, new_avg, price, symbol)
        )
    else:
        cur.execute(
            "INSERT INTO holdings (symbol, qty, avg_cost, last_price) VALUES (?, ?, ?, ?);",
            (symbol, quantity, price, price)
        )

    conn.commit()
    conn.close()


def sell_stock(symbol: str, quantity: int, price: float):
    """
    1) Lookup existing holding; if not enough qty, error out.
    2) Compute realized_pl = (price - avg_cost) * quantity.
    3) Insert SELL into simulation_trades with pnl.
    4) Subtract that qty from holdings (or delete if qty→0).
    5) Add proceeds = price * quantity back into state.cash.
    6) Add realized_pl to state.realized_pl.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    cur = conn.cursor()

    # 1) Get current cash + realized_pl
    cur.execute("SELECT cash, realized_pl FROM state WHERE id = 1;")
    state_row = cur.fetchone()
    if not state_row:
        conn.close()
        raise Exception("No state row found.")
    cash_now, realized = float(state_row[0]), float(state_row[1])

    # 2) Get holding
    cur.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?;", (symbol,))
    hold = cur.fetchone()
    if not hold:
        conn.close()
        raise Exception(f"No holdings for {symbol}.")
    old_qty, avg_cost = int(hold[0]), float(hold[1])
    if quantity > old_qty:
        conn.close()
        raise Exception(f"Cannot sell {quantity} {symbol}; only {old_qty} held.")

    # 3) Compute realized P/L
    proceeds     = price * quantity
    realized_pl  = (price - avg_cost) * quantity

    # 4) Insert SELL trade
    cur.execute(
        "INSERT INTO simulation_trades (symbol, action, price, qty, trade_time, pnl) "
        "VALUES (?, 'SELL', ?, ?, ?, ?);",
        (symbol, price, quantity, timestamp, realized_pl)
    )

    # 5) Update holdings
    new_qty = old_qty - quantity
    if new_qty > 0:
        cur.execute(
            "UPDATE holdings SET qty = ?, last_price = ? WHERE symbol = ?;",
            (new_qty, price, symbol)
        )
    else:
        cur.execute("DELETE FROM holdings WHERE symbol = ?;", (symbol,))

    # 6) Update cash + realized_pl in state
    new_cash     = cash_now + proceeds
    new_realized = realized + realized_pl
    cur.execute(
        "UPDATE state SET cash = ?, realized_pl = ? WHERE id = 1;",
        (new_cash, new_realized)
    )

    conn.commit()
    conn.close()
