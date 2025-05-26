import sqlite3

conn = sqlite3.connect("simulation.db")
conn.execute("""
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cash_balance REAL
)
""")
# Initialize with starting cash if table is empty
cur = conn.execute("SELECT COUNT(*) FROM account")
if cur.fetchone()[0] == 0:
    conn.execute("INSERT INTO account (cash_balance) VALUES (?)", (10000.00,))
conn.commit()
conn.close()
print("✅ Table 'account' created and initialized in simulation.db!")
