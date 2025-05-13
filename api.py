
from flask import Blueprint, jsonify, request
import sqlite3
import time
from services.alert_service import insert_alert, get_all_alerts

api = Blueprint('api', __name__, url_prefix='/api')

DB_PATH = 'alerts_clean.db'

def fetch_alerts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM alerts ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Combined GET and POST on /alerts with strict_slashes off
@api.route('/alerts', methods=['GET','POST'], strict_slashes=False)
def alerts():
    if request.method == 'POST':
        print("[DEBUG] Received POST /api/alerts")
        print("Headers:", dict(request.headers))
        raw = request.get_data(as_text=True)
        print("Raw body:", raw)
        try:
            data = request.get_json(force=True)
        except Exception as e:
            print("[DEBUG] JSON parse error:", e)
            return ("Bad Request: Invalid JSON", 400)
        print("[DEBUG] Parsed JSON payload:", data)
        insert_alert(data)
        return ('', 201)

    # GET listing
    return jsonify(fetch_alerts())

@api.route('/status', methods=['GET'], strict_slashes=False)
def get_status():
    return jsonify({
        'yahoo': 'open' if time.localtime().tm_hour < 16 else 'closed',
        'etrade': 'ok'
    })

@api.route('/alerts/clear_filtered', methods=['POST'], strict_slashes=False)
def clear_filtered():
    data = request.get_json(force=True)
    f = data.get('filter')
    conn = sqlite3.connect(DB_PATH)
    if f and f != 'all':
        conn.execute("DELETE FROM alerts WHERE type=?", (f,))
    else:
        conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return ('', 204)
