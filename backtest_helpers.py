# backtest_helpers.py
import sqlite3
import os

BACKTEST_DB = os.path.join(os.getcwd(), 'backtest.db')

def init_backtest_db():
    conn = sqlite3.connect(BACKTEST_DB)
    cur  = conn.cursor()

    # create a table to track each run
    cur.execute("""
      CREATE TABLE IF NOT EXISTS backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        settings_json TEXT
      );
    """)

    # create a table for individual trades
    cur.execute("""
      CREATE TABLE IF NOT EXISTS backtest_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        symbol TEXT,
        date TEXT,
        action TEXT,
        price REAL,
        qty INTEGER,
        pnl REAL,
        FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
      );
    """)

    conn.commit()
    conn.close()

from collections import namedtuple

BacktestSettings = namedtuple('BacktestSettings', [
    'start_date','end_date','starting_cash','max_per_trade',
    'trailing_stop_pct','sell_after_days',
    'sma_on','rsi_on','macd_on','bb_on','vwap_on','news_on',
    'sma_length','rsi_len','rsi_overbought','rsi_oversold',
    'macd_fast','macd_slow','macd_signal',
    'bb_length','bb_std','vol_multiplier','vwap_threshold',
    'timeframe'
])

def extract_backtest_settings(args):
    return BacktestSettings(
        start_date        = args.get('start_date',  '2023-01-01'),
        end_date          = args.get('end_date',    '2024-01-01'),
        starting_cash     = float(args.get('starting_cash', 10000)),
        max_per_trade     = float(args.get('max_per_trade', 1000)),
        trailing_stop_pct = float(args.get('trailing_stop_pct', 0)),
        sell_after_days   = int(args.get('sell_after_days', 0)),
        sma_on            = bool(args.get('sma_on')),
        rsi_on            = bool(args.get('rsi_on')),
        macd_on           = bool(args.get('macd_on')),
        bb_on             = bool(args.get('bb_on')),
        vwap_on           = bool(args.get('vwap_on')),
        news_on           = bool(args.get('news_on')),
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
        timeframe         = args.get('timeframe', '6mo')
    )

