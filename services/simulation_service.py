import sqlite3
from config import Config
from datetime import datetime

DB_PATH = Config.SIM_DB

def init_db():
    """Initialize the trades table."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            action TEXT,
            quantity INTEGER,
            price REAL
        )
    """)
    conn.commit()
    conn.close()

def reset_state():
    """Clear all trades to reset simulation to starting cash."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM trades")
    conn.commit()
    conn.close()

def get_simulation_state():
    """
    Compute current cash and holdings from trade history.
    Includes formatted timestamps and P/L for sell trades.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, symbol, action, quantity, price FROM trades ORDER BY id")
    rows = c.fetchall()
    conn.close()

    cash = Config.STARTING_CASH
    holdings = {}
    trades = []

    for tid, ts, symbol, action, qty, price in rows:
        # Format timestamp as HH:MM:SS
        try:
            dt = datetime.fromisoformat(ts)
            ts_fmt = dt.strftime('%H:%M:%S')
        except:
            ts_fmt = ts

        sym = symbol.upper()
        pnl = None
        if action.upper() == "SELL":
            prev = holdings.get(sym)
            if prev:
                avg_price = prev["avg_price"]
                pnl = qty * (price - avg_price)
            else:
                pnl = 0.0

        trades.append({
            "id": tid,
            "timestamp": ts_fmt,
            "symbol": sym,
            "action": action.upper(),
            "quantity": qty,
            "price": price,
            "pnl": pnl
        })

        # Apply trade to cash and holdings
        if action.upper() == "BUY":
            cash -= qty * price
            if sym in holdings:
                prev = holdings[sym]
                total_qty = prev["quantity"] + qty
                prev["avg_price"] = ((prev["avg_price"] * prev["quantity"]) + (price * qty)) / total_qty
                prev["quantity"] = total_qty
            else:
                holdings[sym] = {"quantity": qty, "avg_price": price}
        elif action.upper() == "SELL":
            cash += qty * price
            if sym in holdings:
                prev = holdings[sym]
                new_qty = prev["quantity"] - qty
                if new_qty > 0:
                    prev["quantity"] = new_qty
                else:
                    del holdings[sym]

    holdings_list = [(sym, data["quantity"], data["avg_price"]) for sym, data in holdings.items()]
    return {"cash": cash, "holdings": holdings_list, "trades": trades}

def process_trade(symbol, quantity, price):
    """Record a BUY trade."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO trades (timestamp, symbol, action, quantity, price) VALUES (?, ?, ?, ?, ?)",
        (now, symbol.upper(), "BUY", quantity, price)
    )
    conn.commit()
    conn.close()

def process_sell(symbol, quantity, price):
    """Record a SELL trade."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO trades (timestamp, symbol, action, quantity, price) VALUES (?, ?, ?, ?, ?)",
        (now, symbol.upper(), "SELL", quantity, price)
    )
    conn.commit()
    conn.close()

def delete_holding(symbol):
    """Remove all trades for a symbol."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM trades WHERE symbol=?", (symbol.upper(),))
    conn.commit()
    conn.close()
