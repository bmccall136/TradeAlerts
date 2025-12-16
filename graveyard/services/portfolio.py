import sqlite3

from .settings_schema import SIM_DB_PATH


def get_holdings():
    """
    Returns a list of (symbol, qty, avg_cost) for all open positions
    in your simulation database.
    """
    conn = sqlite3.connect(SIM_DB_PATH)
    cur = conn.cursor()
    # Replace 'positions' and columns with whatever schema you actually use
    cur.execute("SELECT symbol, qty, avg_price FROM positions")
    rows = cur.fetchall()
    conn.close()
    return rows
