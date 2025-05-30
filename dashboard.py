from flask import Flask, render_template, redirect, url_for, request
import sqlite3
from api import api_bp
from static_bp import static_bp
from services.alert_service import get_alerts

app = Flask(__name__)
app.register_blueprint(api_bp)
app.register_blueprint(static_bp)

DB_PATH = 'alerts.db'

def safe_insert_alert(data):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT INTO alerts
            (symbol,name,signal,confidence,price,timestamp,type,sparkline,triggers,vwap)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (
            data.get('symbol'),
            data.get('name'),
            data.get('signal'),
            data.get('confidence'),
            data.get('price'),
            data.get('timestamp'),
            data.get('type', 'sell'),
            data.get('sparkline', ''),
            data.get('triggers', ''),
            data.get('vwap', 0.0)
        ))
    except sqlite3.OperationalError:
        # Fallback if 'type' column missing
        conn.execute('''
            INSERT INTO alerts
            (symbol,name,signal,confidence,price,timestamp,sparkline,triggers,vwap)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (
            data.get('symbol'),
            data.get('name'),
            data.get('signal'),
            data.get('confidence'),
            data.get('price'),
            data.get('timestamp'),
            data.get('sparkline', ''),
            data.get('triggers', ''),
            data.get('vwap', 0.0)
        ))
    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        safe_insert_alert(request.get_json(force=True))
        return ('', 204)
    # Fetch alerts to display on dashboard
    alerts = get_alerts()
    filter_val = request.args.get('filter')
    return render_template('alerts.html', alerts=alerts, filter=filter_val)

@app.route('/alerts', methods=['POST'])
def post_alert():
    return index()

@app.route('/alerts/<int:alert_id>/clear', methods=['POST'])

@app.route('/clear_all', methods=['POST'])
def clear_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return redirect('/alerts')

@app.route('/backtest')
def backtest():
    return render_template('backtest.html')

@app.route('/config')
def config():
    # Assuming your config is loaded as 'config'
    config_clean = {}
    for k, v in config.items():
        if isinstance(v, timedelta):
            config_clean[k] = str(v)
        else:
            config_clean[k] = v
    return render_template('config.html', config=config_clean, prod=True)  # Or whatever value 'prod' is

@app.route('/reconnect_api')
def reconnect_api():
    return redirect(url_for('index'))

@app.route('/simulation')
def simulation():
    return render_template('simulation.html')

@app.route('/simulation/reset', methods=['POST'])
def sim_reset():
    return ('', 204)

@app.route('/simulation/buy', methods=['POST'])
def simulation_buy():
    data = request.json
    symbol = data.get('symbol')
    qty = int(data.get('qty', 1))
    # Add to simulation DB
    # return jsonify({'success': True})

@app.route('/alerts/clear/<int:id>', methods=['POST'])
def clear_alert(id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
    return ('', 204)
    return redirect(url_for('index'))

@app.route('/alerts/clear_all', methods=['POST'])
def clear_all_alerts():
    # Your clear all logic here
    return redirect(url_for('index'))

import subprocess
from flask import redirect, url_for, flash

@app.route('/launch_auth', methods=['POST'])
def launch_auth():
    try:
        # Launches in a new CLI window (Windows-specific)
        subprocess.Popen(['start', 'cmd', '/k', 'python', 'etrade_auth_flow.py'], shell=True)
        flash('E*TRADE Auth flow launched in CLI window.', 'success')
    except Exception as e:
        flash(f'Error launching E*TRADE Auth: {e}', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
