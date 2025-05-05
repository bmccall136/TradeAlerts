import sqlite3
from config import Config

DB_PATH = Config.ALERT_DB

COLUMN_NAMES = [
    'id', 'symbol', 'name', 'signal', 'confidence', 'price',
    'timestamp', 'type', 'sparkline', 'triggers', 'vwap'
]

def get_alerts(filter_val=None):
    """
    Retrieve alerts from the database.
    Returns a list of dicts with keys matching COLUMN_NAMES.
    If filter_val is provided (and not 'all'), filter by signal.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if filter_val and filter_val.lower() != 'all':
        cursor.execute("SELECT * FROM alerts WHERE signal = ?", (filter_val,))
    else:
        cursor.execute("SELECT * FROM alerts")
    rows = cursor.fetchall()
    conn.close()
    alerts = []
    # Map rows to dicts and coalesce None to default numeric values
    for row in rows:
        d = dict(zip(COLUMN_NAMES, row))
        # default numeric fields
        if d.get('vwap') is None:
            d['vwap'] = 0.0
        if d.get('price') is None:
            d['price'] = 0.0
        if d.get('confidence') is None:
            d['confidence'] = 0
        alerts.append(d)
    return alerts


def insert_alert(data):
    """
    Insert a new alert record.
    Data is a dict with keys: symbol, name, signal, confidence, price, timestamp, type, sparkline, triggers, vwap.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alerts
        (symbol, name, signal, confidence, price, timestamp, type, sparkline, triggers, vwap)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            data.get('symbol'),
            data.get('name'),
            data.get('signal'),
            data.get('confidence'),
            data.get('price'),
            data.get('timestamp'),
            data.get('type', 'sell'),
            data.get('sparkline', ''),
            data.get('triggers', ''),
            data.get('vwap', 0.0)
        )
    )
    conn.commit()
    conn.close()

def clear_alert(alert_id):
    """
    Delete an alert by its ID.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
