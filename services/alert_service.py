import sqlite3
from services.chart_service import get_sparkline_svg, compute_vwap_for_symbol

DB_PATH = 'alerts.db'

def init_db():
    """
    Enable WAL, set busy_timeout, and create alerts table if missing.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=10000;')
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            name TEXT,
            signal TEXT,
            price REAL,
            timestamp TEXT,
            vwap REAL,
            sparkline TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def insert_alert(alert):
    """
    Insert a new alert, computing VWAP and sparkline SVG on the fly.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Compute VWAP and sparkline for this symbol
    vwap_val = compute_vwap_for_symbol(alert['symbol'])
    spark_svg = get_sparkline_svg(alert.get('id'))

    c.execute(
        """
        INSERT INTO alerts(symbol, name, signal, price, timestamp, vwap, sparkline)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert['symbol'],
            alert.get('name', ''),
            alert.get('signal', ''),
            alert.get('price'),
            alert.get('timestamp'),
            vwap_val,
            spark_svg
        )
    )
    conn.commit()
    conn.close()

def get_alerts(filter_signal='all'):
    """
    Fetch alerts, optionally filtering by 'buy' or 'sell'.
    Attach VWAP to each alert record.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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

    alerts = [dict(r) for r in rows]
    for a in alerts:
        a['vwap'] = compute_vwap_for_symbol(a['symbol'])
    return alerts

def clear_alert(alert_id):
    """Delete a single alert by its ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()

def clear_alerts_by_filter(filter_signal):
    """Clear alerts matching a filter, or all if filter not 'buy'/'sell'."""
    conn = sqlite3.connect(DB_PATH)
    if filter_signal.lower() in ('buy', 'sell'):
        conn.execute(
            "DELETE FROM alerts WHERE lower(signal)=?",
            (filter_signal.lower(),)
        )
    else:
        conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
