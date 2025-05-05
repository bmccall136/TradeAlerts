
import sqlite3
import os

DB = 'simulation_state.db'

def init_sim():
    if not os.path.exists(DB):
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("CREATE TABLE positions (symbol TEXT PRIMARY KEY, quantity REAL, price REAL)")
        conn.commit()
        conn.close()

def get_open_positions():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM positions")
    rows = c.fetchall()
    conn.close()
    return rows

def is_held(symbol):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM positions WHERE symbol=?", (symbol,))
    result = c.fetchone()
    conn.close()
    return result is not None
