import sqlite3
import json
from datetime import datetime

BACKTEST_DB = 'backtest.db'

def log_backtest_run(config, summary):
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO backtest_runs (timestamp, config_json, summary_json)
        VALUES (?, ?, ?)
    """, (
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        json.dumps(config),
        json.dumps(summary)
    ))
    run_id = c.lastrowid
    conn.commit()
    conn.close()
    return run_id

def log_backtest_trade(run_id, symbol, action, price, qty, trade_time, pnl):
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO backtest_trades (run_id, symbol, action, price, qty, trade_time, pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (run_id, symbol, action, price, qty, trade_time, pnl))
    conn.commit()
    conn.close()

def get_last_run_summary():
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute("SELECT summary_json FROM backtest_runs ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return {}

def get_trades_for_run(run_id):
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute("""
        SELECT symbol, action, price, qty, trade_time, pnl
        FROM backtest_trades
        WHERE run_id = ?
        ORDER BY trade_time ASC
    """, (run_id,))
    trades = c.fetchall()
    conn.close()
    return trades
