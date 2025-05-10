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
            quantity REAL,
            price REAL
        )
    """)
    conn.commit()
    conn.close()

def reset_state():
    """Delete all trades to reset the simulation."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM trades")
    conn.commit()
    conn.close()

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

def delete_holding(symbol):
    """Remove all trades for one symbol."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM trades WHERE symbol=?", (symbol.upper(),))
    conn.commit()
    conn.close()

def get_simulation_state():
    """
    Compute current cash and holdings from trade history.
    Returns dict with:
      - cash: remaining cash
      - holdings: list of tuples (symbol, quantity, avg_price)
      - trades: list of trade dicts with id, timestamp, symbol, action, quantity, price
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
        sym = symbol.upper()
        trades.append({
            "id": tid,
            "timestamp": ts,
            "symbol": sym,
            "action": action,
            "quantity": qty,
            "price": price
        })
        if action.upper() == "BUY":
            cash -= qty * price
            if sym in holdings:
                prev = holdings[sym]
                total_qty = prev["quantity"] + qty
                prev["avg_price"] = ((prev["avg_price"] * prev["quantity"]) + (price * qty)) / total_qty
                prev["quantity"] = total_qty
            else:
                holdings[sym] = {"quantity": qty, "avg_price": price}

    holdings_list = [(sym, data["quantity"], data["avg_price"]) for sym, data in holdings.items()]

    return {
        "cash": cash,
        "holdings": holdings_list,
        "trades": trades
    }
