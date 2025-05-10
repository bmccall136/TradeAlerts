#!/usr/bin/env python3
"""
rebuild_simulation_db.py

Drops and recreates the simulation database tables,
then seeds the initial cash balance.
Usage: python rebuild_simulation_db.py [db_file]
If no db_file is provided, defaults to 'simulation.db'.
"""
import sqlite3
import sys

DB_FILE = sys.argv[1] if len(sys.argv) > 1 else 'simulation.db'
INITIAL_CASH = 10000.0

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Drop existing tables
c.execute('DROP TABLE IF EXISTS simulation_state')
c.execute('DROP TABLE IF EXISTS simulation_transactions')

# Create tables
c.execute('''
CREATE TABLE simulation_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cash REAL NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

c.execute('''
CREATE TABLE simulation_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

# Seed initial cash
c.execute('INSERT INTO simulation_state (cash) VALUES (?)', (INITIAL_CASH,))

conn.commit()
conn.close()

print(f"Rebuilt simulation DB '{DB_FILE}' with initial cash ${INITIAL_CASH:.2f}")
