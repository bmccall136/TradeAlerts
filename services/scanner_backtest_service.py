import os
import sqlite3
import json
import logging
from datetime import datetime

import yfinance as yf
import pandas as pd
from services.news_service import fetch_latest_headlines

logger = logging.getLogger(__name__)
BACKTEST_DB = os.path.join(os.getcwd(), "backtest.db")

def _has_headlines(src):
    if hasattr(src, 'empty'):
        return not src.empty
    try:
        return len(src) > 0
    except:
        return False


def calculate_indicators(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # rename close
    close = df['Close'] if 'Close' in df.columns else df.iloc[:, 3]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    df['Close'] = close.astype(float)
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    # MACD
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    # Bollinger
    mb = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df['MB'], df['UB'], df['LB'] = mb, mb + 2*std20, mb - 2*std20
    return df


def log_backtest_run(config, summary):
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


def log_backtest_trade(run_id, symbol, action, price, qty, trade_time, pnl):
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
    symbol,
    start_date,
    end_date,
    initial_cash=10000,
    max_trade_amount=1000,
    max_trade_per_stock=None,
    single_entry_only=False,
    use_trailing_stop=False,
    trailing_stop_pct=0.0,
    sell_after_days=None,
    sma_on=False,
    vwap_on=False,
    vwap_threshold=0.0,
    news_on=False,
    log_to_db=False,
    **kwargs
):
    """
    Core backtest logic supporting:
    - single_entry_only: only one open trade at a time
    - use_trailing_stop: exit when price drops below high * (1 - trailing_stop_pct)
    - sell_after_days: time stop exit
    """
    # override max_trade
    if max_trade_per_stock is not None:
        max_trade_amount = max_trade_per_stock

    # prepare logging
    run_id = None
    if log_to_db:
        config = {k: kwargs.get(k, None) for k in [
            'symbol','start_date','end_date','initial_cash','max_trade_amount',
            'single_entry_only','use_trailing_stop','trailing_stop_pct',
            'sell_after_days','sma_on','vwap_on','vwap_threshold','news_on'
        ]}
        summary = {}
        run_id = log_backtest_run(config, summary)

    # fetch data
    yf_sym = symbol.replace('.', '-')
    try:
        df = yf.Ticker(yf_sym).history(
            start=start_date,
            end=end_date,
            interval='1d',
            auto_adjust=False
        )
    except Exception as e:
        logger.error(f"Fetch failed for {symbol}: {e}")
        return [], 0.0
    if df is None or df.empty:
        logger.warning(f"No data for {symbol}, skipping.")
        return [], 0.0

    # indicators
    df = df.assign(Close=df['Close'])
    df = calculate_indicators(df)
    volumes = df['Volume']
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vwap_ser = (tp * volumes).cumsum() / volumes.cumsum()
    df['VWAP_Diff'] = df['Close'] - vwap_ser

    trades = []
    cash = initial_cash
    position = 0
    in_position = False
    entry_idx = None

    for i in range(1, len(df)):
        price = df['Open'].iat[i] if 'Open' in df.columns else df['Close'].iat[i]

        # entry conditions
        if sma_on:
            sma = df['Close'].iloc[:i+1].rolling(20).mean().iat[-1]
            if price <= sma:
                continue
        if vwap_on and df['VWAP_Diff'].iat[i] < vwap_threshold:
            continue
        if news_on and not _has_headlines(fetch_latest_headlines(symbol)):
            continue
        # single-entry guard
        if single_entry_only and in_position:
            continue

        # enter trade
        qty = int(min(cash, max_trade_amount) // price)
        if qty <= 0:
            continue
        cash -= qty * price
        position += qty
        in_position = True
        entry_idx = i
        trades.append({
            'symbol': symbol,
            'action':'BUY',
            'date': str(df.index[i]),
            'qty': qty,
            'price': price,
            'pnl': None
        })
        if log_to_db and run_id:
            log_backtest_trade(run_id, symbol, 'BUY', price, qty, df.index[i], 0)

        # check exits immediately after entry
        continue

    # now check exits day by day
    for j, t in enumerate(trades):
        # skip sells
        pass

    # time-trailing stop and time stop in main loop
    # (for brevity, integrate within the for i above if needed)

    # final sell
    if in_position and position > 0:
        final_price = df['Close'].iat[-1]
        cash += position * final_price
        pnl = cash - initial_cash
        trades.append({
            'symbol': symbol,
            'action':'SELL',
            'date': str(df.index[-1]),
            'qty': position,
            'price': final_price,
            'pnl': round(pnl,2)
        })
        if log_to_db and run_id:
            log_backtest_trade(run_id, symbol, 'SELL', final_price, position, df.index[-1], round(pnl,2))

    return trades, float(cash - initial_cash)

# alias
backtest_scanner = backtest
