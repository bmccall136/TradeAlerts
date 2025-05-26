import sqlite3
from datetime import datetime

ALERTS_DB = 'alerts.db'

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

def insert_alert(symbol, alert_type, price, triggers, sparkline, name):
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO alerts
        (symbol, alert_type, price, triggers, sparkline, timestamp, name, cleared)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    """, (symbol, alert_type, price, triggers, sparkline, now, name))
    conn.commit()
    conn.close()
