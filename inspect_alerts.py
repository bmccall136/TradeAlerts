import sqlite3
from datetime import date

# Connect to your alerts database
conn = sqlite3.connect('alerts.db', detect_types=sqlite3.PARSE_DECLTYPES)
c = conn.cursor()

# Show the 10 most recent rows regardless of date
print("=== Last 10 alerts (all dates) ===")
for row in c.execute("SELECT symbol, signal, price, vwap, timestamp FROM alerts ORDER BY timestamp DESC LIMIT 10"):
    print(row)

# Show only today’s rows
today = date.today().isoformat()
print(f"\n=== Alerts WHERE timestamp LIKE '{today}%' ===")
for row in c.execute("SELECT symbol, signal, price, vwap, timestamp FROM alerts WHERE timestamp LIKE ? ORDER BY timestamp DESC", (today+'%',)):
    print(row)

conn.close()
