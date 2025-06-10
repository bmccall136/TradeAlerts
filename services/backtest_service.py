import sqlite3
import json
from datetime import datetime

import yfinance as yf
import pandas as pd

from services.indicators import compute_sma, compute_rsi, calculate_macd, compute_bollinger
from services.news_service import fetch_latest_headlines

# Optional: log backtest runs/trades
BACKTEST_DB = 'backtest.db'

def log_backtest_run(config, summary):
    conn = sqlite3.connect(BACKTEST_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO backtest_runs (timestamp, config_json, summary_json)
        VALUES (?, ?, ?)
        """,
        (
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
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
        (run_id, symbol, action, price, qty, trade_time, pnl)
    )
    conn.commit()
    conn.close()


def calculate_indicators(df):
    """
    Flatten columns, pick a Close series, compute RSI, MACD+Signal, Bollinger Bands.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(1)

    cols_lower = [c.lower() for c in df.columns]
    if 'close' in cols_lower:
        close_col = df.columns[cols_lower.index('close')]
    elif 'adj close' in cols_lower:
        close_col = df.columns[cols_lower.index('adj close')]
    else:
        close_col = df.columns[0]

    close_series = df[close_col]
    if isinstance(close_series, pd.DataFrame):
        close_series = close_series.iloc[:,0]
    df['Close'] = close_series.astype(float)

    # RSI
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD + Signal
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # Bollinger Bands
    mb = df['Close'].rolling(window=20).mean()
    std20 = df['Close'].rolling(window=20).std()
    df['MB'] = mb
    df['UB'] = mb + 2 * std20
    df['LB'] = mb - 2 * std20

    return df


def backtest(
    symbol,
    start_date,
    end_date,
    initial_cash=10000,
    max_trade_amount=1000,
    sma_on=False,
    sma_length=20,
    vwap_on=False,
    vwap_threshold=0.0,
    news_on=False,
    log_to_db=False
):
    """
    Run a backtest on `symbol` from `start_date` to `end_date`,
    applying optional filters for SMA, VWAP, and News.
    Returns a tuple (trades_list, net_return).
    """

    df = yf.download(symbol, start=start_date, end=end_date, interval='1d', progress=False)

    if df.empty:
        return [], 0.0

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = calculate_indicators(df)

    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vwap_series = (tp * df['Volume']).cumsum() / df['Volume'].cumsum()
    df['VWAP'] = vwap_series
    df['VWAP_Diff'] = df['Close'] - df['VWAP']

    trades = []
    cash = initial_cash
    position = 0
    run_id = None

    if log_to_db:
        run_id = log_backtest_run(
            {
                'symbol': symbol,
                'start': start_date,
                'end': end_date,
                'initial_cash': initial_cash,
                'sma_on': sma_on,
                'vwap_on': vwap_on,
                'vwap_threshold': vwap_threshold,
                'news_on': news_on
            },
            {'net_return': None}
        )

    for i in range(1, len(df)):
        today = df.iloc[i]
        price = today['Open'] if 'Open' in today else today['Close']

        if sma_on:
            sma_val = df['Close'].iloc[:i+1].rolling(window=sma_length).mean().iloc[-1]
            if price <= sma_val:
                continue

        if vwap_on and df['VWAP_Diff'].iloc[i] < vwap_threshold:
            continue

        if news_on and not fetch_latest_headlines(symbol):
            continue

        qty = int(min(cash, max_trade_amount) // price)
        if qty > 0:
            cost = qty * price
            cash -= cost
            position += qty
            trades.append({
                'action': 'BUY',
                'date': str(today.name),
                'qty': qty,
                'price': price
            })
            if log_to_db:
                log_backtest_trade(run_id, symbol, 'BUY', price, qty, str(today.name), None)

    # Sell all at end
    if position > 0:
        final_price = df['Close'].iloc[-1]
        cash += position * final_price
        trades.append({
            'action': 'SELL',
            'date': str(df.index[-1]),
            'qty': position,
            'price': final_price
        })
        if log_to_db:
            log_backtest_trade(run_id, symbol, 'SELL', final_price, position, str(df.index[-1]), None)

    net_return = cash - initial_cash
    if log_to_db:
        conn = sqlite3.connect(BACKTEST_DB)
        conn.execute("UPDATE backtest_runs SET summary_json=? WHERE id=?", (json.dumps({'net_return': net_return}), run_id))
        conn.commit()
        conn.close()

    return trades, float(net_return)


    # ← EVERYTHING FROM HERE MUST BE INDENTED INSIDE THIS FUNCTION!

    df = yf.download(symbol, start=start_date, end=end_date, progress=False)

    # ✅ Flatten MultiIndex columns: use LEVEL 0 (Open, High, Low, etc.)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    print(f"[DEBUG] Flattened columns for {symbol}: {df.columns.tolist()}")


    if df is None or df.empty:
        raise ValueError(f"No data for {symbol} from {start_date} to {end_date}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    cols = list(df.columns)
    lower = [str(c).lower() for c in cols]

    print(f"[DEBUG] {symbol} → Available columns: {cols}")

    try:
        high_col = cols[lower.index('high')]
        low_col = cols[lower.index('low')]
        close_col = cols[lower.index('close')]
    except ValueError:
        raise KeyError(f"[{symbol}] Missing required column(s): expected ['High', 'Low', 'Close'], got {cols}")


    tp = (df[high_col] + df[low_col] + df[close_col]) / 3
    df = calculate_indicators(df)

    cash, position = initial_cash, 0
    trades = []
    run_id = None
    if log_to_db:
        run_id = log_backtest_run(
            {'symbol': symbol, 'start': start_date, 'end': end_date, 'initial_cash': initial_cash},
            {'net_return': None}
        )

    for i in range(1, len(df)):
        today = df.iloc[i]
        if 'Open' in today.index:
            price = today['Open']
        elif 'Close' in today.index:
            price = today['Close']
        else:
            price = today.iloc[0]

        if sma_on:
            sma_res = compute_sma(df['Close'].iloc[:i+1], length=sma_length)
            sma_val = sma_res.iloc[-1] if hasattr(sma_res, 'iloc') else sma_res
            if price <= sma_val:
                continue

        if vwap_on:
            tp = (df['High'] + df['Low'] + df['Close']) / 3
            vol = df.get('Volume', pd.Series(dtype=float))
            vwap_ser = (tp * vol).cumsum() / vol.cumsum()
            if (price - vwap_ser.iloc[i]) < vwap_threshold:
                continue

        if news_on:
            if not fetch_latest_headlines(symbol):
                continue

    net_return = cash - initial_cash
    return trades, float(net_return)
