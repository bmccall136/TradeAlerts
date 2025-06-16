#!/usr/bin/env python3
import sqlite3

DB_PATH = 'alerts.db'   # adjust if needed
TABLE  = 'indicator_settings'

COLUMNS_TO_ADD = [
    ('sma_on',         'INTEGER NOT NULL DEFAULT 1'),
    ('rsi_on',         'INTEGER NOT NULL DEFAULT 1'),
    ('macd_on',        'INTEGER NOT NULL DEFAULT 0'),
    ('bb_on',          'INTEGER NOT NULL DEFAULT 0'),
    ('vol_on',         'INTEGER NOT NULL DEFAULT 0'),
    ('vwap_on',        'INTEGER NOT NULL DEFAULT 1'),
    ('rsi_slope_on',   'INTEGER NOT NULL DEFAULT 1'),
    ('macd_hist_on',   'INTEGER NOT NULL DEFAULT 1'),
    ('bb_breakout_on', 'INTEGER NOT NULL DEFAULT 1'),
]

def column_exists(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cur.fetchall())

def add_column(conn, table, column, definition):
    print(f"Adding `{column}` …", end=' ')
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")
    print("done.")

def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL;")
    for col, definition in COLUMNS_TO_ADD:
        if not column_exists(conn, TABLE, col):
            add_column(conn, TABLE, col, definition)
        else:
            print(f"`{col}` already exists, skipping.")
    conn.commit()
    conn.close()
    print("All done!")

if __name__ == "__main__":
    main()
