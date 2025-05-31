import sqlite3
import subprocess
from flask import Flask, render_template, redirect, url_for, request, flash
from services.alert_service import get_alerts

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"  # for flashing messages

DB_PATH = 'alerts.db'


def safe_insert_alert(data):
    """
    Inserts a new alert (called by the POST on '/').
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT INTO alerts
            (symbol, name, price, timestamp, vwap, vwap_diff, triggers, sparkline, cleared)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (
            data.get('symbol'),
            data.get('name'),
            data.get('price'),
            data.get('timestamp'),
            data.get('vwap', 0.0),
            data.get('vwap_diff', 0.0),
            data.get('triggers', ''),
            data.get('sparkline', '')
        ))
    except sqlite3.OperationalError as e:
        # If the schema is slightly different (older versions), you can adapt here.
        print(f"[WARN] safe_insert_alert: SQLite error: {e}")
    conn.commit()
    conn.close()


@app.route('/', methods=['GET', 'POST'])
def index():
    """
    GET → Render the dashboard with current alerts.
    POST → Receive a JSON payload (from scanner), store it, and return 204.
    """
    if request.method == 'POST':
        safe_insert_alert(request.get_json(force=True))
        return ('', 204)

    alerts = get_alerts()
    return render_template('alerts.html', alerts=alerts)


@app.route('/nuke_db', methods=['POST'])
def nuke_db():
    """
    Re‑creates (nukes) the alerts.db by calling your init_alerts_db.py script.
    """
    try:
        result = subprocess.run(
            ['python', 'init_alerts_db.py'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            flash('✅ Database nuked and recreated!', 'success')
        else:
            flash(f'❌ Nuke failed: {result.stderr}', 'danger')
    except Exception as e:
        flash(f'❌ Error nuking DB: {e}', 'danger')

    return redirect(url_for('index'))


@app.route('/clear_all', methods=['POST'])
def clear_all_alerts():
    """
    Clears every row in alerts → acts on the “Clear All” button in the UI.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    flash('✅ All alerts cleared!', 'info')
    return redirect(url_for('index'))


@app.route('/clear/<int:id>', methods=['POST'])
def clear_alert(id):
    """
    Clears a single alert by its `id` → used by the “Clear” button next to each row.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM alerts WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash(f'ℹ️ Alert #{id} cleared.', 'info')
    return redirect(url_for('index'))


@app.route('/buy/<symbol>', methods=['POST'])
def buy_stock(symbol):
    """
    Simulated “Buy” → triggered by the “Buy” button in each row.
    """
    # Insert your simulated‑buy logic here (e.g. add to a simulation DB).
    flash(f'🟢 Simulated BUY for {symbol}', 'success')
    return redirect(url_for('index'))


@app.route('/launch_auth', methods=['POST'])
def launch_auth():
    """
    Launches your E*TRADE OAuth script in a separate CLI window
    so the user can copy/paste the PIN and refresh tokens in .env.
    """
    try:
        # Windows: open a new cmd window and run the auth flow
        subprocess.Popen(['start', 'cmd', '/k', 'python', 'etrade_auth_flow.py'], shell=True)
        flash('🔑 E*TRADE Auth flow launched in new window.', 'info')
    except Exception as e:
        flash(f'❌ Error launching E*TRADE Auth: {e}', 'danger')
    return redirect(url_for('index'))


@app.route('/backtest')
def backtest():
    return render_template('backtest.html')


@app.route('/config')
def config():
    # If you have a config dict or object, pass it here. Example:
    from datetime import timedelta
    config = {}  # load or build your config dict
    config_clean = {}
    for k, v in config.items():
        if isinstance(v, timedelta):
            config_clean[k] = str(v)
        else:
            config_clean[k] = v
    return render_template('config.html', config=config_clean)


@app.route('/simulation')
def simulation():
    return render_template('simulation.html')


@app.route('/simulation/reset', methods=['POST'])
def sim_reset():
    return ('', 204)


@app.route('/simulation/buy', methods=['POST'])
def simulation_buy():
    data = request.get_json(force=True)
    symbol = data.get('symbol')
    qty = int(data.get('qty', 1))
    # Add this to your simulation DB if needed
    return ('', 204)


if __name__ == '__main__':
    app.run(debug=True)
