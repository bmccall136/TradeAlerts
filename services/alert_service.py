import sqlite3

DB_PATH = 'alerts.db'

def insert_alert(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''
        INSERT INTO alerts (symbol, name, signal, confidence, price, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (
            data['symbol'],
            data.get('name', ''),
            data['signal'],
            data.get('confidence'),
            data['price'],
            data['timestamp']
        )
    )
    conn.commit()
    conn.close()

def get_alerts(filter='all'):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if filter.lower() != 'all':
        c.execute("SELECT * FROM alerts WHERE signal = ? ORDER BY timestamp DESC", (filter.upper(),))
    else:
        c.execute("SELECT * FROM alerts ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()

    alerts = []
    from services.chart_service import get_sparkline_svg, compute_vwap_for_symbol
    for r in rows:
        a = dict(r)
        a['sparkline'] = get_sparkline_svg(r['id'])
        a['vwap'] = compute_vwap_for_symbol(r['symbol'])
        alerts.append(a)
    return alerts

def clear_alerts_by_filter(filter):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if filter.lower() == 'all':
        c.execute("DELETE FROM alerts")
    else:
        c.execute("DELETE FROM alerts WHERE signal = ?", (filter.upper(),))
    conn.commit()
    conn.close()
