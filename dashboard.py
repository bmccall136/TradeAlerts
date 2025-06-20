
import os
import subprocess
import threading
import time
import platform
import sqlite3
import io
import csv
from pathlib import Path
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from collections import namedtuple

from flask import (
    Flask, request, render_template, redirect,
    url_for, flash, jsonify, Response as FlaskResponse
)

# helpers to initialize DBs
from backtest_helpers import init_backtest_db

# simulation services
from services.simulation_service import run_simulation_loop, stop_simulation
from services.trading_helpers import (
    nuke_simulation_db, get_cash, get_holdings,
    get_realized_pl, get_trades,
    buy_stock, sell_stock, fetch_live_data
)

DB_PATH     = os.path.join(os.getcwd(), 'alerts.db')
SIM_DB      = os.path.join(os.getcwd(), 'simulation.db')
BACKTEST_DB = os.path.join(os.getcwd(), 'backtest.db')

app = Flask(__name__)
app.secret_key = os.environ.get('PokeChop!', 'PokeChop!')

TIMEFRAME_DELTAS = {
    '1mo': {'months': 1},
    '3mo': {'months': 3},
    '6mo': {'months': 6},
    '1y' : {'years': 1},
}

def extract_backtest_settings(args):
    # figure out end_date = today, start_date = today - timeframe
    tf = args.get('timeframe', '6mo')
    today = date.today()
    delta = TIMEFRAME_DELTAS.get(tf, {'months': 6})
    start = today - relativedelta(**delta)
    end   = today

    return BacktestSettings(
        start_date        = args.get('start_date', start.isoformat()),
        end_date          = args.get('end_date',   end.isoformat()),
        starting_cash     = int(args.get('starting_cash',10000)),
        max_per_trade     = int(args.get('max_per_trade',1000)),
        timeframe         = tf,
        trailing_stop_pct = float(args.get('trailing_stop_pct',0.0)),
        sell_after_days   = int(args.get('sell_after_days')) if args.get('sell_after_days') else None,
        sma_on            = 'sma_on' in args,
        rsi_on            = 'rsi_on' in args,
        macd_on           = 'macd_on' in args,
        bb_on             = 'bb_on' in args,
        vol_on            = 'vol_on' in args,
        vwap_on           = 'vwap_on' in args,
        news_on           = 'news_on' in args,
        sma_length        = int(args.get('sma_length',20)),
        rsi_len           = int(args.get('rsi_len',14)),
        rsi_overbought    = int(args.get('rsi_overbought',70)),
        rsi_oversold      = int(args.get('rsi_oversold',30)),
        macd_fast         = int(args.get('macd_fast',12)),
        macd_slow         = int(args.get('macd_slow',26)),
        macd_signal       = int(args.get('macd_signal',9)),
        bb_length         = int(args.get('bb_length',20)),
        bb_std            = float(args.get('bb_std',2.0)),
        vol_multiplier    = float(args.get('vol_multiplier',1.0)),
        vwap_threshold    = float(args.get('vwap_threshold',0.0)),
        single_entry_only = 'single_entry_only' in args,
        use_trailing_stop = 'use_trailing_stop' in args,
    )

SimulationSettings = namedtuple('SimulationSettings', [
  # toggles
  'sma_on','rsi_on','macd_on','bb_on','vol_on','vwap_on','news_on',
  # numeric indicators
  'sma_length','rsi_len','rsi_overbought','rsi_oversold',
  'macd_fast','macd_slow','macd_signal',
  'bb_length','bb_std','vol_multiplier','vwap_threshold',
  # extra entry/exit flags
  'rsi_slope_on','macd_hist_on','bb_breakout_on',
  # exit parameters
  'trailing_stop_pct','sell_after_days',
  # behavioral flags
  'single_entry_only','use_trailing_stop'
])

def extract_simulation_settings(args):
    return SimulationSettings(
      sma_on            = 'sma_on' in args,
      rsi_on            = 'rsi_on' in args,
      macd_on           = 'macd_on' in args,
      bb_on             = 'bb_on' in args,
      vol_on            = 'vol_on' in args,
      vwap_on           = 'vwap_on' in args,
      news_on           = 'news_on' in args,
      sma_length        = int(args.get('sma_length', 20)),
      rsi_len           = int(args.get('rsi_len', 14)),
      rsi_overbought    = int(args.get('rsi_overbought', 70)),
      rsi_oversold      = int(args.get('rsi_oversold', 30)),
      macd_fast         = int(args.get('macd_fast', 12)),
      macd_slow         = int(args.get('macd_slow', 26)),
      macd_signal       = int(args.get('macd_signal', 9)),
      bb_length         = int(args.get('bb_length', 20)),
      bb_std            = float(args.get('bb_std', 2.0)),
      vol_multiplier    = float(args.get('vol_multiplier', 1.0)),
      vwap_threshold    = float(args.get('vwap_threshold', 0.0)),
      rsi_slope_on      = 'rsi_slope_on' in args,
      macd_hist_on      = 'macd_hist_on' in args,
      bb_breakout_on    = 'bb_breakout_on' in args,
      trailing_stop_pct = float(args.get('trailing_stop_pct', 0.0)),
      sell_after_days   = int(args.get('sell_after_days')) if args.get('sell_after_days') else None,
      single_entry_only = 'single_entry_only' in args,
      use_trailing_stop = 'use_trailing_stop' in args,
    )

# 2) BacktestSettings + extractor
from collections import namedtuple
BacktestSettings = namedtuple('BacktestSettings', [
    'start_date','end_date','starting_cash','max_per_trade',
    'timeframe','trailing_stop_pct','sell_after_days',
    # toggles
    'sma_on','rsi_on','macd_on','bb_on','vol_on','vwap_on','news_on',
    # indicator params
    
    
    
    'sma_length','rsi_len','rsi_overbought','rsi_oversold',
    'macd_fast','macd_slow','macd_signal',
    'bb_length','bb_std','vol_multiplier','vwap_threshold',
    # new behavioral flags
    'single_entry_only','use_trailing_stop',
])
def load_your_symbols():
    # reads your SP500 list
    with open('sp500_symbols.txt') as f:
        return [line.strip() for line in f if line.strip()]

# 3) Register the /backtest route
import json
import sqlite3
from flask import request, render_template
from services.backtest_service import run_full_backtest
from flask import request, render_template, flash, redirect, url_for
import sqlite3, json, sys
from datetime import datetime
from backtest_helpers import extract_backtest_settings

BACKTEST_DB = 'backtest.db'

@app.route('/backtest')
def backtest_view():
    settings = extract_backtest_settings(request.args)
    # load symbols
    with open('sp500_symbols.txt') as f:
        symbols = [s.strip() for s in f if s.strip()]

    trades = []
    summary = {
        'total_pnl': 0.0,
        'num_trades': 0,
        'wins': 0,
        'losses': 0,
        'by_symbol': {}
    }

    if request.args.get('run_full') == '1':
        start_ts = datetime.utcnow()
        print(f"[Backtest] START {start_ts.isoformat()}", file=sys.stdout)
        try:
            trades, summary = run_backtest(settings, symbols)
            end_ts = datetime.utcnow()
            print(f"[Backtest] COMPLETE (took {end_ts-start_ts})", file=sys.stdout)
            flash(f"✅ Backtest completed in {end_ts - start_ts}")
        except Exception as e:
            flash(f"❌ Backtest error: {e}")
            print(f"[Backtest] ERROR: {e}", file=sys.stderr)

    return render_template(
        'backtest.html',
        trades=trades,
        summary=summary,
        settings=settings,
        net_return=summary['total_pnl']
    )
# near the top of Dashboard.py, alongside your other flask imports
import io
import csv
import subprocess
import sqlite3
from flask import (
    flash,
    redirect,
    url_for,
    request,
    Response,
)

from flask import request, redirect, url_for, flash
import subprocess

import json
from datetime import datetime
import sqlite3
from flask import flash, render_template
# near the top, after imports
_is_scanner_running = False

@app.route('/scanner_status')
def scanner_status():
    return jsonify(running=_is_scanner_running)

@app.route('/run_backtest', methods=['POST'])
def run_backtest_route():
    # 1) Grab settings & symbols
    settings = extract_backtest_settings(request.form)
    symbols  = load_your_symbols()

    # 2) Reset DB
    init_backtest_db()

    # 3) Run backtest
    trades, summary = run_full_backtest(settings, symbols)

    # 4) Log this run into backtest_runs & backtest_trades
    conn = sqlite3.connect(BACKTEST_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 4a) Insert the run
    cur.execute(
        "INSERT INTO backtest_runs (started_at, settings_json) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), json.dumps(settings._asdict()))
    )
    run_id = cur.lastrowid

    # 4b) Insert each trade
    for t in trades:
        cur.execute("""
          INSERT INTO backtest_trades
            (run_id, symbol, date, action, price, qty, pnl)
          VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
          run_id,
          t['symbol'],
          t['date'],
          t['action'],
          t['price'],
          t['qty'],
          t['pnl']
        ))

    conn.commit()
    conn.close()

    # 5) Notify & render
    flash("✅ Backtest run complete!")
    return render_template(
        'backtest.html',
        trades=trades,
        summary=summary,
        settings=settings,
        net_return=summary['total_pnl']
    )

@app.route('/start_scanner', methods=['POST'])
def start_scanner():
    global _is_scanner_running
    settings = extract_simulation_settings(request.form)
    _is_scanner_running = True

    t = threading.Thread(
        target=run_simulation_loop,
        args=(settings,),
        daemon=True
    )
    t.start()
    flash("▶️ Simulation started", "success")
    return redirect(url_for('simulation'))


@app.route('/stop_scanner', methods=['POST'])
def stop_scanner():
    global _is_scanner_running
    stop_simulation()
    _is_scanner_running = False
    flash("⛔ Simulation stopped", "danger")
    return redirect(url_for('simulation'))

@app.route('/run-checkpoint')
def run_checkpoint():
    bat_path = os.path.join(os.getcwd(), 'checkpoint.bat')  # Adjust path if needed
    try:
        subprocess.Popen(['cmd.exe', '/c', 'start', 'cmd.exe', '/k', bat_path], shell=True)
        return redirect(url_for('index'))
    except Exception as e:
        return f"Error executing batch: {e}", 500
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
# ── 2) run_backtest: wipe + run + log to DB ────────────────────────────────────

# at top of Dashboard.py
BACKTEST_DB = os.path.join(os.getcwd(), 'backtest.db')


# ────────────────────────────────────────────────────────
# 2) RUN BACKTEST (wipe + run + log)
# ────────────────────────────────────────────────────────

@app.route('/reset_backtest', methods=['POST'])
def reset_backtest():
    subprocess.run(['python','init_backtest_db.py'], check=True)
    flash('✅ Backtest DB reset!', 'success')
    return redirect(url_for('backtest_view'))



@app.route('/simulation')
def simulation():
    cash          = get_cash()
    realized_pnl  = get_realized_pl()

    raw_holdings = get_holdings()
    formatted_holdings = []
    unrealized_pnl = 0.0
    for h in raw_holdings:
        unrealized_pnl += h['total_gain']
        formatted_holdings.append({
            'symbol':     h['symbol'],
            'last_price': h['last_price'],
            'qty':        h['qty'],
            'day_gain':   h['day_gain'],
            'total_gain': h['total_gain'],
            'value':      h['value'],
        })

    raw_trades      = get_trades()
    formatted_trades = []
    for t in raw_trades:
        formatted_trades.append({
            'time':   t['trade_time'],
            'symbol': t['symbol'],
            'action': t['action'],
            'qty':    t['qty'],
            'price':  t['price'],
            'pl':     t['pnl'],
        })

    return render_template(
        'simulation.html',
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        holdings=formatted_holdings,
        history=formatted_trades
    )

@app.route('/export/simulation')
def export_simulation():
    cash         = get_cash()
    holdings     = get_holdings()
    trades       = get_trades()
    si = io.StringIO()
    cw = csv.writer(si)

    cw.writerow(['Cash', cash])
    cw.writerow([])
    cw.writerow(['-- HOLDINGS --'])
    cw.writerow(['symbol','qty','last_price','value','day_gain','total_gain'])
    for h in holdings:
        cw.writerow([h['symbol'], h['qty'], h['last_price'], h['value'], h['day_gain'], h['total_gain']])
    cw.writerow([])
    cw.writerow(['-- TRADES --'])
    cw.writerow(['time','symbol','action','qty','price','pl'])
    for t in trades:
        cw.writerow([t['time'], t['symbol'], t['action'], t['qty'], t['price'], t['pl']])

    resp = make_response(si.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=simulation.csv"
    resp.headers["Content-type"] = "text/csv"
    return resp

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



    flash('✅ Backtest run complete!', 'success')
    return redirect(
        url_for('backtest_view', **request.form)
    )
from flask import flash, redirect, url_for
import subprocess

@app.route('/reset_simulation', methods=['POST'])
def reset_simulation():
    try:
        # if you have a script to re-init your simulation DB:
        subprocess.run(
            ['python', 'init_simulation_db.py'],
            check=True, capture_output=True, text=True, timeout=10
        )
        flash('✅ Simulation database reset')
    except Exception as e:
        flash(f'❌ Failed to reset simulation: {e}')
    return redirect(url_for('simulation'))

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
import io, csv
from flask import Response

@app.route('/export_alerts')
def export_alerts():
    # pull your alerts from the DB (or your service)
    alerts = get_alerts()  

    # Build CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Symbol', 'Last Match', 'Filters'])

    # Adjust these keys to whatever your alert dict actually uses:
    for a in alerts:
        last = a.get('last_match_time')  # or .get('time') if that's your field
        filters = ";".join(a.get('matched_filters', []))
        writer.writerow([ a['symbol'], last, filters ])

    # Return as downloadable attachment
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={
            "Content-Disposition": "attachment;filename=alerts.csv"
        }
    )

import io, csv
import json
import sqlite3
from flask import Response, flash, redirect, url_for

@app.route('/export_backtest')
def export_backtest():
    # 1) Rebuild the BacktestSettings from the same query-string
    settings = extract_backtest_settings(request.args)

    # 2) Open your backtest.db
    conn = sqlite3.connect(BACKTEST_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 3) Grab the most recent run_id (order by started_at, not timestamp)
    row = cur.execute(
        "SELECT id FROM backtest_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        flash('❌ No backtest run in the database to export.', 'warning')
        return redirect(url_for('backtest_view'))
    run_id = row['id']

    # 4) Pull all trade rows for that run
    trades = cur.execute(
        """SELECT symbol, date, action, price, qty, pnl
           FROM backtest_trades
           WHERE run_id = ?
           ORDER BY date""",
        (run_id,)
    ).fetchall()
    conn.close()

    # 5) Build the CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)

    # 5a) Dump your settings first
    writer.writerow(["# Backtest Settings"])
    for key, val in settings._asdict().items():
        writer.writerow([key, val])
    writer.writerow([])

    # 5b) Dump the trades
    writer.writerow(["Symbol","Date","Type","Price","Qty","P/L"])
    for t in trades:
        writer.writerow([
            t["symbol"],
            t["date"],
            t["action"],
            t["price"],
            t["qty"],
            t["pnl"]
        ])

    # 6) Return as an attachment
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition":"attachment;filename=backtest.csv"},
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
# ── Background scanner loop ─────────────────────────────────────────────────
def scanner_loop():
    """
    Background thread that runs your scanner every 60 seconds.
    """
    while True:
        try:
            from scanner import run_scan
            run_scan()
            print("[Scanner] ✅ Ran scan loop")
        except Exception as e:
            print(f"[Scanner] ❌ Scanner error: {e}")
        time.sleep(60)
if __name__ == "__main__":
    # spin up the scanner in a daemon thread
    threading.Thread(target=scanner_loop, daemon=True).start()

    # start Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
import json
from datetime import datetime
