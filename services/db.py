import sqlite3

def get_connection():
    # Adjust database filename/path as needed
    conn = sqlite3.connect('alerts.db', detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn
