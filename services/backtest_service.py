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

    import yfinance as yf
    import pandas as pd
    from datetime import datetime

    df = yf.download(symbol, start=start_date, end=end_date, interval='1d')

    if df.empty:
        return [], 0

    df['Date'] = df.index
    df['Signal'] = False
    df['Buy_Price'] = None

    if sma_on:
        df['SMA'] = df['Close'].rolling(window=sma_length).mean()
        df['Signal'] = df['Close'] > df['SMA']

    if vwap_on:
        df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
        df['VWAP_Diff'] = df['Close'] - df['VWAP']
        if 'Signal' in df:
            df['Signal'] &= df['VWAP_Diff'] >= vwap_threshold
        else:
            df['Signal'] = df['VWAP_Diff'] >= vwap_threshold

    # Example news_on logic placeholder
    if news_on:
        pass  # You can add custom logic if you have access to news sentiment

    trades = []
    cash = initial_cash
    position = 0
    buy_price = 0

    for i, row in df.iterrows():
        if row['Signal'] and cash >= row['Close']:
            qty = int(min(cash, max_trade_amount) // row['Close'])
            if qty > 0:
                cost = qty * row['Close']
                cash -= cost
                position += qty
                buy_price = row['Close']
                trades.append({
                    'action': 'BUY',
                    'date': row['Date'],
                    'qty': qty,
                    'price': row['Close']
                })

    # Sell all at end
    if position > 0:
        proceeds = position * df['Close'].iloc[-1]
        cash += proceeds
        trades.append({
            'action': 'SELL',
            'date': df['Date'].iloc[-1],
            'qty': position,
            'price': df['Close'].iloc[-1]
        })

    net_return = cash - initial_cash
    return trades, net_return

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
