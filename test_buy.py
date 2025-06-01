import sqlite3
from datetime import datetime

symbol = "AAPL"
qty = 5
price = 100.00
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

conn = sqlite3.connect("simulation.db")
cursor = conn.cursor()

# Check if the holding already exists
cursor.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,))
row = cursor.fetchone()

if row:
    old_qty, old_cost = row
    new_qty = old_qty + qty
    new_avg = ((old_cost * old_qty) + (price * qty)) / new_qty
    cursor.execute("UPDATE holdings SET qty = ?, avg_cost = ? WHERE symbol = ?", (new_qty, new_avg, symbol))
else:
    cursor.execute("INSERT INTO holdings (symbol, qty, avg_cost) VALUES (?, ?, ?)", (symbol, qty, price))

# Insert trade history
cursor.execute("""
    INSERT INTO trade_history (timestamp, symbol, action, qty, price)
    VALUES (?, ?, 'BUY', ?, ?)
""", (timestamp, symbol, qty, price))

# Deduct from account
cursor.execute("UPDATE account SET cash_balance = cash_balance - ? WHERE id = 1", (price * qty,))

conn.commit()
conn.close()
print(f"✅ Test buy executed: {qty} shares of {symbol} at ${price}")
