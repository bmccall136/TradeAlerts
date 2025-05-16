
import sqlite3
from .db import get_connection

def insert_alert(data):
    """
    Insert a new alert into the alerts table. If the 'confidence' column
    doesn't exist yet, add it, then retry the insert.
    """
    conn = get_connection()
    c = conn.cursor()
    # Ensure confidence column exists before insert
    _ensure_confidence_column(c, conn)

    c.execute(
        "INSERT INTO alerts(symbol, name, signal, confidence, price, vwap, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            data.get('symbol'),
            data.get('name'),
            data.get('signal'),
            data.get('confidence'),
            data.get('price'),
            data.get('vwap'),
            data.get('timestamp'),
        )
    )
    conn.commit()
    conn.close()

def get_alerts(filter_name='all'):
    """
    Retrieve alerts from the database. Ensures 'confidence' column exists.
    Supports filtering by 'signal' field.
    """
    conn = get_connection()
    c = conn.cursor()
    # Ensure confidence column exists before selecting
    _ensure_confidence_column(c, conn)

    if filter_name and filter_name.lower() != 'all':
        c.execute(
            "SELECT symbol, name, signal, confidence, price, vwap, timestamp "
            "FROM alerts WHERE signal = ? ORDER BY timestamp DESC",
            (filter_name,)
        )
    else:
        c.execute(
            "SELECT symbol, name, signal, confidence, price, vwap, timestamp "
            "FROM alerts ORDER BY timestamp DESC"
        )
    rows = c.fetchall()
    conn.close()

    return [
        {
            'symbol':     row[0],
            'name':       row[1],
            'signal':     row[2],
            'confidence': row[3],
            'price':      row[4],
            'vwap':       row[5],
            'timestamp':  row[6],
        }
        for row in rows
    ]

def clear_alerts_by_filter(filter_name='all'):
    """
    Delete alerts matching the given filter. If 'all', clears all alerts.
    """
    conn = get_connection()
    c = conn.cursor()
    if filter_name and filter_name.lower() != 'all':
        c.execute("DELETE FROM alerts WHERE signal = ?", (filter_name,))
    else:
        c.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()

def _ensure_confidence_column(cursor, conn):
    """
    Add 'confidence' column if missing.
    """
    cursor.execute("PRAGMA table_info(alerts)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'confidence' not in cols:
        cursor.execute("ALTER TABLE alerts ADD COLUMN confidence TEXT")
        conn.commit()
