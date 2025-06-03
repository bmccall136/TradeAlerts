import sqlite3
import json
from datetime import datetime
import yfinance as yf
import pandas as pd
import numpy as np

BACKTEST_DB = 'backtest.db'

def log_backtest_run(config, summary):
    """
    Insert a new backtest run record into the 'backtest_runs' table.
    """
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
    """
    Insert a new trade from a backtest run into the 'backtest_trades' table.
    """
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO backtest_trades (run_id, symbol, action, price, qty, trade_time, pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (run_id, symbol, action, price, qty, trade_time, pnl))
    conn.commit()
    conn.close()

def get_last_run_summary():
    """
    Fetch the JSON‐decoded summary of the most recent backtest run.
    """
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute("SELECT summary_json FROM backtest_runs ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return {}

def get_trades_for_run(run_id):
    """
    Return a list of (symbol, action, price, qty, trade_time, pnl) for the given run_id,
    ordered by trade_time ascending.
    """
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

def calculate_indicators(df):
    """
    Given a DataFrame 'df' that may have MultiIndex columns (e.g. ('AAPL','Close')),
    flatten its columns so they become something like ['Open','High','Low','Close','Adj Close','Volume',...].
    Then:
      1) Find any column whose name contains 'close' (case‐insensitive) and call it close_col.
         If none has 'close', fallback to the first column.
      2) Copy that close_col into a new df['Close'] (of type float).
      3) Compute RSI (14), MACD (12,26)+Signal (9), Bollinger Bands (20).
    Returns the modified DataFrame with new columns: 'RSI','MACD','Signal','MB','UB','LB'.
    """

    # 1) If columns are MultiIndex, pick whichever level holds the field names
    if isinstance(df.columns, pd.MultiIndex):
        field_level = None
        for lvl in [0, 1]:
            vals = [str(v).lower() for v in df.columns.get_level_values(lvl)]
            if any(x in ['open','high','low','close','adj close','volume'] for x in vals):
                field_level = lvl
                break
        if field_level is None:
            # fallback if neither level looks like field names
            field_level = 1
        df.columns = df.columns.get_level_values(field_level)

    # 2) Identify which existing column to treat as the “close” price
    cols_lower = [c.lower() for c in df.columns]

    if 'close' in cols_lower:
        close_col = df.columns[cols_lower.index('close')]
    elif 'adj close' in cols_lower:
        close_col = df.columns[cols_lower.index('adj close')]
    else:
        # pick the first column whose lowercase name contains “close”
        candidates = [df.columns[i] for i, lc in enumerate(cols_lower) if 'close' in lc]
        if candidates:
            close_col = candidates[0]
        else:
            # if no column has “close” anywhere, just pick the very first column
            close_col = df.columns[0]

    # 3) Copy that column into df['Close'] as floats
    df['Close'] = df[close_col].astype(float)

    # ------- RSI (14) -------
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ----- MACD (12,26) and Signal (9) -----
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # ----- Bollinger Bands (20) -----
    close = df['Close']
    mb = close.rolling(window=20).mean()       # middle band
    std20 = close.rolling(window=20).std()     # 20‐period standard deviation
    df['MB'] = mb
    df['UB'] = mb + 2 * std20
    df['LB'] = mb - 2 * std20

    return df

def backtest(symbol, start, end, initial_cash=10000, log_to_db=False):
    """
    Run a basic RSI+MACD crossover backtest on 'symbol' from 'start' to 'end'.
    Buys when MACD crosses above its Signal (and RSI < 30),
    sells when it crosses below (and RSI > 70).
    Trades execute at the NEXT BAR’s Open price.
    If log_to_db=True, runs and trades are recorded in SQLite.
    Returns (trades_list, net_return).
    """

    # Download historical data (yfinance may return MultiIndex columns)
    df = yf.download(symbol, start=start, end=end, progress=False)
    if df.empty:
        raise ValueError(f"No data for {symbol} in {start}–{end}.")

    # Flatten & compute indicators
    df = calculate_indicators(df)

    cash = initial_cash
    position = 0
    trades = []
    run_id = None

    if log_to_db:
        config = {'symbol': symbol, 'start': start, 'end': end, 'initial_cash': initial_cash}
        summary = {'net_return': None}
        run_id = log_backtest_run(config, summary)

    # Iterate row by row; “yesterday” and “today” are each single‐row Series
    for i in range(1, len(df)):
        yesterday = df.iloc[i - 1]
        today = df.iloc[i]

        # BUY: yesterday['MACD'] < yesterday['Signal']  AND  today['MACD'] > today['Signal']  AND  today['RSI'] < 30
        if (
            (yesterday['MACD'] < yesterday['Signal']) and
            (today['MACD'] > today['Signal']) and
            (today['RSI'] < 30) and
            (position == 0)
        ):
            price = today['Open']
            qty = int(cash // price)
            if qty > 0:
                cash -= qty * price
                position = qty
                trades.append({
                    'Date': today.name.strftime("%Y-%m-%d %H:%M:%S"),
                    'Type': 'Buy',
                    'Price': float(price),
                    'Qty': qty,
                    'P/L': None
                })
                if log_to_db:
                    log_backtest_trade(
                        run_id, symbol, 'Buy',
                        float(price), qty,
                        today.name.strftime("%Y-%m-%d %H:%M:%S"),
                        None
                    )

        # SELL: yesterday['MACD'] > yesterday['Signal']  AND  today['MACD'] < today['Signal']  AND  today['RSI'] > 70
        elif (
            (yesterday['MACD'] > yesterday['Signal']) and
            (today['MACD'] < today['Signal']) and
            (today['RSI'] > 70) and
            (position > 0)
        ):
            price = today['Open']
            cash += position * price
            buy_price = trades[-1]['Price'] if trades else 0
            pnl = (price - buy_price) * position
            trades.append({
                'Date': today.name.strftime("%Y-%m-%d %H:%M:%S"),
                'Type': 'Sell',
                'Price': float(price),
                'Qty': position,
                'P/L': float(pnl)
            })
            if log_to_db:
                log_backtest_trade(
                    run_id, symbol, 'Sell',
                    float(price), position,
                    today.name.strftime("%Y-%m-%d %H:%M:%S"),
                    float(pnl)
                )
            position = 0

    # If still holding at the very end, force-sell at last close
    if position > 0:
        final_price = df['Close'].iloc[-1]
        cash += position * final_price
        buy_price = trades[-1]['Price'] if trades else 0
        pnl = (final_price - buy_price) * position
        trades.append({
            'Date': df.index[-1].strftime("%Y-%m-%d %H:%M:%S"),
            'Type': 'Sell',
            'Price': float(final_price),
            'Qty': position,
            'P/L': float(pnl)
        })
        if log_to_db:
            log_backtest_trade(
                run_id, symbol, 'Sell',
                float(final_price), position,
                df.index[-1].strftime("%Y-%m-%d %H:%M:%S"),
                float(pnl)
            )
        position = 0

    net_return = cash - initial_cash

    if log_to_db and (run_id is not None):
        summary = {'net_return': float(net_return), 'total_trades': len(trades)}
        conn = sqlite3.connect(BACKTEST_DB)
        c = conn.cursor()
        c.execute("""
            UPDATE backtest_runs
            SET summary_json = ?
            WHERE id = ?
        """, (json.dumps(summary), run_id))
        conn.commit()
        conn.close()

    return trades, float(net_return)

if __name__ == "__main__":
    # Quick sanity check when running this file directly:
    symbol = "SPY"
    start_date = "2023-01-01"
    end_date = "2023-12-31"
    trades, pnl = backtest(symbol, start_date, end_date, initial_cash=10000, log_to_db=False)
    print(f"Net return for {symbol} from {start_date} to {end_date}: ${pnl:.2f}")
    for t in trades:
        print(t)
