# File: dashboard.py

from pathlib import Path
import os
import subprocess
import sqlite3
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, jsonify
)
from services.simulation_service import buy_stock
from services.alert_service import get_alerts
from services.news_service import fetch_latest_headlines, news_sentiment
from services.etrade_service import get_etrade_price

# Import everything we need from simulation_service:
from services.simulation_service import (
    get_holdings,
    get_cash,
    get_realized_pl,
    get_trades,
    sell_stock
)
from services.backtest_service import backtest

trades, pnl = backtest("AAPL", "2024-01-01", "2024-06-01", initial_cash=10000)
# Now you can format `trades` into a table or feed into your simulation service.

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"

DB_PATH  = 'alerts.db'
SIM_DB   = 'simulation.db'  # Must match SIM_DB in simulation_service.py


### ────────────── ALERTS (UNCHANGED) ────────────── ###

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Insert an incoming alert JSON payload
        safe_insert_alert(request.get_json(force=True))
        return ('', 204)
    alerts = get_alerts()
    return render_template('alerts.html', alerts=alerts)


@app.route('/nuke_db', methods=['POST'])
def nuke_db():
    try:
        result = subprocess.run(
            ['python', 'init_alerts_db.py'],
            capture_output=True, text=True, timeout=10
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
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    flash('✅ All alerts cleared!', 'info')
    return redirect(url_for('index'))


@app.route('/clear/<int:id>', methods=['POST'])
def clear_alert(id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM alerts WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash(f'ℹ️ Alert #{id} cleared.', 'info')
    return redirect(url_for('index'))


@app.route('/buy/<symbol>', methods=['POST'])
def buy_stock_route(symbol):
    # This “Buy” route is only for the Alerts page (index), not Simulation.
    flash(f'🟢 Simulated BUY for {symbol}', 'success')
    return redirect(url_for('index'))


@app.route('/launch_auth', methods=['POST'])
def launch_auth():
    try:
        subprocess.Popen(
            ['start', 'cmd', '/k', 'python', 'etrade_auth_flow.py'],
            shell=True
        )
        flash('🔑 E*TRADE Auth flow launched in new window.', 'info')
    except Exception as e:
        flash(f'❌ Error launching E*TRADE Auth: {e}', 'danger')
    return redirect(url_for('index'))


@app.route("/backtest")
def backtest_view():
    symbol = "AAPL"
    start_date = "2024-01-01"
    end_date = "2024-06-01"
    trades, pnl = backtest(symbol, start_date, end_date)
    return render_template("backtest.html", trades=trades, pnl=pnl)

@app.route('/config')
def config():
    config = {}
    config_clean = {
        k: str(v) if isinstance(v, timedelta) else v
        for k, v in config.items()
    }
    return render_template('config.html', config=config_clean)


### ────────────── SIMULATION ────────────── ###

@app.route('/reset_simulation', methods=['POST'])
def reset_simulation():
    result = nuke_simulation_db()
    if result:
        return "Simulation reset!", 200
    else:
        return "Failed to reset simulation database.", 500


def nuke_simulation_db():
    try:
        with sqlite3.connect(str(Path(__file__).resolve().parent.parent / 'simulation.db')) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM holdings;")
            c.execute("DELETE FROM simulation_trades;")
            # Try to reset realized_pl in state
            try:
                c.execute("UPDATE state SET realized_pl = 0.0 WHERE id = 1;")
            except sqlite3.OperationalError:
                c.execute("ALTER TABLE state ADD COLUMN realized_pl REAL DEFAULT 0.0;")
                c.execute("UPDATE state SET realized_pl = 0.0 WHERE id = 1;")
            c.execute("INSERT OR IGNORE INTO state (id, realized_pl) VALUES (1, 0.0);")
            conn.commit()

        print("Simulation DB nuked/reset!")
        return True  # <--- NOT indented under with!
    except Exception as e:
        print(f"Failed to nuke simulation DB: {e}")
        return False


@app.route('/simulation')
def simulation():
    # Default fallback values if something goes wrong
    cash               = 0.0
    unrealized_pnl     = 0.0
    realized_pnl       = 0.0     # define it here to avoid NameError
    formatted_holdings = []
    formatted_trades   = []

    try:
        # 1) Current cash & realized P/L
        cash          = get_cash()
        realized_pnl  = get_realized_pl()   # ← newly added line

        # 2) Gather and format holdings for the template
        raw_holdings = get_holdings()
        unrealized_pnl = 0.0
        for h in raw_holdings:
            unrealized_pnl += h['total_gain']
            formatted_holdings.append({
                'symbol':     h['symbol'],
                'last_price': h['last_price'],
                'change':     h['change'],
                'change_pct': h['change_pct'],
                'qty':        h['qty'],
                'price_paid': h['price_paid'],
                'day_gain':   h['day_gain'],
                'total_gain': h['total_gain'],
                'value':      h['value']
            })

        # 3) Gather and format trade history for the template
        raw_trades = get_trades()
        for t in raw_trades:
            pl_display = f"${t['pnl']:.2f}" if t['pnl'] is not None else "-"
            formatted_trades.append({
                'time':     t['trade_time'],
                'symbol':   t['symbol'],
                'action':   t['action'],
                'qty':      t['qty'],
                'price':    f"${t['price']:.2f}",
                'pl':       pl_display
            })

    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[Simulation Error] {e}")

    return render_template(
        'simulation.html',
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,   # now defined above
        holdings=formatted_holdings,
        history=formatted_trades
    )


@app.route("/simulation/buy", methods=["POST"])
def simulation_buy():
    data = request.get_json()
    symbol = data.get("symbol")
    qty    = int(data.get("qty", 0))
    if not symbol or qty <= 0:
        return jsonify({"error": "Invalid symbol or quantity"}), 400

    try:
        price = get_etrade_price(symbol)  # or however you fetch a live price
        buy_stock(symbol, qty, price)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"success": True, "cash": get_cash()}), 200


@app.route("/simulation/sell", methods=["POST"])
def simulation_sell():
    data = request.get_json()
    symbol = data.get("symbol")
    qty    = int(data.get("qty", 0))
    if not symbol or qty <= 0:
        return jsonify({"error": "Invalid symbol or quantity"}), 400

    try:
        price = get_etrade_price(symbol)
        sell_stock(symbol, qty, price)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "success": True,
        "cash": get_cash(),
        "realized_pl": get_realized_pl()
    }), 200

@app.route('/news/<symbol>')
def news_for_symbol(symbol):
    headlines = fetch_latest_headlines(symbol)
    sentiment = news_sentiment(symbol)
    return jsonify({'headlines': headlines, 'sentiment': sentiment})


if __name__ == '__main__':
    app.run(debug=True)
