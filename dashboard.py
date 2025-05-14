from flask import Flask, render_template, request, redirect, url_for, Response
import sqlite3

from services.alert_service import get_alerts, insert_alert, clear_alert, clear_alerts_by_filter, init_db
from services.chart_service import get_sparkline_svg
from api import api as api_bp

app = Flask(__name__)

# Register API blueprint (it already has its own '/api' prefix)
app.register_blueprint(api_bp)

# Enable WAL and busy_timeout, then initialize table schema
conn = sqlite3.connect('alerts.db', timeout=10)
conn.execute('PRAGMA journal_mode=WAL;')
conn.execute('PRAGMA busy_timeout=10000;')
conn.close()
init_db()

@app.route('/')
def root():
    return redirect(url_for('alerts_index', filter='all'))

@app.route('/alerts')
def alerts_index():
    current_filter = request.args.get('filter', 'all')
    alerts_list    = get_alerts(current_filter)
    return render_template('alerts.html', alerts=alerts_list, current_filter=current_filter)

@app.route('/alerts/clear', methods=['POST'], endpoint='clear_filtered')
def clear_filtered():
    current_filter = request.form.get('filter', 'all')
    clear_alerts_by_filter(current_filter)
    return redirect(url_for('alerts_index', filter=current_filter))

@app.route('/alerts/<int:alert_id>/clear', methods=['POST'], endpoint='clear_one')
def clear_one(alert_id):
    clear_alert(alert_id)
    return redirect(url_for('alerts_index', filter=request.args.get('filter', 'all')))

@app.route('/sparkline/<int:alert_id>.svg')
def sparkline_svg(alert_id):
    svg = get_sparkline_svg(alert_id)
    return Response(svg, mimetype='image/svg+xml') if svg else ('', 404)

if __name__ == '__main__':
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    # Debug print of routes omitted
    app.run(debug=True)
