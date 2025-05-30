import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
import io

ALERTS_DB = 'alerts.db'

def generate_sparkline(prices):
    fig, ax = plt.subplots(figsize=(2.0, 0.4), dpi=100)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    ax.plot(prices, color='yellow', linewidth=1.25)
    ax.axis('off')

    buf = io.BytesIO()
    plt.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0, transparent=True)
    plt.close(fig)
    svg_data = buf.getvalue().decode()
    svg_data = svg_data.split('<svg', 1)[1]
    svg_data = f'<svg{svg_data}'
    return svg_data

def get_active_alerts():
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("""
        SELECT id, symbol, name, price, vwap, vwap_diff, triggers, sparkline, timestamp
        FROM alerts
        WHERE cleared=0
        ORDER BY timestamp DESC
    """)
    rows = c.fetchall()
    columns = [desc[0] for desc in c.description]
    alerts = [dict(zip(columns, row)) for row in rows]
    conn.close()
    return alerts

def mark_alert_cleared(alert_id):
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("UPDATE alerts SET cleared=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()

def clear_all_alerts():
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("UPDATE alerts SET cleared=1")
    conn.commit()
    conn.close()

def insert_alert(timestamp, symbol, name, price, vwap, vwap_diff, triggers, sparkline):
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO alerts (symbol, name, price, vwap, vwap_diff, triggers, sparkline, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S','now'))
    """, (symbol, name, price, vwap, vwap_diff, triggers, sparkline))
    conn.commit()
    conn.close()

def clear_alerts_by_filter(filter_type, value):
    conn = sqlite3.connect(ALERTS_DB)
    cursor = conn.cursor()
    if filter_type == 'symbol':
        cursor.execute("UPDATE alerts SET cleared=1 WHERE symbol=?", (value,))
    elif filter_type == 'trigger':
        cursor.execute("UPDATE alerts SET cleared=1 WHERE triggers LIKE ?", (f"%{value}%",))
    conn.commit()
    conn.close()

get_alerts = get_active_alerts
