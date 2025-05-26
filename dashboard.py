import os
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import pytz
import json

app = Flask(__name__)

# --- CONFIG PATHS ---
PROD_CONFIG_PATH = 'config_live.json'
BACKTEST_CONFIG_PATH = 'config_backtest.json'
SIM_DB = 'simulation.db'
ALERTS_DB = 'alerts.db'
BACKTEST_DB = 'backtest.db'

# --- TIMEZONE ---
LOCAL_TZ = pytz.timezone('America/New_York')

# --- UTILS ---
def local_time_str(utc_str):
    # Convert UTC string to Eastern time string for display
    utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
    return utc_dt.replace(tzinfo=pytz.utc).astimezone(LOCAL_TZ).strftime('%Y-%m-%d %I:%M:%S %p')

# --- LOAD CONFIG ---
def load_config(prod=True):
    cfg_path = PROD_CONFIG_PATH if prod else BACKTEST_CONFIG_PATH
    if not os.path.exists(cfg_path):
        return {}
    with open(cfg_path, 'r') as f:
        return json.load(f)

def save_config(cfg, prod=True):
    cfg_path = PROD_CONFIG_PATH if prod else BACKTEST_CONFIG_PATH
    with open(cfg_path, 'w') as f:
        json.dump(cfg, f, indent=2)

# --- ALERT ROUTES ---
@app.route('/')
@app.route('/alerts')
def alerts():
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("SELECT id, symbol, price, triggers, sparkline, timestamp, name FROM alerts WHERE cleared=0 ORDER BY timestamp DESC")
    alerts = c.fetchall()
    conn.close()
    # convert UTC to local for display
    alerts = [list(alert) for alert in alerts]
    for alert in alerts:
        alert[5] = local_time_str(alert[5])
        alert[4] = f"/sparkline/{alert[0]}.svg" if alert[4] else ""
    return render_template('alerts.html', alerts=alerts, config=load_config(True))


@app.route('/clear_alert/<int:alert_id>', methods=['POST'])
def clear_alert(alert_id):
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("UPDATE alerts SET cleared=1 WHERE id=?", (alert_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/clear_all_alerts', methods=['POST'])
def clear_all_alerts():
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("UPDATE alerts SET cleared=1")
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

# --- SIMULATION ROUTES ---
@app.route('/simulation')
def simulation():
    conn = sqlite3.connect(SIM_DB)
    c = conn.cursor()
    c.execute("SELECT symbol, qty, avg_cost, last_price FROM holdings")
    holdings = c.fetchall()
    unrealized_total = 0
    holdings_data = []
    for sym, qty, avg_cost, last_price in holdings:
        unreal = (last_price - avg_cost) * qty
        holdings_data.append({
            "symbol": sym,
            "qty": qty,
            "avg_cost": avg_cost,
            "last_price": last_price,
            "unreal": unreal
        })
        unrealized_total += unreal
    c.execute("SELECT cash_balance FROM account LIMIT 1")
    row = c.fetchone()
    cash = row[0] if row else 0

    conn.close()
    return render_template('simulation.html',
                           holdings=holdings_data,
                           unrealized_total=unrealized_total,
                           cash=cash,
                           config=load_config(True))

# --- BACKTEST ROUTES ---
@app.route('/backtest', methods=['GET', 'POST'])
def backtest():
    # POST runs a backtest, GET displays last run
    if request.method == 'POST':
        config = request.json or request.form
        # ... Insert your backtest run logic here ...
        # Simulate and store results
        pass
    # For now, show a placeholder
    return render_template('backtest.html', config=load_config(False))

# --- CONFIG ROUTES ---
@app.route('/config', methods=['GET', 'POST'])
def config():
    prod = (request.args.get('mode', 'prod') == 'prod')
    if request.method == 'POST':
        cfg = request.json if request.is_json else request.form.to_dict()
        save_config(cfg, prod=prod)
        return jsonify({'status': 'success'})
    cfg = load_config(prod=prod)
    return render_template('config.html', config=cfg, prod=prod)

# --- STATUS ROUTE ---
@app.route('/status')
def status():
    # Add health checks for API keys, database status, etc.
    return jsonify({'status': 'ok'})
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
from flask import send_file

@app.route('/sparkline/<int:alert_id>.svg')
def sparkline(alert_id):
    conn = sqlite3.connect(ALERTS_DB)
    c = conn.cursor()
    c.execute("SELECT sparkline FROM alerts WHERE id=?", (alert_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return ('<svg width="60" height="20"></svg>', 200, {'Content-Type': 'image/svg+xml'})
    try:
        prices = json.loads(row[0])
        if not isinstance(prices, list):
            raise ValueError
    except Exception:
        return ('<svg width="60" height="20"></svg>', 200, {'Content-Type': 'image/svg+xml'})
    fig, ax = plt.subplots(figsize=(2.4, 0.75), dpi=50)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    ax.plot(prices, linewidth=2, color="#39ff14")
    ax.axis('off')
    ax.set_xlim([0, len(prices)-1])
    ax.set_ylim([min(prices), max(prices)])
    for spine in ax.spines.values():
        spine.set_visible(False)
    rect = plt.Rectangle((0,0),1,1, color='black', zorder=-1)
    ax.add_patch(rect)
    buf = io.BytesIO()
    plt.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0, facecolor='black')
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype='image/svg+xml')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
