from flask import Blueprint, jsonify, request
import sqlite3
import time

from services.alert_service import insert_alert

api = Blueprint('api', __name__, url_prefix='/api')

DB_PATH = 'alerts.db'

@api.route('/alerts', methods=['GET', 'POST'], strict_slashes=False)
def alerts():
    if request.method == 'GET':
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200

    data = request.get_json(force=True)
    insert_alert(data)
    return ('', 201)

@api.route('/status', methods=['GET'], strict_slashes=False)
def status():
    return jsonify({
        'yahoo': 'open' if time.localtime().tm_hour < 16 else 'closed',
        'etrade': 'ok'
    }), 200

@api.route('/alerts/clear_filtered', methods=['POST'], strict_slashes=False)
def clear_filtered():
    payload = request.get_json(force=True)
    f = payload.get('filter')
    conn = sqlite3.connect(DB_PATH)
    if f and f.lower() in ('buy','sell'):
        conn.execute(
            "DELETE FROM alerts WHERE lower(signal)=?", (f.lower(),)
        )
    else:
        conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return ('', 204)
