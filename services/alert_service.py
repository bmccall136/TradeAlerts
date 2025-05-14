import sqlite3
from typing import List, Dict

DB_PATH = 'alerts.db'

def get_db_connection():
    """Return a SQLite connection with row factory set to Row."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create the alerts table if it doesn't exist."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            signal TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def insert_alert(data: Dict):
    """Insert a new alert into the database."""
    # Ensure name is never NULL
    name = data.get('name') or data['symbol']
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO alerts (symbol, name, signal, price, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data['symbol'],
        name,
        data['signal'],
        data['price'],
        data['timestamp'],
    ))
    conn.commit()
    conn.close()

def get_alerts(filter_signal: str = 'all') -> List[Dict]:
    """Retrieve alerts, optionally filtering by signal ('buy' or 'sell')."""
    conn = get_db_connection()
    c = conn.cursor()
    if filter_signal.lower() in ('buy', 'sell'):
        rows = c.execute(
            "SELECT * FROM alerts WHERE lower(signal)=? ORDER BY timestamp DESC",
            (filter_signal.lower(),)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def clear_alerts_by_filter(filter_signal: str = 'all') -> None:
    """Delete alerts based on the given filter."""
    conn = get_db_connection()
    c = conn.cursor()
    if filter_signal.lower() in ('buy', 'sell'):
        c.execute(
            "DELETE FROM alerts WHERE lower(signal)=?",
            (filter_signal.lower(),)
        )
    else:
        c.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()

def clear_alert(alert_id: int) -> None:
    """Delete a single alert by its ID."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
