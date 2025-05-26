import sqlite3

conn = sqlite3.connect('alerts.db')
c = conn.cursor()
c.execute('DROP TABLE IF EXISTS alerts')
c.execute('''
    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        alert_type TEXT,
        price REAL,
        triggers TEXT,
        sparkline TEXT,
        timestamp TEXT,
        name TEXT,
        cleared INTEGER DEFAULT 0
    )
''')
conn.commit()
conn.close()
print("alerts table recreated.")
