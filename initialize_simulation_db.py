
import sqlite3

db_path = 'simulation.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create simulation_state table
cursor.execute('''
CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cash REAL NOT NULL,
    open_value REAL NOT NULL,
    realized_pl REAL NOT NULL
)
''')

# Create simulation_trades table
cursor.execute('''
CREATE TABLE IF NOT EXISTS simulation_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL
)
''')

# Initialize starting state if empty
cursor.execute('SELECT COUNT(*) FROM simulation_state')
if cursor.fetchone()[0] == 0:
    cursor.execute('INSERT INTO simulation_state (cash, open_value, realized_pl) VALUES (?, ?, ?)', (5000.0, 0.0, 0.0))

conn.commit()
conn.close()

print('✅ Simulation database initialized successfully!')
