import sqlite3
from pathlib import Path

# Path to your alerts database
DB_PATH = Path(__file__).parent.parent / 'alerts_clean.db'

def insert_alert(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Insert alert including sparkline
    c.execute(
        'INSERT INTO alerts (symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap, buy_sell) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            data.get('symbol'),
            data.get('name'),
            data.get('signal'),
            float(data.get('confidence', 0)),
            float(data.get('price', 0)),
            data.get('timestamp'),
            data.get('sparkline'),  # store CSV sparkline string
            ','.join(data.get('triggers', [])),
            float(data.get('vwap', 0)),
            data.get('buy_sell', 'BUY')
        )
    )
    conn.commit()
    conn.close()

def get_alerts(filter_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if filter_type == 'all':
        c.execute(
            'SELECT id, symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap, buy_sell '
            'FROM alerts ORDER BY timestamp DESC'
        )
    elif filter_type == 'sell':
        c.execute(
            """SELECT id, symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap, buy_sell
                 FROM alerts WHERE buy_sell='SELL' ORDER BY timestamp DESC"""
        )
    else:
        c.execute(
            """SELECT id, symbol, name, signal, confidence, price, timestamp, sparkline, triggers, vwap, buy_sell
                 FROM alerts WHERE LOWER(signal)=? ORDER BY timestamp DESC""",
            (filter_type.lower(),)
        )
    rows = c.fetchall()
    conn.close()

    alerts = []
    for row in rows:
        # Map columns, including sparkline string
        alerts.append({
            'id':         row[0],
            'symbol':     row[1],
            'name':       row[2],
            'signal':     row[3],
            'confidence': row[4],
            'price':      row[5],
            'timestamp':  row[6],
            'sparkline':  row[7],  # CSV data for sparkline
            'triggers':   row[8].split(',') if row[8] else [],
            'vwap':       row[9],
            'buy_sell':   row[10]
        })
    return alerts

def clear_alert(filter_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if filter_type == 'all':
        c.execute('DELETE FROM alerts')
    elif filter_type == 'sell':
        c.execute("""DELETE FROM alerts WHERE buy_sell='SELL'"""
    )
    else:
        c.execute("""DELETE FROM alerts WHERE LOWER(signal)=?""", (filter_type.lower(),))
    conn.commit()
    conn.close()
