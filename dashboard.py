from pathlib import Path
import os
import subprocess
import sqlite3
import threading
import time

scanner_active = False  # Global flag

from datetime import datetime, timedelta
from flask import request, render_template
from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, jsonify
)

# ALERTS & INDICATOR SETTINGS
from services.alert_service import (
    save_indicator_settings,
    get_all_indicator_settings,
    get_alerts,
    clear_all_alerts,
    insert_alert,
)
from functools import wraps
from flask import request, Response

USERNAME = os.environ.get("BASIC_AUTH_USER", "admin")
PASSWORD = os.environ.get("BASIC_AUTH_PASS", "Shadow!")

def check_auth(user, pw):
    return user == USERNAME and pw == PASSWORD

def authenticate():
    return Response("⛔ Authentication Required", 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# NEWS
from services.news_service import fetch_latest_headlines, fetch_sentiment_for

# E*TRADE
from services.etrade_service import get_etrade_price

# SIMULATION
from services.simulation_service import (
    buy_stock,
    get_holdings,
    get_cash,
    get_realized_pl,
    get_trades,
    sell_stock,
    nuke_simulation_db   # if you need to reset simulation DB
)

# BACKTEST
from services.backtest_service import backtest

# MARKET SCANNER
from services.market_service import analyze_symbol, get_symbols

app = Flask(__name__)
app.secret_key = "replace_with_your_secret_key"

DB_PATH  = 'alerts.db'
SIM_DB   = 'simulation.db'  # Must match SIM_DB in simulation_service.py
import subprocess
import platform

def scanner_loop():
    global scanner_active
    scanner_active = True
    while True:
        try:
            from scanner import run_scan
            run_scan()
            print("[Scanner] ✅ Ran scan loop")
        except Exception as e:
            print(f"[Scanner] ❌ Error: {e}")
        time.sleep(60)
        
@app.route("/start_scanner", methods=["POST"])
def start_scanner():
    if platform.system() == "Windows":
        subprocess.Popen(["start", "start_scanner.bat"], shell=True)
    return redirect(url_for('index'))

@app.route("/stop_scanner", methods=["POST"])
def stop_scanner():
    if platform.system() == "Windows":
        subprocess.call(["stop_scanner.bat"], shell=True)
    return redirect(url_for('index'))

@app.route('/run-checkpoint')
def run_checkpoint():
    bat_path = os.path.join(os.getcwd(), 'checkpoint.bat')  # Adjust path if needed
    try:
        subprocess.Popen(['cmd.exe', '/c', 'start', 'cmd.exe', '/k', bat_path], shell=True)
        return redirect(url_for('index'))
    except Exception as e:
        return f"Error executing batch: {e}", 500

### ────────────── PRELOAD BACKTEST DATA (optional) ────────────── ###
# If you want to run a backtest when the server starts, uncomment below:
# trades, pnl = backtest("AAPL", "2024-01-01", "2024-06-01", initial_cash=10000)
# You can then pass `trades` and `pnl` into a template or store them.


### ────────────── ALERTS (LIST & CLEAR) ────────────── ###

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
    print("✅ /clear_all route hit")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/clear/<int:id>', methods=['POST'])
def clear_alert(id):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM alerts WHERE id=?", (id,))
        conn.commit()
        conn.close()
        print(f"✅ Cleared alert #{id}")
        return jsonify({"success": True})
    except Exception as e:
        print(f"❌ Error clearing alert #{id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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


### ────────────── BACKTEST VIEW ────────────── ###

from flask import request, render_template
from scanner_backtest_service import backtest_scanner
from collections import namedtuple

BacktestSettings = namedtuple('BacktestSettings', [
    'start_date', 'end_date', 'starting_cash', 'max_per_trade',
    'trailing_stop_pct', 'sell_after_days',
    'sma_on', 'rsi_on', 'macd_on', 'bb_on', 'vwap_on', 'news_on'
])

def extract_backtest_settings(args):
    return BacktestSettings(
        start_date=args.get('start_date', '2023-01-01'),
        end_date=args.get('end_date', '2024-01-01'),
        starting_cash=int(args.get('starting_cash', 10000)),
        max_per_trade=int(args.get('max_per_trade', 1000)),
        trailing_stop_pct=float(args.get('trailing_stop_pct', 0.05)),
        sell_after_days=int(args.get('sell_after_days')) if args.get('sell_after_days') else None,
        sma_on='sma_on' in args,
        rsi_on='rsi_on' in args,
        macd_on='macd_on' in args,
        bb_on='bb_on' in args,
        vwap_on='vwap_on' in args,
        news_on='news_on' in args
    )

from flask import request, render_template
from scanner_backtest_service import backtest_scanner
from services.backtest_service import backtest
@app.route('/backtest', methods=['GET'])
def backtest_view():
    args = request.args
    settings = {
        "start_date": args.get("start_date", "2023-01-01"),
        "end_date": args.get("end_date", "2024-01-01"),
        "starting_cash": int(args.get("starting_cash", 10000)),
        "max_per_trade": int(args.get("max_per_trade", 1000)),
        "trailing_stop_pct": float(args.get("trailing_stop_pct", 0.05)),
        "sell_after_days": int(args.get("sell_after_days")) if args.get("sell_after_days") else None,
        "sma_on": 'sma_on' in args,
        "rsi_on": 'rsi_on' in args,
        "macd_on": 'macd_on' in args,
        "bb_on": 'bb_on' in args,
        "vwap_on": 'vwap_on' in args,
        "news_on": 'news_on' in args,
        "rsi_slope_on": 'rsi_slope_on' in args,
        "macd_hist_on": 'macd_hist_on' in args,
        "bb_breakout_on": 'bb_breakout_on' in args,
        "run_full_scan": 'run_full_scan' in args,
        "timeframe": args.get("timeframe", "6mo")
    }

    trades = []
    net_return = 0

    if settings["run_full_scan"]:
        trades = backtest_scanner(
            start_date=settings["start_date"],
            end_date=settings["end_date"],
            initial_cash=settings["starting_cash"],
            max_trade_per_stock=settings["max_per_trade"],
            trailing_stop_pct=settings["trailing_stop_pct"],
            sell_after_days=settings["sell_after_days"],
            sma_on=settings["sma_on"],
            rsi_on=settings["rsi_on"],
            macd_on=settings["macd_on"],
            bb_on=settings["bb_on"],
            vwap_on=settings["vwap_on"],
            news_on=settings["news_on"],
            rsi_slope_on=settings["rsi_slope_on"],
            macd_hist_on=settings["macd_hist_on"],
            bb_breakout_on=settings["bb_breakout_on"]
        )
        net_return = sum(t["pnl"] for t in trades)
    else:
        trades, net_return = backtest(
            symbol="AAPL",
            start_date=settings["start_date"],
            end_date=settings["end_date"],
            initial_cash=settings["starting_cash"],
            max_trade_amount=settings["max_per_trade"],
            sma_on=settings["sma_on"],
            vwap_on=settings["vwap_on"],
            news_on=settings["news_on"]
        )

    return render_template("backtest.html", trades=trades, net_return=net_return, settings=settings)

@app.route('/scanner_backtest', methods=['GET', 'POST'])
def scanner_backtest_view():
    from scanner_backtest_service import backtest_scanner
    trades = []
    summary = None

    if request.method == 'POST':
        form = request.form
        start_date = form.get('start_date')
        end_date = form.get('end_date')
        initial_cash = float(form.get('initial_cash', 10000))
        max_trade = float(form.get('max_trade_per_stock', 1000))
        trailing_stop = float(form.get('trailing_stop_pct', 0.05))
        sell_after_days = int(form.get('sell_after_days')) if form.get('sell_after_days') else None

        sma_on = 'sma_on' in form
        rsi_on = 'rsi_on' in form
        macd_on = 'macd_on' in form
        bb_on = 'bb_on' in form
        vwap_on = 'vwap_on' in form
        news_on = 'news_on' in form

        trades = backtest_scanner(
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            max_trade_per_stock=max_trade,
            trailing_stop_pct=trailing_stop,
            sell_after_days=sell_after_days,
            sma_on=sma_on,
            rsi_on=rsi_on,
            macd_on=macd_on,
            bb_on=bb_on,
            vwap_on=vwap_on,
            news_on=news_on
        )
     
        summary = {
            'total_pnl': round(sum(t['pnl'] for t in trades), 2),
            'num_trades': len(trades),
            'wins': sum(1 for t in trades if t['pnl'] > 0),
            'losses': sum(1 for t in trades if t['pnl'] < 0),
        }

    return render_template('scanner_backtest.html', trades=trades, summary=summary)

@app.route("/health")
def health_check():
    return "OK", 200



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
    success = nuke_simulation_db()
    if success:
        return "Simulation reset!", 200
    else:
        return "Failed to reset simulation database.", 500


@app.route('/simulation')
def simulation():
    # Default fallback values if something goes wrong
    cash               = 0.0
    unrealized_pnl     = 0.0
    realized_pnl       = 0.0
    formatted_holdings = []
    formatted_trades   = []

    try:
        # 1) Current cash & realized P/L
        cash          = get_cash()
        realized_pnl  = get_realized_pl()

        # 2) Gather and format holdings
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

        # 3) Gather and format trade history
        raw_trades = get_trades()
        for t in raw_trades:
            pl_display = f"${t['pnl']:.2f}" if t['pnl'] is not None else "-"
            formatted_trades.append({
                'time':   t['trade_time'],
                'symbol': t['symbol'],
                'action': t['action'],
                'qty':    t['qty'],
                'price':  f"${t['price']:.2f}",
                'pl':     pl_display
            })

    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[Simulation Error] {e}")

    return render_template(
        'simulation.html',
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        holdings=formatted_holdings,
        history=formatted_trades
    )


@app.route("/simulation/buy", methods=["POST"])
def simulation_buy():
    from flask import current_app
    try:
        data   = request.get_json(force=True)
        symbol = data.get("symbol")
        qty    = int(data.get("qty", 1))

        # 1) Validate
        if not symbol or qty <= 0:
            return jsonify(success=False, error="Invalid symbol or quantity"), 400

        # 2) Fetch current price from E*TRADE API
        from services.etrade_service import fetch_etrade_quote
        quote_data = fetch_etrade_quote(symbol)
        if isinstance(quote_data, dict):
            # tweak these keys if your API returns different field names
            price = float(
                quote_data.get("lastTrade") or
                quote_data.get("closePrice") or
                0
            )
        else:
            price = float(quote_data)

        current_app.logger.info(f"💲 Using E*TRADE price for {symbol}: {price}")

        # 3) Perform the buy with the live price
        result = buy_stock(symbol, qty, price)
        if result:
            return jsonify(success=True), 200
        else:
            current_app.logger.error("❌ buy_stock() returned False")
            return jsonify(success=False, error="buy_stock() returned False"), 500

    except Exception as e:
        current_app.logger.exception("🚨 Exception in simulation_buy")
        return jsonify(success=False, error=str(e)), 500


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


from flask import request, redirect, url_for, render_template
from services.alert_service import (
    get_all_indicator_settings,
    update_indicator_settings,
    get_alerts
)

@app.route("/", methods=["GET"])
def index():
    # 1) Load persisted settings (or defaults if first run)
    settings = get_all_indicator_settings()

    # 2) If the user clicked “Apply” (i.e. there's any query-string),
    #    merge those overrides into `settings`, persist, then redirect.
    if request.args:
        # Boolean toggles: checked ⇒ present in request.args
        for toggle in (
            "sma_on","rsi_on","macd_on","bb_on","vol_on",
            "vwap_on","news_on","rsi_slope_on","macd_hist_on","bb_breakout_on"
        ):
            settings[toggle] = (toggle in request.args)

        # Numeric filters: parse back out of the query string
        for field in (
            "sma_length","rsi_len","rsi_overbought","rsi_oversold",
            "macd_fast","macd_slow","macd_signal",
            "bb_length","bb_std","vol_multiplier","vwap_threshold"
        ):
            if field in request.args:
                val = request.args[field]
                # floating‐point for the ones that need it:
                if field in ("bb_std","vol_multiplier","vwap_threshold"):
                    settings[field] = float(val)
                else:
                    settings[field] = int(val)

        # Persist and clean‐URL redirect
        update_indicator_settings(settings)
        return redirect(url_for("index"))

    # 3) No query‐string ⇒ build your alerts with current settings,
    #    update match_count, persist it, then render.
    alerts = get_alerts()
    settings["match_count"] = len(alerts)
    update_indicator_settings(settings)

    return render_template(
        "alerts.html",
        alerts=alerts,
        settings=settings,
        match_count=settings["match_count"]
    )




@app.before_request
def secure_everything():
    if request.path == "/health":
        return  # Allow unauthenticated access to /health
    return require_auth(lambda: None)()  # Apply auth to all other routes


if __name__ == "__main__":
    # Local dev only
    threading.Thread(target=scanner_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)




