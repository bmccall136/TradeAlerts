# backtest_helpers.py

import sqlite3
import os
from datetime import date
from dateutil.relativedelta import relativedelta
from collections import namedtuple

# ── Path to your backtest DB ───────────────────────────────────────────────
BACKTEST_DB = os.path.join(os.getcwd(), 'backtest.db')

# ── 1) Database initialization ─────────────────────────────────────────────
def init_backtest_db():
    """Drop & re-create the tables for tracking backtest runs & trades."""
    conn = sqlite3.connect(BACKTEST_DB)
    cur  = conn.cursor()

    # ── DROP any old tables so we always start fresh ─────────────────────────
    cur.execute("DROP TABLE IF EXISTS backtest_trades;")
    cur.execute("DROP TABLE IF EXISTS backtest_runs;")

    # ── CREATE the runs table with settings_json ─────────────────────────────
    cur.execute("""
      CREATE TABLE backtest_runs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at    TEXT,
        settings_json TEXT
      );
    """)

    # ── CREATE the trades table ───────────────────────────────────────────────
    cur.execute("""
      CREATE TABLE backtest_trades (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id   INTEGER,
        symbol   TEXT,
        date     TEXT,
        action   TEXT,
        price    REAL,
        qty      INTEGER,
        pnl      REAL,
        FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
      );
    """)

    conn.commit()
    conn.close()

# ── 2) Settings data structure ─────────────────────────────────────────────
TIMEFRAME_DELTAS = {
    '1mo': {'months': 1},
    '3mo': {'months': 3},
    '6mo': {'months': 6},
    '1y' : {'years': 1},
}
BacktestSettings = namedtuple('BacktestSettings', [
    'start_date','end_date',
    'starting_cash','max_per_trade',
    'trailing_stop_pct','sell_after_days',
    'sma_on','rsi_on','macd_on','bb_on','vol_on','vwap_on','news_on',
    'sma_length','rsi_len','rsi_overbought','rsi_oversold',
    'macd_fast','macd_slow','macd_signal',
    'bb_length','bb_std','vol_multiplier','vwap_threshold',
    'timeframe'
])

# ── 3) Timeframe‐aware extractor ────────────────────────────────────────────
def extract_backtest_settings(args):
    """
    Build BacktestSettings(start,end,…) from request args,
    defaulting start = today - timeframe, end = today.
    """
    tf    = args.get('timeframe', '6mo')
    today = date.today()
    delta = TIMEFRAME_DELTAS.get(tf, {'months': 6})
    start = today - relativedelta(**delta)
    end   = today

    return BacktestSettings(
        start_date        = args.get('start_date',  start.isoformat()),
        end_date          = args.get('end_date',    end.isoformat()),
        starting_cash     = float(args.get('starting_cash', 10000)),
        max_per_trade     = float(args.get('max_per_trade', 1000)),
        trailing_stop_pct = float(args.get('trailing_stop_pct', 0)),
        sell_after_days   = int(args.get('sell_after_days', 0)),
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
        timeframe         = tf
    )
