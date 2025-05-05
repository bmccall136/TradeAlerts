from flask import Blueprint, jsonify, request
import sqlite3
import time

api = Blueprint('api', __name__, url_prefix='/api')
DB_PATH = 'alerts_clean.db'

def fetch_alerts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM alerts ORDER BY timestamp DESC").fetchall()
    conn.close()
    alerts = []
    for r in rows:
        # handle missing 'type' column gracefully
        alert = dict(r)
        alert.setdefault('type', 'sell')
        alerts.append(alert)
    return alerts

@api.route('/alerts', methods=['GET'])
def get_alerts():
    return jsonify(fetch_alerts())

@api.route('/status', methods=['GET'])
def get_status():
    status = {
        'yahoo': 'open' if time.localtime().tm_hour < 16 else 'closed',
        'etrade': 'ok'
    }
    return jsonify(status)

@api.route('/alerts/clear_filtered', methods=['POST'])
def clear_filtered():
    data = request.get_json(force=True)
    f = data.get('filter')
    conn = sqlite3.connect(DB_PATH)
    if f and f != 'all':
        try:
            conn.execute("DELETE FROM alerts WHERE type=?", (f,))
        except sqlite3.OperationalError:
            conn.execute("DELETE FROM alerts")
    else:
        conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return ('', 204)
