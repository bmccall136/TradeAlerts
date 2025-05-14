from flask import Blueprint, jsonify, request
import sqlite3
import time

from services.alert_service import insert_alert, get_alerts, clear_alerts_by_filter

DB_PATH = 'alerts.db'
api = Blueprint('api', __name__, url_prefix='/api')

# just define it here, don’t decorate the Blueprint
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=10000;')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            signal TEXT NOT NULL,
            confidence REAL,
            price REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

@api.route('/alerts', methods=['GET','POST'], strict_slashes=False)
def alerts():
    if request.method == 'POST':
        data = request.get_json(force=True)
        insert_alert(data)
        return '', 201
    return jsonify(get_alerts()), 200

@api.route('/status', methods=['GET'], strict_slashes=False)
def status():
    return jsonify({
        'yahoo': 'open' if time.localtime().tm_hour < 16 else 'closed',
        'etrade': 'ok'
    }), 200

@api.route('/alerts/clear', methods=['POST'], strict_slashes=False)
def clear_filtered():
    payload = request.get_json(force=True)
    f = (payload.get('filter') or 'all').lower()
    clear_alerts_by_filter(f)
    return '', 204
