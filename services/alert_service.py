import sqlite3
from datetime import datetime

DB = 'alerts.db'

def init_db():
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE,
                price REAL,
                filter_name TEXT,
                confidence REAL,
                timestamp TEXT,
                spark TEXT,
                triggers TEXT
            )"""
        )
        conn.commit()

def insert_alert(symbol, price, filter_name, confidence, spark=None, triggers=None, **kwargs):
    """
    Insert or update an alert for a symbol. Overwrites any existing alert for the same symbol.
    """
    ts = datetime.utcnow().isoformat()
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM alerts WHERE symbol = ?', (symbol,))
        c.execute(
            'INSERT INTO alerts (symbol, price, filter_name, confidence, timestamp, spark, triggers) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (symbol, price, filter_name, confidence, ts, spark or '', triggers or '')
        )
        conn.commit()

def get_alerts(filter_name='all'):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        if filter_name == 'all':
            c.execute(
                'SELECT id, symbol, price, filter_name, confidence, timestamp, spark, triggers '
                'FROM alerts ORDER BY id DESC'
            )
        else:
            c.execute(
                'SELECT id, symbol, price, filter_name, confidence, timestamp, spark, triggers '
                'FROM alerts WHERE filter_name = ? ORDER BY id DESC',
                (filter_name,)
            )
        rows = c.fetchall()
    return [
        {
            'id': r[0], 'symbol': r[1], 'price': r[2],
            'filter_name': r[3], 'confidence': r[4],
            'timestamp': r[5], 'spark': r[6], 'triggers': r[7]
        }
        for r in rows
    ]

def clear_alerts(filter_name='all'):
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        if filter_name == 'all':
            c.execute('DELETE FROM alerts')
        else:
            c.execute('DELETE FROM alerts WHERE filter_name = ?', (filter_name,))
        conn.commit()

def delete_alert(alert_id):
    """
    Delete a single alert by its ID.
    """
    with sqlite3.connect(DB) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))
        conn.commit()

# Alias for backward compatibility
clear_alerts_by_filter = clear_alerts
