import os
import sqlite3
import json
import logging
from datetime import datetime

import yfinance as yf
import pandas as pd

from services.news_service import fetch_latest_headlines
from config import BACKTEST_DB, BACKTEST_SCHEMA

logger = logging.getLogger(__name__)


def init_backtest_db():
    """Create or reset backtest.db schema."""
    conn = sqlite3.connect(BACKTEST_DB)
    conn.executescript(BACKTEST_SCHEMA)
    conn.commit()
    conn.close()
    logger.info("Initialized backtest.db with backtest_runs & backtest_trades")


def _has_headlines(src):
    if hasattr(src, 'empty'):
        return not src.empty
    try:
        return len(src) > 0
    except:
        return False


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, MACD, Bollinger Bands."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df['Close']
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    # MACD
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD'] = macd
    df['Signal'] = signal
    # Bollinger
    mb = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df['MB'] = mb
    df['UB'] = mb + 2*std20
    df['LB'] = mb - 2*std20
    return df


def log_backtest_run(config: dict, summary: dict) -> int:
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO backtest_runs (timestamp, config_json, summary_json)
        VALUES (?, ?, ?)
        """,
        (
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            json.dumps(config),
            json.dumps(summary)
        )
    )
    run_id = c.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_backtest_trade(run_id: int, symbol: str, action: str, price: float, qty: int, trade_time, pnl: float):
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO backtest_trades (run_id, symbol, action, price, qty, trade_time, pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, symbol, action, price, qty, str(trade_time), pnl)
    )
    conn.commit()
    conn.close()


def backtest(
    symbol: str,
    start_date: str,
    end_date: str,
    initial_cash: float,
    max_trade_per_stock: float,
    sma_on: bool,
    rsi_on: bool,
    macd_on: bool,
    bb_on: bool,
    vol_on: bool,
    vwap_on: bool,
    sma_length: int,
    rsi_len: int,
    rsi_overbought: float,
    rsi_oversold: float,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    bb_length: int,
    bb_std: float,
    vol_multiplier: float,
    vwap_threshold: float,
    trailing_stop_pct: float = 0.0,
    single_entry_only: bool = False,
    news_on: bool = False,
    log_to_db: bool = False
) -> (list, float):
    """
    Run a single-symbol backtest with optional trailing-stop, VWAP, and news filters.
    Returns (trades, net_pnl).
    """
    # initialize DB if logging
    run_id = None
    if log_to_db:
        config = locals().copy()
        config.pop('log_to_db')
        config.pop('run_id', None)
        run_id = log_backtest_run(config, {})

    # fetch price history
    yf_sym = symbol.replace('.', '-')
    df = yf.Ticker(yf_sym).history(
        start=start_date,
        end=end_date,
        interval='1d',
        auto_adjust=False
    )
    if df is None or df.empty:
        logger.warning(f"No data for {symbol}, skipping.")
        return [], 0.0

    df = calculate_indicators(df)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP_Diff'] = (tp * df['Volume']).cumsum() / df['Volume'].cumsum()

    trades = []
    cash = initial_cash
    position = 0
    in_pos = False
    entry_idx = None

    for i in range(1, len(df)):
        price = df['Open'].iat[i] if 'Open' in df.columns else df['Close'].iat[i]

        # 1) TRAILING-STOP EXIT
        if in_pos and trailing_stop_pct > 0:
            entry_price = df['Close'].iat[entry_idx]
            if price <= entry_price * (1 - trailing_stop_pct):
                pnl = (price - entry_price) * position
                cash += position * price
                trades.append({
                    'symbol': symbol, 'action': 'SELL',
                    'date': str(df.index[i]), 'qty': position,
                    'price': price, 'pnl': round(pnl, 2)
                })
                if log_to_db and run_id:
                    log_backtest_trade(run_id, symbol, 'SELL', price, position, df.index[i], round(pnl,2))
                in_pos = False
                position = 0
                continue

        # 2) ENTRY
        if not in_pos:
            if sma_on:
                sma = df['Close'].rolling(sma_length).mean().iat[i]
                if price <= sma:
                    continue
            if vwap_on and df['VWAP_Diff'].iat[i] < vwap_threshold:
                continue
            if news_on and not _has_headlines(fetch_latest_headlines(symbol)):
                continue
            if single_entry_only and in_pos:
                continue

            qty = int(min(cash, max_trade_per_stock) // price)
            if qty <= 0:
                continue
            cash -= qty * price
            position = qty
            in_pos = True
            entry_idx = i
            trades.append({
                'symbol': symbol, 'action': 'BUY',
                'date': str(df.index[i]), 'qty': qty,
                'price': price, 'pnl': None
            })
            if log_to_db and run_id:
                log_backtest_trade(run_id, symbol, 'BUY', price, qty, df.index[i], 0)
            continue

    # 3) FINAL SELL
    if in_pos and position > 0:
        final_price = df['Close'].iat[-1]
        cash += position * final_price
        pnl = (final_price - df['Close'].iat[entry_idx]) * position
        trades.append({
            'symbol': symbol, 'action': 'SELL',
            'date': str(df.index[-1]), 'qty': position,
            'price': final_price, 'pnl': round(pnl,2)
        })
        if log_to_db and run_id:
            log_backtest_trade(run_id, symbol, 'SELL', final_price, position, df.index[-1], round(pnl,2))

    return trades, round(cash - initial_cash, 2)


def run_full_backtest(settings, symbols):
    """
    Initialize DB, run backtest() for each symbol, and aggregate results.
    """
    init_backtest_db()
    all_trades = []
    summary = {}
    for sym in symbols:
        tr, pnl = backtest(
            symbol=sym,
            start_date=settings.start_date,
            end_date=settings.end_date,
            initial_cash=settings.starting_cash,
            max_trade_per_stock=settings.max_per_trade,
            sma_on=settings.sma_on,
            rsi_on=settings.rsi_on,
            macd_on=settings.macd_on,
            bb_on=settings.bb_on,
            vol_on=settings.vol_on,
            vwap_on=settings.vwap_on,
            sma_length=settings.sma_length,
            rsi_len=settings.rsi_len,
            rsi_overbought=settings.rsi_overbought,
            rsi_oversold=settings.rsi_oversold,
            macd_fast=settings.macd_fast,
            macd_slow=settings.macd_slow,
            macd_signal=settings.macd_signal,
            bb_length=settings.bb_length,
            bb_std=settings.bb_std,
            vol_multiplier=settings.vol_multiplier,
            vwap_threshold=settings.vwap_threshold,
            trailing_stop_pct=settings.trailing_stop_pct,
            single_entry_only=settings.single_entry_only,
            news_on=settings.news_on,
            log_to_db=True
        )
        all_trades.extend(tr)
        summary[sym] = pnl
    return all_trades, summary

# alias
backtest_scanner = backtest
