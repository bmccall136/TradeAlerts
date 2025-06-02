from pathlib import Path
import os
import requests
import sqlite3
import subprocess
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, jsonify
)
from services.alert_service import get_alerts
from services.news_service import fetch_latest_headlines, news_sentiment
from services.etrade_service import get_etrade_price

app = Flask(__name__)
app.secret_key = "replace_this_with_a_random_secret"

DB_PATH = 'alerts.db'
SIM_DB = 'simulation.db'


def get_realtime_price(symbol):
    url = f"https://api.etrade.com/v1/market/quote/{symbol}.json"
    headers = {
        "Authorization": f"Bearer {os.getenv('ETRADE_ACCESS_TOKEN')}"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        quote_data = data.get("quoteResponse", {}).get("quoteData", [])
        if not quote_data:
            print(f"❌ No QuoteData returned for {symbol}")
            return None

        last_trade = quote_data[0].get("All", {}).get("lastTrade")
        if last_trade is None:
            print(f"❌ No lastTrade price found for {symbol}")
            return None

        return float(last_trade)

    except Exception as e:
        print(f"❌ API error for {symbol}: {e}")
        return None

   
def safe_insert_alert(data):
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
        print(f"[WARN] safe_insert_alert: SQLite error: {e}")
    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
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
def buy_stock(symbol):
    flash(f'🟢 Simulated BUY for {symbol}', 'success')
    return redirect(url_for('index'))

@app.route('/launch_auth', methods=['POST'])
def launch_auth():
    try:
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
    config = {}
    config_clean = {k: str(v) if isinstance(v, timedelta) else v for k, v in config.items()}
    return render_template('config.html', config=config_clean)

@app.route('/reset_simulation', methods=['POST'])
def reset_simulation():
    try:
        subprocess.run(["python", "init_simulation_db.py"], check=True)
        flash('🌀 Simulation database reset.', 'info')
        return redirect(url_for('simulation'))
    except subprocess.CalledProcessError:
        return "Failed to reset simulation database.", 500

@app.route('/simulation')
def simulation():
    cash = 0.0
    holdings = []
    trades = []
    try:
        conn = sqlite3.connect(SIM_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT cash_balance FROM account WHERE id = 1")
        row = cursor.fetchone()
        if row:
            cash = row["cash_balance"]

        cursor.execute("SELECT * FROM holdings")
        holdings_raw = cursor.fetchall()
        for row in holdings_raw:
            symbol   = row["symbol"]
            qty      = row["qty"]
            avg_cost = row["avg_cost"]

            # Fetch live last price from E*TRADE
            try:
                last_price_val = get_etrade_price(symbol) or 0.0
            except Exception:
                last_price_val = 0.0
            last_price = float(last_price_val)

            # Compute P/L and other fields based on live last_price
            change       = last_price - avg_cost
            change_pct   = (change / avg_cost * 100) if avg_cost else 0.0
            day_gain     = change * qty
            total_gain   = change * qty
            total_pct    = (change / avg_cost * 100) if avg_cost else 0.0
            value        = last_price * qty

            holdings.append({
                'symbol':       symbol,
               'last_price':   f"${last_price:.2f}",
                'change':       f"${change:.2f}",
                'change_pct':   f"{change_pct:.2f}%",
                'qty':          qty,
                'price_paid':   f"${avg_cost:.2f}",
                'day_gain':     f"${day_gain:.2f}",
                'total_gain':   f"${total_gain:.2f}",
                'total_pct':    f"{total_pct:.2f}%",
                'value':        f"${value:.2f}"
            })

        cursor.execute("SELECT * FROM trades")
        history_raw = cursor.fetchall()
        for t in history_raw:
            trades.append({
                'time':      t["time"],
                'symbol':    t["symbol"],
                'action':    t["action"],
                'qty':       t["qty"],
                'price':     f"${t['price']:.2f}",
                'pl':        f"${t['pl']:.2f}"
            })

    except Exception as e:
        print(f"[Simulation Error] {e}")
    finally:
        conn.close()

        return render_template('simulation.html', holdings=holdings, history=trades, cash=cash)

@app.route('/simulation/reset', methods=['POST'])
def sim_reset():
    return ('', 204)

@app.route("/simulation/buy", methods=["POST"])
def simulation_buy():
    data = request.get_json()
    symbol = data.get("symbol")
    qty = int(data.get("qty", 1))
    from services.etrade_service import get_etrade_price
    price = get_etrade_price(symbol)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(SIM_DB)
    cursor = conn.cursor()

    existing = cursor.execute("SELECT qty, avg_cost FROM holdings WHERE symbol = ?", (symbol,)).fetchone()
    if existing:
        old_qty, old_cost = existing
        total_qty = old_qty + qty
        new_avg = ((old_cost * old_qty) + (price * qty)) / total_qty
    print(f"📦 Buying {qty} shares of {symbol} at price: {price}")
    if price is None:
        return "Price is missing", 400
    
        cursor.execute("UPDATE holdings SET qty = ?, avg_cost = ? WHERE symbol = ?", (total_qty, new_avg, symbol))
    else:
        cursor.execute("INSERT INTO holdings (symbol, qty, avg_cost) VALUES (?, ?, ?)", (symbol, qty, price))

    cursor.execute("INSERT INTO trade_history (timestamp, symbol, action, qty, price) VALUES (?, ?, 'BUY', ?, ?)",
                   (timestamp, symbol, qty, price))

    cursor.execute("UPDATE account SET cash_balance = cash_balance - ? WHERE id = 1", (price * qty,))
    conn.commit()
    conn.close()
    return jsonify(success=True)

@app.route('/news/<symbol>')
def news_for_symbol(symbol):
    # … fetch from news_service, return JSON or render a template …
    headlines = fetch_latest_headlines(symbol)
    sentiment = news_sentiment(symbol)
    return jsonify({'headlines': headlines, 'sentiment': sentiment})

if __name__ == '__main__':
    app.run(debug=True)


