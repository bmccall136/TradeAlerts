import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
import io
ALERTS_DB = 'alerts.db'

def generate_sparkline(prices):
    fig, ax = plt.subplots(figsize=(2.0, 0.4), dpi=100)
    fig.patch.set_facecolor('black')       # Black outer background
    ax.set_facecolor('black')              # Black plot background
    ax.plot(prices, color='yellow', linewidth=1.25)
    ax.axis('off')

    buf = io.BytesIO()
    plt.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0, transparent=True)
    plt.close(fig)
    svg_data = buf.getvalue().decode()

    # Strip unneeded metadata from SVG
    svg_data = svg_data.split('<svg', 1)[1]
    svg_data = f'<svg{svg_data}'

    return svg_data

def get_active_alerts():
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("""
        SELECT id, symbol, alert_type, price, confidence, timestamp, triggers, sparkline, cleared
        FROM alerts
        WHERE cleared=0
        ORDER BY timestamp DESC
    """)
    alerts = c.fetchall()
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

def insert_alert(symbol, alert_type, price, confidence, triggers, sparkline):
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO alerts
        (symbol, alert_type, price, confidence, timestamp, triggers, sparkline, cleared)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    """, (symbol, alert_type, price, confidence, now, triggers, sparkline))
    conn.commit()
    conn.close()
