# File: dashboard.py

from pathlib import Path
import subprocess
import sqlite3
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, jsonify
)

from services.alert_service import get_alerts
from services.news_service import fetch_latest_headlines, news_sentiment
from services.etrade_service import get_etrade_price

from services.simulation_service import (
    get_cash,
    get_realized_pl,
    get_holdings,
    get_trades,
    buy_stock,
    sell_stock
)

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"

DB_PATH  = 'alerts.db'
SIM_DB   = 'simulation.db'  # Must match the path in simulation_service.py


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
    # This route is unrelated to the simulation; it just flashes a message.
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


@app.route('/backtest')
def backtest():
    return render_template('backtest.html')


@app.route('/config')
def config():
    config = {}
    config_clean = {k: str(v) if isinstance(v, timedelta) else v for k, v in config.items()}
    return render_template('config.html', config=config_clean)


### ────────────── SIMULATION ────────────── ###

@app.route('/reset_simulation', methods=['POST'])
def reset_simulation():
    """
    Whenever the user clicks “Reset Simulation,” we re‑create the simulation DB
    by invoking an external script (init_simulation_db.py).
    """
    try:
        subprocess.run(["python", "init_simulation_db.py"], check=True)
        flash('🌀 Simulation database reset.', 'info')
        return redirect(url_for('simulation'))
    except subprocess.CalledProcessError:
        return "Failed to reset simulation database.", 500


@app.route('/simulation')
def simulation():
    """
    Renders the main Simulation page with:
      - current cash
      - unrealized P/L (sum of holdings’ paper gains)
      - realized P/L (from state table)
      - a list of holdings (with formatted strings for display)
      - trade history (all BUY/SELL rows)
    """
    # Default fallback values if something goes wrong
    cash               = 0.0
    unrealized_pnl     = 0.0
    realized_pnl       = 0.0
    formatted_holdings = []
    formatted_trades   = []

    try:
        # 1) Current cash & realized P/L
        cash = get_cash()
        realized_pnl = get_realized_pl()

        # 2) Gather and format holdings for the template
        raw_holdings = get_holdings()
        unrealized_pnl = 0.0
        for h in raw_holdings:
            # Accumulate total (paper) gain = h['total_gain']
            unrealized_pnl += h['total_gain']

            formatted_holdings.append({
                'symbol':     h['symbol'],
                'last_price': f"${h['last_price']:.2f}",
                'change':     f"${h['change']:.2f}",
                'change_pct': f"{h['change_percent']:.2f}%",
                'qty':        h['qty'],
                'price_paid': f"${h['avg_cost']:.2f}",
                'day_gain':   f"${h['day_gain']:.2f}",
                'total_gain': f"${h['total_gain']:.2f}",
                'value':      f"${h['value']:.2f}"
            })

        # 3) Gather and format trade history for the template
        raw_trades = get_trades()
        for t in raw_trades:
            pl_display = f"${t['pl']:.2f}" if t['pl'] is not None else "-"
            formatted_trades.append({
                'time':   t['timestamp'],
                'symbol': t['symbol'],
                'action': t['action'],
                'qty':    t['quantity'],
                'price':  f"${t['price']:.2f}",
                'pl':     pl_display
            })

    except Exception as e:
        print(f"[Simulation Error] {e}")

    return render_template(
        'simulation.html',
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        holdings=formatted_holdings,
        history=formatted_trades
    )


@app.route('/simulation/sell', methods=['POST'])
def route_sell_stock():
    """
    Expects JSON: { "symbol": "...", "qty": N, "price": 123.45 }
    Returns JSON on failure (with error message) or on success:
      { "success": true, "cash":  <new_cash>, "realized_pl": <new_realized_pl> }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON payload"}), 400

    symbol = data.get("symbol")
    try:
        qty   = int(data.get("qty", 0))
        price = float(data.get("price", 0.0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid qty or price"}), 400

    if not symbol or qty <= 0 or price <= 0.0:
        return jsonify({"error": "Symbol, qty, and price must be provided"}), 400

    try:
        sell_stock(symbol, qty, price)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # If successful, return updated cash & realized P/L
    new_cash     = get_cash()
    new_realized = get_realized_pl()
    return jsonify({
        "success":      True,
        "cash":         new_cash,
        "realized_pl":  new_realized
    }), 200


@app.route("/simulation/buy", methods=["POST"])
def simulation_buy():
    """
    Expects JSON: { "symbol": "...", "qty": N }
    Uses E*TRADE price as `price` for the buy.
    Returns JSON: { "success": true, "cash": <new_cash> }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON payload"}), 400

    symbol = data.get("symbol")
    try:
        qty = int(data.get("qty", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid qty"}), 400

    # Fetch E*TRADE price
    price = get_etrade_price(symbol)
    if price is None:
        return jsonify({"error": "Could not fetch price"}), 400

    try:
        buy_stock(symbol, qty, price)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    new_cash = get_cash()
    return jsonify({"success": True, "cash": new_cash}), 200


@app.route('/news/<symbol>')
def news_for_symbol(symbol):
    headlines = fetch_latest_headlines(symbol)
    sentiment = news_sentiment(symbol)
    return jsonify({'headlines': headlines, 'sentiment': sentiment})


if __name__ == '__main__':
    app.run(debug=True)
