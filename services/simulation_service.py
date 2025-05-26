import sqlite3

SIM_DB = 'simulation.db'

def get_holdings():
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings")
    rows = c.fetchall()
    conn.close()
    holdings = []
    for row in rows:
        holdings.append({
            'symbol': row[0],
            'qty': row[1],
            'avg_cost': row[2],
            'last_price': row[3],
            'unreal': (row[3] - row[2]) * row[1]
        })
    return holdings

def get_cash():
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("SELECT cash_balance FROM account LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_holding(symbol, qty, avg_cost, last_price):
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO holdings (symbol, qty, avg_cost, last_price)
        VALUES (?, ?, ?, ?)
    """, (symbol, qty, avg_cost, last_price))
    conn.commit()
    conn.close()

def update_cash(new_balance):
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("UPDATE account SET cash_balance = ?", (new_balance,))
    conn.commit()
    conn.close()

def add_cash(initial_balance=10000):
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("INSERT INTO account (cash_balance) VALUES (?)", (initial_balance,))
    conn.commit()
    conn.close()
