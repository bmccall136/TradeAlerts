import sqlite3

conn = sqlite3.connect('alerts.db')
try:
    conn.execute("ALTER TABLE alerts ADD COLUMN name TEXT")
    print("Added 'name' column to alerts table.")
except sqlite3.OperationalError:
    print("Column already exists or table missing. Check manually if needed.")
conn.close()
