import sqlite3
from config import Config

DB_PATH = Config.SIM_DB

def init_db():
    """
    Create simulation tables if they do not exist.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Migrate old trades table if 'id' column is missing
    cursor.execute("PRAGMA table_info(trades)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'id' not in cols:
        cursor.execute("ALTER TABLE trades RENAME TO old_trades")
        cursor.execute("""CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            action TEXT,
            quantity REAL,
            price REAL
        )""")
        cursor.execute("INSERT INTO trades (timestamp, symbol, action, quantity, price) SELECT timestamp, symbol, action, quantity, price FROM old_trades")
        cursor.execute("DROP TABLE old_trades")

    cursor.execute("""CREATE TABLE IF NOT EXISTS state (cash REAL);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS holdings (symbol TEXT PRIMARY KEY, quantity REAL, avg_price REAL);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        symbol TEXT,
        action TEXT,
        quantity REAL,
        price REAL
    );""")
    # Ensure initial state row
    cursor.execute("""INSERT OR IGNORE INTO state (rowid, cash) VALUES (1, ?);""", (Config.STARTING_CASH,))
    conn.commit()
    conn.close()

def reset_state(starting_cash=None):
    if starting_cash is None:
        starting_cash = Config.STARTING_CASH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE state SET cash=?", (starting_cash,))
    cursor.execute("DELETE FROM holdings;")
    conn.commit()
    conn.close()

def _record_trade(timestamp, symbol, action, quantity, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO trades (timestamp, symbol, action, quantity, price)
                      VALUES (?, ?, ?, ?, ?)""", (timestamp, symbol, action, quantity, price))
    conn.commit()
    conn.close()

def update_state_for_trade(action, symbol, quantity, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if action.upper() == 'BUY':
        # Deduct cash
        cursor.execute("UPDATE state SET cash = cash - ?", (quantity * price,))
        # Update holdings
        cursor.execute("SELECT quantity, avg_price FROM holdings WHERE symbol=?", (symbol,))
        row = cursor.fetchone()
        if row:
            old_q, old_p = row
            new_q = old_q + quantity
            new_avg = ((old_q * old_p) + (quantity * price)) / new_q
            cursor.execute("UPDATE holdings SET quantity=?, avg_price=? WHERE symbol=?", (new_q, new_avg, symbol))
        else:
            cursor.execute("INSERT INTO holdings (symbol, quantity, avg_price) VALUES (?, ?, ?)", (symbol, quantity, price))
    elif action.upper() == 'SELL':
        # Increase cash
        cursor.execute("UPDATE state SET cash = cash + ?", (quantity * price,))
        # Update holdings
        cursor.execute("SELECT quantity, avg_price FROM holdings WHERE symbol=?", (symbol,))
        row = cursor.fetchone()
        if row:
            old_q, old_p = row
            new_q = max(old_q - quantity, 0)
            if new_q > 0:
                cursor.execute("UPDATE holdings SET quantity=? WHERE symbol=?", (new_q, symbol))
            else:
                cursor.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()

def process_trade(timestamp, symbol, action, quantity, price):
    """
    Process a trade: update state, holdings, and record the trade.
    """
    init_db()
    update_state_for_trade(action, symbol, quantity, price)
    _record_trade(timestamp, symbol, action, quantity, price)

def recompute_state():
    """
    Reset state and reapply all trades to rebuild holdings and state.
    """
    init_db()
    # Reset to starting cash and clear holdings
    reset_state(Config.STARTING_CASH)
    # Reapply trades in order
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, symbol, action, quantity, price FROM trades ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    for timestamp, symbol, action, quantity, price in rows:
        update_state_for_trade(action, symbol, quantity, price)

def delete_trade(trade_id):
    """
    Remove a trade and recompute state.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    conn.commit()
    conn.close()
    recompute_state()


def get_simulation_state():
    """
    Retrieve the current simulation state: cash, holdings, trade history.
    Returns dict with cash, holdings list of (sym,q,avg), trades list of dicts including id.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash FROM state;")
    cash = cursor.fetchone()[0]
    cursor.execute("SELECT symbol, quantity, avg_price FROM holdings;")
    holdings = cursor.fetchall()
    # Try to select with id; if id column missing, fallback to rowid
    try:
        cursor.execute("SELECT id, timestamp, symbol, action, quantity, price FROM trades;")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        cursor.execute("SELECT rowid AS id, timestamp, symbol, action, quantity, price FROM trades;")
        rows = cursor.fetchall()
    conn.close()
    # Build trades list of dicts
    trades = []
    for tid, timestamp, symbol, action, quantity, price in rows:
        trades.append({
            'id': tid,
            'timestamp': timestamp,
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'price': price
        })
    return {
        'cash': cash,
        'holdings': holdings,
        'trades': trades
    }

    """
    Retrieve the current simulation state: cash, holdings, trade history.
    Returns dict with cash, holdings list of (sym,q,avg), trades list of (id,t,s,a,q,p).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash FROM state;")
    cash = cursor.fetchone()[0]
    cursor.execute("SELECT symbol, quantity, avg_price FROM holdings;")
    holdings = cursor.fetchall()
    cursor.execute("SELECT id, timestamp, symbol, action, quantity, price FROM trades;")
    trades = cursor.fetchall()
    conn.close()
    return {
        'cash': cash,
        'holdings': holdings,
        'trades': trades
    }


def delete_holding(symbol):
    """
    Delete all trades for symbol and recompute state.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()
    recompute_state()
