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
from services.etrade_service import fetch_etrade_quote
from services.simulation_service import analyze_symbol, _is_market_open
from services.simulation_service import load_simulation_settings

# Path to your JSON config (adjust filename if different)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "simulation_config.json")

import os
import json
import subprocess
import sqlite3
import logging
import io
import csv
import services.label_config as label_config
from requests.exceptions import HTTPError
from pathlib import Path
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from collections import namedtuple
from types import SimpleNamespace
from flask import request, redirect, url_for, render_template
from flask import Flask, render_template, request, redirect, url_for
import pandas as pd

# import all label dicts from centralized config
from services.label_config import (
    timeframe_labels,
    sma_length_labels,
    rsi_len_labels,
    rsi_overbought_labels,
    rsi_oversold_labels,
    macd_fast_labels,
    macd_slow_labels,
    macd_signal_labels,
    bb_length_labels,
    bb_std_labels,
    vol_mult_labels,
    vwap_labels,
    trailing_stop_pct_labels,
    sell_after_days_labels,
)
from dataclasses import dataclass
from typing import Optional
from services.backtest_service import run_full_backtest
from types import SimpleNamespace
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask import request, redirect, url_for, render_template
from services.backtest_service import run_full_backtest
# ─── Load environment variables ───────────────────────────────
from dotenv import load_dotenv, set_key
load_dotenv()

# ─── Core Flask imports ───────────────────────────────────────
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

# ─── Service imports ──────────────────────────────────────────
from services.indicators import (
    compute_atr,
    daily_range_pct,
    gap_up_pct,
    price_above_sma
)
from services.trading_helpers import (
    set_cash,
    get_holdings,
    get_trades,
    get_realized_pl,
    get_unrealized_pl,
    get_cash,
    setup_simulation_db,
    init_backtest_db
)
from services.simulation_service import run_simulation_loop, stop_simulation
from services.settings_service import load_settings, save_settings
from types import SimpleNamespace
from datetime import datetime
from dateutil.relativedelta import relativedelta
from services.market_service import fetch_data_with_timeout
from services.etrade_service import fetch_etrade_quote
from types import SimpleNamespace
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask import request, redirect, url_for, render_template
from services.settings_service import load_settings, save_settings
from services.settings_schema import SimulationSettings, extract_simulation_settings
from services.backtest_service  import run_full_backtest
from services.market_service    import get_symbols
from flask import url_for
import webbrowser
from services.trading_helpers import setup_simulation_db
try:
    from services.broker_api import fetch_live_data
except ImportError:
    fetch_live_data = None
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import io
from types import SimpleNamespace
from flask import Flask, request, send_file, flash, render_template
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from services.trading_helpers import setup_simulation_db
from pathlib import Path

# assuming simulation_config.json lives next to dashboard.py
CONFIG_PATH = Path(__file__).parent / "simulation_config.json"

# before any get_cash()/buy()/sell() calls:
setup_simulation_db()

# ── Dynamic Unicode font registration ────────────────────────────────
if os.name == 'nt':  # Windows
    font_path = r"C:\Windows\Fonts\seguiemj.ttf"     # Segoe UI Emoji
else:                # macOS/Linux
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

try:
    pdfmetrics.registerFont(TTFont('UnicodeFont', font_path))
    unicode_font_name = 'UnicodeFont'
except Exception as e:
    print(f"[WARN] Unicode font load failed ({e}), falling back to Helvetica")
    unicode_font_name = 'Helvetica'
# ─────────────────────────────────────────────────────────────────────

# Pick a Unicode font path based on platform
if os.name == 'nt':  # Windows
    # Segoe UI Emoji ships with Windows 10+ and covers 🚀📊 etc.
    font_path = r"C:\Windows\Fonts\seguiemj.ttf"
else:
    # Linux fallback
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Try to register it; if that fails, fall back to built-in Helvetica
try:
    unicode_font_name = 'UnicodeFont'
except Exception as e:
    print(f"[WARN] Unicode font registration failed ({e}), falling back to Helvetica")
    unicode_font_name = 'Helvetica'

# Register DejaVu Sans (bundled with most systems) for full Unicode support:
# Make a paragraph style that uses DejaVuSans:
unicode_style = ParagraphStyle(
    'Unicode',
    parent=getSampleStyleSheet()['Normal'],
    fontName='DejaVuSans'
)
unicode_title = ParagraphStyle(
    'UnicodeTitle',
    parent=getSampleStyleSheet()['Title'],
    fontName='DejaVuSans',
    fontSize=24,
    alignment=1  # center
)

# near the top of dashboard.py
_is_scanner_running = False
_needs_auth          = False


# ─── Logging configuration ───────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-5s %(name)s: %(message)s'
)

# ─── Flask app setup ─────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'supersecret')
setup_simulation_db()
# ─── Database file paths ─────────────────────────────────────
SIM_DB      = os.path.join(os.getcwd(), 'simulation.db')
BACKTEST_DB = os.path.join(os.getcwd(), 'backtest.db')

# ─── Timeframe presets & simulation defaults ────────────────
TIMEFRAME_DELTAS = {
    '1mo': {'months': 1},
    '3mo': {'months': 3},
    '6mo': {'months': 6},
    '1y' : {'years': 1},
}
DEFAULT_STARTING_CASH = 10000.0
DEFAULT_MAX_PER_TRADE  = 1000.0

# ─── E*TRADE OAuth configuration (production only) ──────────
CONSUMER_KEY       = '1e0978925ddea6a6addb5436e6ff2164'
CONSUMER_SECRET    = '0fdac4a22a68112d7e855281bab9df70af85cfd023206d15d75bcf51f1390bc2'
OAUTH_TOKEN        = 'mcjsKyZ+GEfimgLRexsERoevbOQ9EVRrN7iJ/I13Dwg='
OAUTH_TOKEN_SECRET = 'YFDwu7K23oWft+n+0TongPACdDzkQR0oB6xPug3GpOw='
OAUTH_HOST         = 'https://api.etrade.com'
REQUEST_TOKEN_URL  = f'{OAUTH_HOST}/oauth/request_token'
ACCESS_TOKEN_URL   = f'{OAUTH_HOST}/oauth/access_token'
AUTHORIZE_URL      = 'https://us.etrade.com/e/t/etws/authorize'
ENV_PATH           = os.path.join(os.path.dirname(__file__), '.env')
KEY_OAUTH_TOKEN         = 'OAUTH_TOKEN'
KEY_OAUTH_TOKEN_SECRET  = 'OAUTH_TOKEN_SECRET'

# ─── OAuth routes ────────────────────────────────────────────
from requests_oauthlib import OAuth1Session
print("LOADING settings_service.py from", __file__)

@app.route('/oauth_callback')
def oauth_callback():
    # TODO: implement OAuth callback handling
    pass
@app.context_processor
def inject_label_config():
    return {
        "timeframe_labels":         label_config.timeframe_labels,
        "sma_length_labels":        label_config.sma_length_labels,
        "rsi_len_labels":           label_config.rsi_len_labels,
        "rsi_overbought_labels":    label_config.rsi_overbought_labels,
        "rsi_oversold_labels":      label_config.rsi_oversold_labels,
        "macd_fast_labels":         label_config.macd_fast_labels,
        "macd_slow_labels":         label_config.macd_slow_labels,
        "macd_signal_labels":       label_config.macd_signal_labels,
        "bb_length_labels":         label_config.bb_length_labels,
        "bb_std_labels":            label_config.bb_std_labels,
        "vol_mult_labels":          label_config.vol_mult_labels,
        "vwap_labels":              label_config.vwap_labels,
        "trailing_stop_pct_labels": label_config.trailing_stop_pct_labels,
        "sell_after_days_labels":   label_config.sell_after_days_labels,
    }


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

@app.context_processor
def inject_indicator_labels():
    return {
        # ── SMA lengths ──
        'sma_labels': {
            10: "SMA (10)",
            20: "SMA (20)",
            50: "SMA (50)",
        },
        # ── RSI lengths ──
        'rsi_len_options': {
            7:  "RSI (7)",
            14: "RSI (14)",
            21: "RSI (21)",
        },
        'rsi_len_labels': {
            7:  "RSI (7)",
            14: "RSI (14)",
            21: "RSI (21)",
        },
        # ── RSI thresholds ──
        'rsi_ob_labels': {
            70: "Overbought ≥ 70",
            80: "Overbought ≥ 80",
            90: "Overbought ≥ 90",
        },
        'rsi_os_labels': {
            30: "Oversold ≤ 30",
            20: "Oversold ≤ 20",
            10: "Oversold ≤ 10",
        },
        # ── MACD EMA labels ──
        'macd_fast_labels': {
            5:  "Fast EMA 5",
            8:  "Fast EMA 8",
            12: "Fast EMA 12",
        },
        'macd_slow_labels': {
            17: "Slow EMA 17",
            26: "Slow EMA 26",
            35: "Slow EMA 35",
        },
        'macd_signal_labels': {
            5:  "Signal EMA 5",
            9:  "Signal EMA 9",
            12: "Signal EMA 12",
        },
        # ── (Optional) MACD presets ──
        'macd_presets': {
            (12, 26, 9): "MACD (12,26,9)",
            (5, 35, 5):  "MACD (5,35,5)",
            (8, 17, 9):  "MACD (8,17,9)",
        },
        # ── Bollinger Bands ──
        'bb_length_labels': {
            20:  "BB Length 20",
            50:  "BB Length 50",
            100: "BB Length 100",
        },
        'bb_std_labels': {
            2.0: "Std Dev ×2",
            2.5: "Std Dev ×2.5",
            3.0: "Std Dev ×3",
        },
        # ── Volume multiplier ──
        'vol_multiplier_labels': {
            1.0: "Vol ≥ 1× Avg",
            1.5: "Vol ≥ 1.5× Avg",
            2.0: "Vol ≥ 2× Avg",
        },
        # ── VWAP thresholds ──
        'vwap_threshold_labels': {
            0.0: "VWAP+ ≥ $0.00",
            0.5: "VWAP+ ≥ $0.50",
            1.0: "VWAP+ ≥ $1.00",
        },
        # ── ATR % filters ──
        'atr_labels': {
            0.5: "ATR ≥ 0.5%",
            1.0: "ATR ≥ 1.0%",
            1.5: "ATR ≥ 1.5%",
        },
        # ── Daily range % filters ──
        'range_labels': {
            0.5: "Range ≥ 0.5%",
            1.0: "Range ≥ 1.0%",
            1.5: "Range ≥ 1.5%",
        },
        # ── Pre-market gap-up % filters ──
        'gap_labels': {
            1.0: "Gap ≥ 1.0%",
            2.0: "Gap ≥ 2.0%",
            3.0: "Gap ≥ 3.0%",
        },
    }


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

# ── 1) Define your settings tuples ───────────────────────────────────

from collections import namedtuple

BacktestSettings = namedtuple('BacktestSettings', [
    # date & capital
    'start_date', 'end_date', 'starting_cash', 'max_per_trade', 'timeframe',

    # core entry toggles
    'sma_on', 'rsi_on', 'macd_on', 'bb_on', 'vol_on', 'vwap_on', 'news_on',

    # core numeric parameters
    'sma_length', 'rsi_len', 'rsi_overbought', 'rsi_oversold',
    'macd_fast', 'macd_slow', 'macd_signal',
    'bb_length', 'bb_std', 'vol_multiplier', 'vwap_threshold',

    # advanced entry flags
    'rsi_slope_on', 'macd_hist_on', 'bb_breakout_on', 'price_sma_on',
    'atr_on', 'atr_pct', 'range_on', 'range_pct', 'gap_on', 'gap_pct',

    # exit behavior
    'single_entry_only', 'use_trailing_stop',
    'trailing_stop_pct', 'sell_after_days',
    'stop_loss_pct', 'take_profit_pct',
])

SimulationSettings = namedtuple('SimulationSettings', [
    # ── entry toggles ──
    'sma_on', 'rsi_on', 'macd_on', 'bb_on', 'vol_on', 'vwap_on', 'news_on',
    # ── entry numeric ──
    'sma_length', 'rsi_len', 'rsi_overbought', 'rsi_oversold',
    'macd_fast', 'macd_slow', 'macd_signal',
    'bb_length', 'bb_std', 'vol_multiplier', 'vwap_threshold',
    # ── advanced entry filters ──
    'atr_on', 'atr_pct', 'range_on', 'range_pct', 'gap_on', 'gap_pct',
    'price_sma_on',
    # ── extra entry/exit toggles ──
    'rsi_slope_on', 'macd_hist_on', 'bb_breakout_on',
    'single_entry_only', 'use_trailing_stop',
    # ── exit behavior ──
    'trailing_stop_pct', 'sell_after_days',
    'stop_loss_pct', 'take_profit_pct',
    # ── capital settings ──
    'starting_cash', 'max_per_trade'
])

# ── 2) Extract backtest settings from args ───────────────────────────

def extract_backtest_settings(args):
    return BacktestSettings(
        # date & capital
        start_date        = args.get('start_date'),
        end_date          = args.get('end_date'),
        starting_cash     = float(args.get('starting_cash', 10000)),
        max_per_trade     = float(args.get('max_per_trade', 1000)),
        timeframe         = args.get('timeframe'),
        # core entry filters
        sma_on            = 'sma_on' in args,
        rsi_on            = 'rsi_on' in args,
        macd_on           = 'macd_on' in args,
        bb_on             = 'bb_on' in args,
        vol_on            = 'vol_on' in args,
        vwap_on           = 'vwap_on' in args,
        news_on           = 'news_on' in args,
        rsi_slope_on      = 'rsi_slope_on' in args,
        macd_hist_on      = 'macd_hist_on' in args,
        bb_breakout_on    = 'bb_breakout_on' in args,
        price_sma_on      = 'price_sma_on' in args,
        atr_on            = 'atr_on' in args,
        range_on          = 'range_on' in args,
        gap_on            = 'gap_on' in args,

        # core numeric parameters
        sma_length        = int(args.get('sma_length', 20)),
        rsi_len           = int(args.get('rsi_len', 14)),
        rsi_overbought    = int(args.get('rsi_ob', 70)),
        rsi_oversold      = int(args.get('rsi_os', 30)),
        macd_fast         = int(args.get('macd_fast', 12)),
        macd_slow         = int(args.get('macd_slow', 26)),
        macd_signal       = int(args.get('macd_signal', 9)),
        bb_length         = int(args.get('bb_length', 20)),
        bb_std            = float(args.get('bb_std', 2.0)),
        vol_multiplier    = float(args.get('vol_multiplier', 1.0)),
        vwap_threshold    = float(args.get('vwap_threshold', 0.0)),
        # advanced entry filters
        atr_pct           = float(args.get('atr_pct', 1.0)) / 100,
        range_pct         = float(args.get('range_pct', 1.0)) / 100,
        gap_pct           = float(args.get('gap_pct', 2.0)) / 100,
        # exit behavior
        single_entry_only = 'single_entry_only' in args,
        use_trailing_stop = 'use_trailing_stop' in args,
        trailing_stop_pct = float(args.get('trailing_stop_pct', 0.0)),
        sell_after_days   = int(args.get('sell_after_days')) if args.get('sell_after_days') else None,
        stop_loss_pct     = float(args.get('stop_loss_pct')  or 0.0),
        take_profit_pct   = float(args.get('take_profit_pct') or 0.0),
    )

# ── 3) Extract simulation settings from args ──────────────────────────


def load_your_symbols():
    # reads your SP500 list
    settings = extract_simulation_settings(cfg)

    # make sure you load or define your symbols before calling the loop
    with open("sp500_symbols.txt") as f:
        symbols = [line.strip() for line in f if line.strip()]

    # pass both settings and symbols
    run_simulation_loop(settings, symbols)

BACKTEST_DB = 'backtest.db'


from flask import request, flash, render_template
from types import SimpleNamespace
from dateutil.relativedelta import relativedelta
from datetime import datetime

from services.settings_schema import BacktestSettings, extract_backtest_settings
from services.risk_management import enforce_wash_sale, enforce_settlement
from services.backtest_engine import run_full_backtest
import json
from pathlib import Path
from datetime import timedelta
# ─── Persistence ─────────────────────────────────────────────
SETTINGS_FILE = Path(__file__).parent / "settings.json"

TIMEFRAME_DELTAS = {
    "1d": timedelta(days=1),
    "1h": timedelta(hours=1),
    "15m": timedelta(minutes=15),
    # …etc…
}

def load_settings(defaults: dict = None) -> dict:
    """
    Load dashboard settings from JSON, then overlay them onto `defaults` if provided.
    """
    saved = {}
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
        except json.JSONDecodeError:
            saved = {}

    if defaults is None:
        return saved
    merged = defaults.copy()
    merged.update(saved)
    return merged

def save_settings(settings: dict) -> None:
    """
    Persist the given settings dict to JSON.
    """
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))

@app.route("/backtest", methods=["GET", "POST"])
@app.route("/backtest", methods=["GET", "POST"])
def backtest_view():
    defaults      = BacktestSettings().__dict__
    settings_dict = load_settings(defaults)
    settings      = extract_backtest_settings(request.values)

    trades, summary = None, None
    if request.method == "POST":
        save_settings(settings.__dict__)
        delta_args           = TIMEFRAME_DELTAS[settings.timeframe]
        settings.start_date  = datetime.now().date() - relativedelta(**delta_args)
        settings.end_date    = datetime.now().date()

        symbols = get_symbols(simulation=True)
        trades, summary = run_full_backtest(
            settings,
            symbols,
            wash_sale=enforce_wash_sale,
            settlement=enforce_settlement
        )
        summary = SimpleNamespace(**summary)

    return render_template(
        "backtest.html",
        settings=settings,
        trades=trades,
        summary=summary,
    )


@app.route('/scanner_status')
def scanner_status():
    return jsonify(
      running=_is_scanner_running,
     needs_auth=_needs_auth
    )

from dataclasses import asdict
from types import SimpleNamespace
from datetime import datetime
import sqlite3, json

from flask import request, render_template, flash
from dateutil.relativedelta import relativedelta

from services.settings_schema   import BacktestSettings, extract_backtest_settings
from services.label_config      import (            # if you still need to import it
    # you shouldn’t need these here if you’re using the context processor,
    # but listed in case you render anything manually
    timeframe_labels,
    sma_length_labels,
    # …etc…
    vol_mult_labels,
    vwap_labels,
)
from services.trading_helpers   import init_backtest_db
from services.market_service    import get_symbols
from services.backtest_engine   import run_full_backtest
from services.risk_management   import enforce_wash_sale, enforce_settlement
from settings                    import BACKTEST_DB
from dashboard                   import load_settings, save_settings, TIMEFRAME_DELTAS

@app.route('/run_backtest', methods=['POST'])
def run_backtest_route():
    # 1) Build a BacktestSettings from the form
    settings = extract_backtest_settings(request.form)
    # 2) Override the two numeric fields directly
    settings.starting_cash = float(request.form.get("starting_cash", settings.starting_cash))
    settings.max_per_trade = float(request.form.get("max_per_trade", settings.max_per_trade))

    # 3) Reset the backtest DB
    init_backtest_db()

    # 4) Run the backtest
    symbols = get_symbols(simulation=True)
    result  = run_full_backtest(
        settings,
        symbols,
        wash_sale=enforce_wash_sale,
        settlement=enforce_settlement
    )

    # 5) Normalize result
    if not (isinstance(result, tuple) and len(result) == 2):
        flash("⚠️ Backtest didn’t produce any data—showing an empty run", "warning")
        trades  = []
        summary = {'total_pnl': 0.0, 'num_trades': 0, 'wins': 0, 'losses': 0, 'by_symbol': {}}
    else:
        trades, summary = result

    # 6) Log this run
    conn = sqlite3.connect(BACKTEST_DB)
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO backtest_runs (started_at, settings_json) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), json.dumps(asdict(settings)))
    )
    run_id = cur.lastrowid

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

    flash("✅ Backtest run complete!")

    # 7) Render the same template—labels come from your context processor
    return render_template(
        "backtest.html",
        settings=settings,
        trades=trades,
        summary=SimpleNamespace(**summary),
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

from io import BytesIO
from flask import make_response
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from types import SimpleNamespace

import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors

from services.backtest_service import run_full_backtest
from services.market_service    import get_symbols
from flask import send_file

@app.route('/export_backtest_pdf')
def export_backtest_pdf():
    # 1) rebuild settings & run backtest
    settings = extract_backtest_settings(request.args)

    # DEBUG: log out the settings we received
    app.logger.debug(f"PDF export settings: {settings}")

    # 2) Load symbols and run backtest
    symbols = get_symbols(simulation=True)
    trades, summary_dict = run_full_backtest(settings, symbols)
    summary = SimpleNamespace(**summary_dict)

    # … rest of your export logic …


    # 2) PDF setup
    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()

    # Ensure you have registered a Unicode-capable font earlier:
    #   pdfmetrics.registerFont(TTFont('UnicodeFont', font_path))
    #   unicode_font_name = 'UnicodeFont'
    unicode_title = ParagraphStyle(
        'UnicodeTitle',
        parent=styles['Title'],
        fontName=unicode_font_name,
        fontSize=24,
        alignment=1
    )
    unicode_style = ParagraphStyle(
        'Unicode',
        parent=styles['Normal'],
        fontName=unicode_font_name
    )

    elems = []

    # 3) 🚀 Title
    elems.append(Spacer(1, 12))
    elems.append(Paragraph("🚀 TradeAlerts 🚀", unicode_title))
    elems.append(Spacer(1, 12))

    # 4) Summary table
    summary_data = [
        ["Starting Cash",    f"${settings.starting_cash:.2f}"],
        ["Total P&L",        f"${summary.total_pnl:.2f}"],
        ["Current Cash",     f"${settings.starting_cash + summary.total_pnl:.2f}"],
        ["P&L %",            f"{(summary.total_pnl / settings.starting_cash * 100):.2f}%"],
        ["Total Trades",     str(summary.num_trades)],
        ["Win %",            f"{summary.win_rate_pct:.1f}%"],
        ["Avg P/L / Trade",  f"${summary.avg_pnl_per_trade:.2f}"],
        ["Best Trade",       f"${summary.best_trade_pnl:.2f}"],
        ["Worst Trade",      f"${summary.worst_trade_pnl:.2f}"],
    ]
    tbl = Table(summary_data, hAlign='CENTER')
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), '#a8d8ea'),
        ('TEXTCOLOR',  (0, 0), (1, 0), 'white'),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 12))

    # 5) Enabled indicators (human-readable)
    indicator_labels = []

    # Core toggles:
    if settings.sma_on:
        indicator_labels.append(f"SMA ({settings.sma_length})")
    if settings.rsi_on:
        indicator_labels.append(f"RSI ({settings.rsi_len})")
    if settings.macd_on:
        indicator_labels.append(f"MACD ({settings.macd_fast},{settings.macd_slow},{settings.macd_signal})")
    if settings.bb_on:
        indicator_labels.append(f"BB ({settings.bb_length},σ={settings.bb_std})")
    if settings.vol_on:
        indicator_labels.append(f"Vol ≥ {settings.vol_multiplier}×")
    if settings.vwap_on:
        indicator_labels.append("VWAP+")
    if settings.news_on:
        indicator_labels.append("News")

    # Advanced entry filters:
    if getattr(settings, 'rsi_slope_on', False):
        indicator_labels.append("RSI Slope ⤴")
    if getattr(settings, 'macd_hist_on', False):
        indicator_labels.append("MACD Hist 📊")
    if getattr(settings, 'bb_breakout_on', False):
        indicator_labels.append("BB Breakout 💥")
    if getattr(settings, 'price_sma_on', False):
        indicator_labels.append(f"Price>SMA({settings.sma_length})")
    if getattr(settings, 'atr_on', False):
        indicator_labels.append(f"ATR ≥ {settings.atr_pct*100:.1f}%")
    if getattr(settings, 'range_on', False):
        indicator_labels.append(f"Range ≥ {settings.range_pct*100:.1f}%")
    if getattr(settings, 'gap_on', False):
        indicator_labels.append(f"Gap ≥ {settings.gap_pct*100:.1f}%")

    elems.append(Paragraph("Enabled Indicators:", styles['Heading3']))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(", ".join(indicator_labels), unicode_style))
    elems.append(Spacer(1, 12))


    # 6) Trade log
    data = [['Symbol', 'Date', 'Action', 'Price', 'Qty', 'P/L']] + [
        [
            t['symbol'],
            t['date'],
            t['action'],
            f"{t['price']:.2f}",
            str(t['qty']),
            f"{t['pnl']:.2f}" if t.get('pnl') is not None else ""
        ]
        for t in trades
    ]
    trade_tbl = Table(data, hAlign='CENTER')
    trade_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('GRID',       (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elems.append(trade_tbl)

    # 7) Finish and send
    doc.build(elems)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/pdf',
        download_name='backtest_report.pdf'
    )

@app.route('/clear_all', methods=['POST'])
def clear_all_alerts():
    print("✅ /clear_all route hit")
    conn = sqlite3.connect(ALERTS_DB )
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/clear/<int:id>', methods=['POST'])
def clear_alert(id):
    try:
        conn = sqlite3.connect(ALERTS_DB)
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


from services.trading_helpers import setup_simulation_db  # you already have this

@app.route('/simulation/reset', methods=['POST'])
def nuke_simulation_db():
    # re‐initialize your simulation schema
    setup_simulation_db()
    flash("Simulation DB reset!", "success")
    return redirect(url_for('simulation'))

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
            trade_time = t.get('trade_time') or t.get('timestamp')
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
        'timestamp':   t.get('timestamp'),
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
        unrealized_pnl_pct=unrealized_pnl_pct,
        realized_pnl_pct=realized_pnl_pct,
        realized_pnl=realized_pnl,
        holdings=formatted_holdings,
        history=formatted_trades
    )
@app.route('/simulation/status')
def simulation_status():
    return jsonify({"status": "ok", "market_open": True}), 200


@app.route('/export/simulation')
def export_simulation():
    cash     = get_cash()
    holdings = get_holdings()
    trades   = get_trades()

    # --- Helper for formatting trade times ---
    def format_trade_time(ts):
        from datetime import datetime
        if isinstance(ts, datetime):
            return ts.strftime('%Y-%m-%d %H:%M:%S')
        try:
            dt = datetime.fromisoformat(str(ts))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(ts).split('.')[0]

    # ---- Prepare holdings as dicts for calculations ----
    holding_dicts = []
    for h in holdings:
        # Accept both dict and tuple formats
        if isinstance(h, dict):
            symbol = h['symbol']
            qty = h['qty']
            price_paid = h['price_paid']
        else:
            symbol, qty, price_paid, _ = h[:4]

        try:
            # Get live price
            last_price = fetch_etrade_quote(symbol) or 0.0

            # Get previous close (for day gain)
            hist = fetch_data_with_timeout(symbol, "2d")
            if hist is not None:
                print(f"{symbol}: hist['close'] = {hist['close'].to_list()}")
                print(f"{symbol}: prev_close = {hist['close'].iloc[-2] if len(hist) > 1 else 'N/A'}")
                print(f"{symbol}: price_paid = {price_paid}")
            logger.debug(f"{symbol} close history for 2d: {hist['close'].to_list() if hist is not None else 'None'}")
            # Use correct column name (case-sensitive!)
            col_close = next((c for c in hist.columns if c.lower() == "close"), "Close")
            if hist is not None and len(hist) > 1 and col_close in hist.columns:
                prev_close = float(hist[col_close].iloc[-2])
            else:
                prev_close = h["price_paid"]


            change = last_price - price_paid
            day_gain = (last_price - prev_close) * qty
            total_gain = (last_price - price_paid) * qty
            change_pct = (change / price_paid * 100) if price_paid else 0
            value = last_price * qty

        except Exception:
            last_price = price_paid
            day_gain = total_gain = change_pct = value = 0.0

        holding_dicts.append({
            "symbol": symbol,
            "qty": qty,
            "price_paid": price_paid,
            "last_price": last_price,
            "change": change,
            "change_pct": change_pct,
            "day_gain": day_gain,
            "total_gain": total_gain,
            "value": value,
        })

    # ---- Update holdings with live prices & gain calculations ----
    for h in holding_dicts:
        try:
            live = fetch_etrade_quote(h["symbol"]) or 0.0
            change = live - h["price_paid"]
            h["last_price"] = round(live, 2)
            h["total_gain"] = round(change * h["qty"], 2)
        except Exception:
            h["total_gain"] = 0.0

    unrealized_pnl = round(sum(h.get("total_gain", 0) for h in holding_dicts), 2)
    total_cost_basis = sum(h["qty"] * h["price_paid"] for h in holding_dicts)
    unrealized_pnl_pct = round((unrealized_pnl / total_cost_basis * 100), 2) if total_cost_basis else 0.0

    # ---- Build trade history for realized P&L ----
    history = []
    for t in trades:
        if isinstance(t, dict):
            pl_val = float(t.get("pl") or t.get("pnl") or 0)
            trade_time = t.get("trade_time") or t.get("timestamp") or t.get("time")
            history.append({
                "time": format_trade_time(trade_time),  # <-- CORRECT
                "symbol": t.get("symbol"),
                "action": t.get("action"),
                "qty":    t.get("qty"),
                "price":  t.get("price"),
                "pl":     pl_val,
            })
        else:
            trade_time, symbol, action, qty, price, pl = t[:6]
            try:
                pl_val = float(pl)
            except (TypeError, ValueError):
                pl_val = 0.0
            history.append({
                "time":   format_trade_time(trade_time),
                "symbol": symbol,
                "action": action,
                "qty":    qty,
                "price":  price,
                "pl":     pl_val,
            })
    realized_pnl = sum(t["pl"] for t in history if t.get("action") == "SELL")

    # ---- Write summary and export ----
    import io
    si = io.StringIO()
    cw = csv.writer(si)

    cw.writerow(['Cash', f"${cash:.2f}"])
    cw.writerow(['Unrealized P&L', f"${unrealized_pnl:.2f}"])
    cw.writerow(['Unrealized P&L %', f"{unrealized_pnl_pct:.2f}%"])
    cw.writerow(['Realized P&L', f"${realized_pnl:.2f}"])
    cw.writerow([])  # Blank row for spacing

    cw.writerow(['-- HOLDINGS --'])
    cw.writerow(['symbol','last_price','change','change_pct','qty','price_paid','day_gain','total_gain','value'])
    for h in holding_dicts:
        symbol      = h.get('symbol')
        qty         = h.get('qty')
        price_paid  = h.get('price_paid')
        last_price  = h.get('last_price')

        try:
            price_paid = float(price_paid)
            qty = int(qty)
            last_price = float(last_price)
        except Exception:
            price_paid = 0.0
            qty = 0
            last_price = 0.0

        change     = last_price - price_paid
        change_pct = (change / price_paid * 100) if price_paid else 0
        total_gain = change * qty
        day_gain   = total_gain  # Or recalc daily if you have that
        value      = last_price * qty

        cw.writerow([
            symbol,
            f"${last_price:.2f}",
            f"${change:.2f}",
            f"{change_pct:.1f}%",
            qty,
            f"${price_paid:.2f}",
            f"${day_gain:.2f}",
            f"${total_gain:.2f}",
            f"${value:.2f}",
        ])

    cw.writerow([])
    cw.writerow(['-- TRADES --'])
    cw.writerow(['timestamp','symbol','action','qty','price','pl'])
    for t in history:
        cw.writerow([
            t["time"],
            t["symbol"],
            t["action"],
            t["qty"],
            t["price"],
            abs(t["pl"] or 0)
        ])

    resp = make_response(si.getvalue())
    resp.headers["Content-Disposition"] = "attachment; filename=simulation.csv"
    resp.headers["Content-type"] = "text/csv"
    return resp
@app.route('/start_scanner', methods=['POST'])
def start_scanner():
    global _is_scanner_running

    setup_simulation_db()
    symbols = get_symbols(simulation=True)
    _is_scanner_running = True
    t = threading.Thread(
        target=run_simulation_loop,
        args=(sim_settings,),
        daemon=True
    )
    t.start()

    flash("▶️ Simulation started (DB nuked first)", "success")
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
    """
    Returns the average price paid per share for all BUY trades of a given symbol.
    """
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
            # (timestamp, symbol, action, qty, price, pl)
            _, sym, action, qty, price, *_ = t
        else:
            continue

        try:
            qty = int(qty)
            price = float(price)
        except Exception:
            continue

        if sym == symbol and action.upper() == 'BUY':
            total_qty  += qty
            total_cost += qty * price

    return (total_cost / total_qty) if total_qty else 0.0
from services.trading_helpers  import (
    setup_simulation_db,
    check_if_position_open,
    enter_trade,
    check_exit_orders,
    compute_qty
)
import json
import webbrowser
from requests.exceptions import HTTPError
from flask import current_app

from services.trading_helpers import get_cash, get_holdings, get_realized_pl, get_unrealized_pl
from services.trading_helpers import get_trades
from flask import Blueprint, redirect, url_for
from services.trading_helpers import setup_simulation_db, set_cash

sim_bp = Blueprint('simulation', __name__)
from services.trading_helpers import set_cash, get_cash
@sim_bp.route('/simulation/reset', methods=['POST'])
def reset_sim():
    # 1) Rebuild all tables:
    setup_simulation_db()

    # 2) Load your JSON config and apply starting cash:
    cfg = json.load(open('simulation_config.json'))
    settings = extract_simulation_settings(cfg)
    set_cash(settings.starting_cash)
    logging.info(f"[SIM] Seed cash set to: ${get_cash():.2f}")
    return redirect(url_for('simulation.simulation'))


from services.etrade_service import fetch_etrade_quote

from services.trading_helpers import (
    get_cash,
    get_unrealized_pl,
    get_realized_pl,
    get_holdings,
    get_trades,
)

from flask import render_template
from services.etrade_service   import fetch_etrade_quote
from services.simulation_service import run_simulation_loop, stop_simulation
from services.trading_helpers import (
    get_cash,
    get_holdings,
    get_trades,
    get_realized_pl,
)

from services.data_fetch import fetch_data_with_timeout  # Move this to the top of your file

@app.route("/simulation")
def simulation_view():
    # --- Helper for formatting trade times ---
    def format_trade_time(ts):
        from datetime import datetime
        if isinstance(ts, datetime):
            return ts.strftime('%Y-%m-%d %H:%M:%S')
        try:
            dt = datetime.fromisoformat(str(ts))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(ts).split('.')[0]

    # 1) pull cash & realized P/L
    cash     = get_cash()
    realized = get_realized_pl()
    
    # 2) pull raw holdings (as tuples)
    raw = get_holdings()  # (symbol, qty, avg_cost, old_last_price)
    # 3) convert to dicts, one dict per holding
    holdings = [{
        "symbol":     s,
        "qty":        q,
        "price_paid": ac,
        "last_price": lp,
        "day_gain":   None,
        "total_gain": None,
        "change_pct": None,
        "value":      None,
    } for s, q, ac, lp in raw]

    from services.trading_helpers import extract_total_gain, extract_cost_basis

    # --- Now update each holding with live prices ---
    for h in holdings:
        try:
            symbol = h["symbol"]
            qty = h["qty"]
            price_paid = h["price_paid"]

            live = fetch_etrade_quote(symbol) or price_paid

            hist = fetch_data_with_timeout(symbol, "2d")

            # --- SAFETY: Normalize columns for pandas MultiIndex or non-string ---
            if hist is not None:
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.get_level_values(-1)
                hist.columns = [str(c) for c in hist.columns]

            prev_close = price_paid  # Default fallback

            if hist is not None and len(hist) > 1:
                # Find "close" column, case-insensitive
                col_close = next((c for c in hist.columns if str(c).lower() == "close"), None)
                if col_close:
                    prev_close = float(hist[col_close].iloc[-2])

            change = live - price_paid

            h["last_price"] = round(live, 2)
            h["total_gain"] = round(change * qty, 2)
            h["day_gain"]   = round((live - prev_close) * qty, 2)
            h["change_pct"] = round((change / price_paid * 100) if price_paid else 0, 1)
            h["value"]      = round(live * qty, 2)

        except Exception as e:
            print(f"[SIM] Error updating holding {h}: {e}")
            if isinstance(h, dict):
                h["last_price"] = h.get("last_price", 0)
                h["total_gain"] = 0
                h["day_gain"] = 0
                h["change_pct"] = 0
                h["value"] = 0

    # 4) Now safely compute summary/header numbers
    unrealized_pnl = round(sum((h.get("total_gain") or 0) for h in holdings), 2)
    total_cost_basis = sum(h["qty"] * h["price_paid"] for h in holdings)
    unrealized_pnl_pct = round((unrealized_pnl / total_cost_basis * 100), 2) if total_cost_basis else 0.0

    # 5) rebuild trade history so `history` exists
    history = []
    for t in get_trades():
        # handle tuple or dict
        if isinstance(t, dict):
            pl_val = float(t.get("pl") or t.get("pnl") or 0)
            trade_time = t.get("trade_time") or t.get("timestamp") or t.get("time")
            history.append({
                "time": format_trade_time(trade_time),  # <-- CORRECT
                "symbol": t.get("symbol"),
                "action": t.get("action"),
                "qty":    t.get("qty"),
                "price":  t.get("price"),
                "pl":     pl_val,
            })

        else:  # tuple or list
            trade_time, symbol, action, qty, price, pl = t[:6]
            try:
                pl_val = float(pl)
            except (TypeError, ValueError):
                pl_val = 0.0
            history.append({
                "time": format_trade_time(trade_time),
                "symbol": symbol,
                "action": action,
                "qty":    qty,
                "price":  price,
                "pl":     pl_val,
            })

    # 6) now sum realized P&L safely (history now exists)
    realized_pnl = sum(t["pl"] for t in history if t.get("action") == "SELL")
    from services.simulation_service import load_simulation_settings
    settings = load_simulation_settings()
    print("DEBUG: Simulation route called, settings:", settings)
    # Calculate total buy cost
    total_buy_cost = sum(
        t["qty"] * t["price"] 
        for t in history if t["action"] == "BUY"
    )

    realized_pnl_pct = (
        (realized_pnl / total_buy_cost * 100) if total_buy_cost else 0.0
    )

    # 7) finally render
    return render_template(
        "simulation.html",
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        realized_pnl=realized_pnl,
        holdings=holdings,
        history=history,
        settings=settings,  # ← must be here!
        realized_pnl_pct=realized_pnl_pct,
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
# Alias /simulation → the same view as simulation_buy
@app.route("/simulation", methods=["GET", "POST"])
def simulation():
    return simulation_buy()

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
        last = a.get('last_match_time')  # or .get('timestamp') if that's your field
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

import sqlite3
import json
from flask import render_template
from services.settings_schema import SIM_DB_PATH
from services.trading_helpers import (
    setup_simulation_db, get_holdings, get_cash, get_realized_pl
)
from services.etrade_service import fetch_etrade_quote

CONFIG_PATH = Path(__file__).parent / "simulation_config.json"

@app.route("/")
def index():
    setup_simulation_db()
    from services.simulation_service import load_simulation_settings
    settings = load_simulation_settings() 
            # --- Helper for formatting trade times ---
    def format_trade_time(ts):
        from datetime import datetime
        if isinstance(ts, datetime):
            return ts.strftime('%Y-%m-%d %H:%M:%S')
        try:
            dt = datetime.fromisoformat(str(ts))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(ts).split('.')[0]

    # holdings
    raw = get_holdings()
    holdings = []
    for symbol, qty, avg_cost, _ in raw:
        try:
            last_price = fetch_etrade_quote(symbol)
        except Exception:
            last_price = _
        gain_per_share = last_price - avg_cost
        holdings.append({
            "symbol":     symbol,
            "qty":        qty,
            "price_paid": avg_cost,
            "last_price": last_price,
            "day_gain":   round(gain_per_share, 2),
            "change_pct": round((gain_per_share / avg_cost * 100), 1) if avg_cost else 0.0,
            "total_gain": round(gain_per_share * qty, 2),
            "value":      round(last_price * qty, 2),
        })

    cash = round(get_cash(), 2)
    unrealized_pnl = round(sum((h.get("total_gain") or 0) if isinstance(h, dict) else 0 for h in holdings), 2)
    total_cost_basis = sum(h["qty"] * h["price_paid"] for h in holdings)
    unrealized_pnl_pct = round((unrealized_pnl / total_cost_basis * 100), 2) if total_cost_basis else 0.0
    config = json.load(open(CONFIG_PATH))

    # build trade history FIRST!
    conn = sqlite3.connect(SIM_DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
      SELECT
        trade_time AS time,
        symbol,
        action,
        qty,
        price,
        pnl        AS pl
      FROM simulation_trades
      ORDER BY trade_time DESC
      LIMIT 50;
    """)
    rows = cur.fetchall()
    conn.close()
    def format_trade_time(ts):
        from datetime import datetime
        if isinstance(ts, datetime):
            return ts.strftime('%Y-%m-%d %H:%M:%S')
        try:
            dt = datetime.fromisoformat(str(ts))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(ts).split('.')[0]

    history = [
        {
            "time":   format_trade_time(row[0]),   # <--- fix!
            "symbol": row[1],
            "action": row[2],
            "qty":    row[3],
            "price":  row[4],
            "pl":     row[5],
        }
        for row in rows
    ]
    total_buy_cost = sum(
        t["qty"] * t["price"]
        for t in history if t["action"] == "BUY"
    )
    realized_pnl = sum(t["pl"] for t in history if t.get("action") == "SELL")
    realized_pnl_pct = (realized_pnl / total_buy_cost * 100) if total_buy_cost else 0.0

    return render_template(
        "simulation.html",
        holdings=holdings,
        cash=cash,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        realized_pnl_pct=realized_pnl_pct,
        history=history,
        config=config,
        settings=settings,
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=True)
