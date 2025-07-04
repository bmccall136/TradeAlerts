import os
import time
import json
import subprocess
import threading
import sqlite3
import logging
import io
import csv
from requests.exceptions import HTTPError
from pathlib import Path
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from collections import namedtuple
from types import SimpleNamespace
import logging
logger = logging.getLogger(__name__)

from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    jsonify,
    Response as FlaskResponse,
    session
)

# ── 1) Load your .env first ──────────────────────────────────
from dotenv import load_dotenv, set_key
load_dotenv()

# ── 2) All other imports ────────────────────────────────────
from services.alert_service import (
    get_all_indicator_settings,
    update_indicator_settings,
    get_alerts,
    insert_alert,
    generate_sparkline
)
from services.trading_helpers import (
    nuke_simulation_db,
    set_cash,
    get_holdings,
    get_trades,
    get_realized_pl,
    get_unrealized_pl,
    get_cash,
    buy_stock,
    sell_stock,
    setup_simulation_db,
    init_backtest_db,
)
# Dashboard.py, at the top
from services.backtest_service   import run_full_backtest
from services.simulation_service import run_simulation_loop, stop_simulation
from services.market_service     import fetch_data_with_timeout
from services.etrade_service     import fetch_etrade_quote
try:
    from services.broker_api import fetch_live_data
except ImportError:
    fetch_live_data = None

# ── DB file paths ───────────────────────────────────────────
DB_PATH     = os.path.join(os.getcwd(), 'alerts.db')
SIM_DB      = os.path.join(os.getcwd(), 'simulation.db')
BACKTEST_DB = os.path.join(os.getcwd(), 'backtest.db')

# ── Flask app ───────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'supersecret')

# ── Logging configuration ───────────────────────────────────
import logging

# get your sim logger and make it print to the console at DEBUG
sim_logger = logging.getLogger('sim')
sim_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-4s %(name)s: %(message)s"
))
sim_logger.addHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-5s %(name)s: %(message)s'
)
for lib in ('werkzeug', 'urllib3', 'requests_oauthlib', 'oauthlib', 'yfinance', 'peewee'):
    logging.getLogger(lib).setLevel(logging.WARNING)

# ── Timeframe presets & simulation defaults ─────────────────
TIMEFRAME_DELTAS = {
    '1mo': {'months': 1},
    '3mo': {'months': 3},
    '6mo': {'months': 6},
    '1y' : {'years': 1},
}
DEFAULT_STARTING_CASH = 10000.0
DEFAULT_MAX_PER_TRADE = 1000.0

# ── E*TRADE OAuth configuration (production only) ──────────
# Keys filled in directly as provided
CONSUMER_KEY       = '1e0978925ddea6a6addb5436e6ff2164'
CONSUMER_SECRET    = '0fdac4a22a68112d7e855281bab9df70af85cfd023206d15d75bcf51f1390bc2'
OAUTH_TOKEN        = 'mcjsKyZ+GEfimgLRexsERoevbOQ9EVRrN7iJ/I13Dwg='
OAUTH_TOKEN_SECRET = 'YFDwu7K23oWft+n+0TongPACdDzkQR0oB6xPug3GpOw='
OAUTH_HOST         = 'https://api.etrade.com'
REQUEST_TOKEN_URL  = f'{OAUTH_HOST}/oauth/request_token'
ACCESS_TOKEN_URL   = f'{OAUTH_HOST}/oauth/access_token'
AUTHORIZE_URL      = 'https://us.etrade.com/e/t/etws/authorize'
ENV_PATH           = os.path.join(os.path.dirname(__file__), '.env')
KEY_OAUTH_TOKEN        = 'OAUTH_TOKEN'
KEY_OAUTH_TOKEN_SECRET = 'OAUTH_TOKEN_SECRET'

# ── OAuth routes ────────────────────────────────────────────
from flask import render_template, session, redirect, url_for, flash
from requests_oauthlib import OAuth1Session

@app.route('/etrade/auth')
def etrade_start_auth():
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri='oob'   # out-of-band
    )
    resp = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    session['req_token']  = resp['oauth_token']
    session['req_secret'] = resp['oauth_token_secret']
    auth_url = f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resp['oauth_token']}"
    return render_template('etrade_pin.html', auth_url=auth_url)

@app.route('/etrade/pin', methods=['POST'])
def etrade_handle_pin():
    # Grab the PIN (oauth_verifier) from the form
    verifier   = request.form['oauth_verifier']
    req_token  = session.pop('req_token', None)
    req_secret = session.pop('req_secret', None)

    # Exchange for real access tokens
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=req_token,
        resource_owner_secret=req_secret,
        verifier=verifier
    )
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

    # Persist into .env so fetch_etrade_quote() works
    set_key(ENV_PATH, KEY_OAUTH_TOKEN,        tokens['oauth_token'])
    set_key(ENV_PATH, KEY_OAUTH_TOKEN_SECRET, tokens['oauth_token_secret'])

    flash('✅ E*TRADE authenticated!', 'success')
    return redirect(url_for('index'))

@app.route('/etrade/callback')
def etrade_handle_callback():
    """Step 2: Exchange verifier for access tokens & persist."""
    verifier   = request.args.get('oauth_verifier')
    req_token  = session.pop('req_token', None)
    req_secret = session.pop('req_secret', None)

    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=req_token,
        resource_owner_secret=req_secret,
        verifier=verifier
    )
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

    # Persist into .env
    set_key(ENV_PATH, KEY_OAUTH_TOKEN,        tokens['oauth_token'])
    set_key(ENV_PATH, KEY_OAUTH_TOKEN_SECRET, tokens['oauth_token_secret'])

    flash('✅ E*TRADE authenticated!', 'success')
    return redirect(url_for('index'))

# ── …then the rest of your routes and logic follow below…


def fetch_current_price(symbol):
    try:
        price = fetch_etrade_quote(symbol)
        return float(price)
    except Exception as e:
        logging.warning(f"[PRICE] {symbol}: E*TRADE fetch failed ({e})")
        raise


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
        # ── NEW ──
        stop_loss_pct   = float(args.get('stop_loss_pct',   0.0)),
        take_profit_pct = float(args.get('take_profit_pct', 0.0)),
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
    'single_entry_only','use_trailing_stop',
    # cash settings
   'starting_cash','max_per_trade',
   'stop_loss_pct','take_profit_pct',
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
      # if the form field comes back empty, fall back to 0.0 instead of trying to float('')
      trailing_stop_pct = float(args.get('trailing_stop_pct') or 0.0),
      sell_after_days   = int(args.get('sell_after_days')) if args.get('sell_after_days') else None,
      single_entry_only = 'single_entry_only' in args,
      use_trailing_stop = 'use_trailing_stop' in args,
      # ── here are the two you were missing ──
      starting_cash     = float(args.get('starting_cash', 10000)),
      max_per_trade     = float(args.get('max_per_trade', 1000)),
      stop_loss_pct     = float(args.get('stop_loss_pct')  or 0.0),
      take_profit_pct   = float(args.get('take_profit_pct') or 0.0),
    )

BacktestSettings = namedtuple('BacktestSettings', [
    'start_date','end_date','starting_cash','max_per_trade',
    'timeframe','trailing_stop_pct','sell_after_days',
    'sma_on','rsi_on','macd_on','bb_on','vol_on','vwap_on','news_on',
    'sma_length','rsi_len','rsi_overbought','rsi_oversold',
    'macd_fast','macd_slow','macd_signal',
    'bb_length','bb_std','vol_multiplier','vwap_threshold',
    'single_entry_only','use_trailing_stop',
    # ── NEW ──
    'stop_loss_pct','take_profit_pct'
])
def load_your_symbols():
    # reads your SP500 list
    with open('sp500_symbols.txt') as f:
        return [line.strip() for line in f if line.strip()]
        logging.debug(f"[sim] symbols to scan: {symbols[:5]}… ({len(symbols)} total)")


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

    # 3) Run backtest (safely handle None or unexpected result)
    result = run_full_backtest(settings, symbols)
    if not (isinstance(result, tuple) and len(result) == 2):
        logger.warning("run_full_backtest returned unexpected result: %r", result)
        flash("⚠️ Backtest didn’t produce any data—showing an empty run", "warning")
        trades = []
        summary = {
            'total_pnl': 0.0,
            'num_trades': 0,
            'wins': 0,
            'losses': 0,
            'by_symbol': {}
        }
    else:
        trades, summary = result

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
        cur.execute(
            """
            INSERT INTO backtest_trades
              (run_id, symbol, date, action, price, qty, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                t['symbol'],
                t['date'],
                t['action'],
                t['price'],
                t['qty'],
                t['pnl']
            )
        )

    conn.commit()
    conn.close()

    # 5) Notify & render
    flash("✅ Backtest run complete!")
    return render_template(
        'backtest.html',
        trades=trades,
        summary=summary,
        settings=settings,
        net_return=summary.get('total_pnl', 0.0)
    )


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

def simulation():
    raw_trades       = get_trades()
    formatted_trades = []

    # DEBUG: inspect first trade to see its shape
    if raw_trades:
        print("🔍 raw_trades[0] =", raw_trades[0])

    for t in raw_trades:
        # Case A: dict
        if isinstance(t, dict):
            trade_time = t.get('trade_time') or t.get('time')
            symbol     = t.get('symbol')
            action     = t.get('action')
            qty        = t.get('qty')
            # coerce to numeric so Jinja sees real numbers
            price_str  = t.get('price')
            pnl_str    = t.get('pnl') or t.get('pl')
            price = float(t.get('price'))
            pl    = float(t.get('pnl') or t.get('pl'))

        # Case B: tuple
        elif isinstance(t, tuple):
            # Adjust this unpack order to match your service’s return
            trade_time, symbol, action, qty, price, pnl = t

        else:
            # Unexpected type; skip
            continue

    formatted_trades.append({
        'time':   t.get('time'),
        'symbol': t.get('symbol'),
        'action': t.get('action'),
        'qty':    int(t.get('qty')),
        'price':  price,
        'pl':     pl,
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
    cash     = get_cash()
    holdings = get_holdings()
    trades   = get_trades()

    si = io.StringIO()
    cw = csv.writer(si)

    cw.writerow(['Cash', cash])
    cw.writerow([])
    cw.writerow(['-- HOLDINGS --'])
    cw.writerow(['symbol','qty','last_price','value','day_gain','total_gain'])
    for h in holdings:
        try:
            live = fetch_etrade_quote(h['symbol'])
            app.logger.info(f"[PRICE] {h['symbol']}: E*TRADE price = {live}")
            h['last_price'] = round(live, 2)
            # recalc all the P/L
            change     = h['last_price'] - h['price_paid']
            h['change']     = round(change, 2)
            h['change_pct'] = round((change / h['price_paid']*100) if h['price_paid'] else 0, 1)
            h['total_gain'] = round(change * h['qty'], 2)
            h['day_gain']   = h['total_gain']  # or however you define “day”
            h['value']      = round(h['last_price'] * h['qty'], 2)
        except Exception as e:
            app.logger.warning(f"[PRICE] {h['symbol']} fetch failed: {e}")

    cw.writerow([])
    cw.writerow(['-- TRADES --'])
    cw.writerow(['time','symbol','action','qty','price','pl'])
    for t in trades:
        cw.writerow([
            t['time'],
            t['symbol'],
            t['action'],
            t['qty'],
            t['price'],
            abs(t['pl'])
        ])

    resp = make_response(si.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=simulation.csv"
    resp.headers["Content-type"] = "text/csv"
    return resp
# ── Main Simulation Page ──

@app.route('/start_scanner', methods=['POST'])
def start_scanner():
     global _is_scanner_running
     # ── ALWAYS clear out the old sim state ──
     nuke_simulation_db()

     # seed your starting cash (pulled from the form on Alerts)
     starting_cash   = float(request.form.get('starting_cash', 10000))
     set_cash(starting_cash)
     _is_scanner_running = True

     # also grab max_per_trade so we can hand it back to /simulation
     max_per_trade = float(request.form.get('max_per_trade', 1000))

     # now start the thread as before…
     _is_scanner_running = True
     t = threading.Thread(
         target=run_simulation_loop,
         args=(extract_simulation_settings(request.form),),
         daemon=True
     )
     t.start()
     flash("▶️ Simulation started (DB nuked first)", "success")
     # send the user back to the live simulation dashboard, passing our two form values
     return redirect(url_for(
        'simulation',
        starting_cash=starting_cash,
        max_per_trade=max_per_trade
    ))

# near the top of Dashboard.py
DEFAULT_STARTING_CASH = 10000.0
DEFAULT_MAX_PER_TRADE = 1000.0

from services.trading_helpers import (
    get_cash, get_holdings, get_trades,
    get_unrealized_pl, get_realized_pl
)
from flask import request
from services.trading_helpers import get_trades, get_cash, get_realized_pl, get_unrealized_pl
from services.market_service import fetch_data_with_timeout
# at the very top, with your other imports
from services.trading_helpers import get_trades

from services.trading_helpers import get_trades

# at the top of Dashboard.py, make sure cost_basis is defined as we did earlier
def cost_basis(symbol):
    trades = get_trades()
    total_qty  = 0
    total_cost = 0.0
    for t in trades:
        if isinstance(t, dict):
            sym    = t.get('symbol')
            action = t.get('action')
            qty    = t.get('qty', 0)
            price  = t.get('price', 0.0)
        elif isinstance(t, (tuple, list)):
            # adjust unpack order if your tuple is different
            _, sym, action, qty, price, *_ = t
        else:
            continue

        if sym == symbol and action.upper() == 'BUY':
            total_qty  += qty
            total_cost += qty * price

    return (total_cost / total_qty) if total_qty else 0.0

@app.route('/simulation')
def simulation():
    cash = get_cash()
    raw_holdings = get_holdings()
    formatted_holdings = []
    unrealized_pnl = sum(h['total_gain'] for h in formatted_holdings)
    realized_pnl   = get_realized_pl()

    for symbol, qty, avg_cost, db_last_price in raw_holdings:
        try:
            live_price = fetch_etrade_quote(symbol)
            logger.info(f"[PRICE] {symbol}: live price = {live_price}")
        except HTTPError as e:
            # if it’s a 401, kick off the OAuth dance
            if e.response is not None and e.response.status_code == 401:
                logger.warning(f"[PRICE] {symbol}: 401 → redirecting to auth")
                return redirect(url_for('etrade_start_auth'))
            # otherwise just fall back to the DB price
            logger.warning(f"[PRICE] {symbol}: live fetch failed ({e})")
            live_price = db_last_price

        value      = live_price * qty
        total_gain = (live_price - avg_cost) * qty
        change_pct = (total_gain / (avg_cost * qty) * 100) if avg_cost else 0.0
        day_gain   = total_gain

        formatted_holdings.append({
            'symbol'     : symbol,
            'qty'        : qty,
            'price_paid' : avg_cost,
            'last_price' : live_price,
            'day_gain'   : day_gain,
            'total_gain' : total_gain,
            'change_pct' : change_pct,
            'value'      : value,
        })

    # …the rest of formatting trades, pulling P/L, then render_template…


    # ── C) format trades
    raw_trades = get_trades()
    formatted_trades = []
    for t in raw_trades:
        if isinstance(t, dict):
            trade_time = t.get('time') or t.get('trade_time')
            symbol     = t['symbol']
            action     = t['action']
            qty        = t['qty']
            price      = float(t.get('price', 0))
            pl         = float(t.get('pnl') or t.get('pl') or 0)
        else:
            trade_time, symbol, action, qty, price, pl = t

        formatted_trades.append({
            'time'   : trade_time,
            'symbol' : symbol,
            'action' : action,
            'qty'    : qty,
            'price'  : price,
            'pl'     : pl,
        })

    # ── D) echo back your form-supplied settings
    starting_cash = float(request.args.get('starting_cash', DEFAULT_STARTING_CASH))
    max_per_trade = float(request.args.get('max_per_trade',   DEFAULT_MAX_PER_TRADE))

    # ── E) compute P/L totals
    unrealized_pnl = get_unrealized_pl()
    realized_pnl   = get_realized_pl()

    # ── F) render once, with everything defined
    return render_template(
        'simulation.html',
        cash=cash,
        holdings=formatted_holdings,
        history=formatted_trades,
        starting_cash=starting_cash,
        max_per_trade=max_per_trade,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        is_running=_is_scanner_running
    )

@app.route("/simulation/buy", methods=["POST"])
def simulation_buy():
    try:
        data   = request.get_json(force=True)
        symbol = data.get("symbol")
        qty    = int(data.get("qty", 1))

        # 1) Validate
        if not symbol or qty <= 0:
            return jsonify(success=False, error="Invalid symbol or quantity"), 400
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

@app.route('/simulation/reset', methods=['POST'])
def reset_simulation():
    # read the default starting cash from a hidden form field or query string
    default_cash = float(request.form.get('starting_cash', 10000))
    set_cash(default_cash)
    # clear out any trades/holdings if you want
    nuke_simulation_db()
    flash(f"Simulation reset: cash back to ${default_cash:,.2f}", "info")
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # ← add debug=True (and use_reloader if you want)
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=True)

