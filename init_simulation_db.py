import sqlite3
import os

# Path to your simulation database file; adjust as needed
SIM_DB = os.path.join(os.getcwd(), 'simulation.db')


def init_simulation_db():
    print("🔧 initializing simulation.db schema…")
    """
    Initialize the simulation database schema.
    Drops existing tables if they exist and recreates:
    - state: stores simulation key/value pairs (e.g., cash)
    - holdings: tracks current positions
    - simulation_trades: logs each buy/sell with timestamp
    """
    conn = sqlite3.connect(SIM_DB)
    cur = conn.cursor()

    # Drop old tables
    cur.execute("DROP TABLE IF EXISTS state")
    cur.execute("DROP TABLE IF EXISTS holdings")
    # Ensure old trades tables are cleared
    cur.execute("DROP TABLE IF EXISTS simulation_trades")
    cur.execute("DROP TABLE IF EXISTS trades")

    # 1) State table for storing simulation-wide values (e.g., cash)
    cur.execute("""
        CREATE TABLE state (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)

    # 2) Holdings table: one row per symbol in portfolio
    cur.execute("""
        CREATE TABLE holdings (
            symbol TEXT PRIMARY KEY,
            qty INTEGER NOT NULL,
            price_paid REAL NOT NULL
        )
    """)

    # 3) Simulation trades table: logs each trade event
    cur.execute("""
        CREATE TABLE simulation_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            qty INTEGER NOT NULL,
            trade_time TEXT NOT NULL,
            pnl REAL
        )
    """)

    conn.commit()
    conn.close()


# Run on import to ensure schema exists
if __name__ == '__main__':
    init_simulation_db()
