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
in_position = False
entry_index = None

for i in range(1, len(df)):
    price = df['Close'].iat[i]

    # entry logic
    if buy_signal(i):
        if not settings.single_entry_only or not in_position:
            qty = compute_qty(...)
            buy(...)
            in_position = True
            entry_index = i

    # trailing‐stop exit
    if in_position and settings.use_trailing_stop:
        high_since_entry = df['High'].iloc[entry_index:i+1].max()
        if price <= high_since_entry * (1 - settings.trailing_stop_pct):
            sell(...)
            in_position = False

    # time‐stop exit
    if in_position and settings.sell_after_days is not None:
        days_in_trade = (df.index[i] - df.index[entry_index]).days
        if days_in_trade >= settings.sell_after_days:
            sell(...)
            in_position = False

def _has_headlines(src):
    if hasattr(src, "empty"):
        return not src.empty
    try:
        return len(src) > 0
    except:
        return False

def calculate_indicators(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    df["Close"] = close.astype(float)

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    # Bollinger Bands
    mb = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["MB"], df["UB"], df["LB"] = mb, mb + 2 * std20, mb - 2 * std20

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
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            json.dumps(config),
            json.dumps(summary),
        ),
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
        INSERT INTO backtest_trades
          (run_id, symbol, action, price, qty, trade_time, pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, symbol, action, price, qty, str(trade_time), pnl),
    )
    conn.commit()
    conn.close()

def backtest(
    symbol,
    start_date,
    end_date,
    initial_cash,
    max_trade_amount,
    max_trade_per_stock=None,
    trailing_stop_pct=0.0,
    sell_after_days=None,
    sma_on=False,
    rsi_on=False,
    macd_on=False,
    bb_on=False,
    vwap_on=False,
    news_on=False,
    sma_length=20,
    rsi_len=14,
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    bb_length=20,
    bb_std=2.0,
    vol_multiplier=1.0,
    vwap_threshold=0.0,
    log_to_db=False,
    **kwargs,
):
    # allow dashboard override
    if max_trade_per_stock is not None:
        max_trade_amount = max_trade_per_stock

    # if logging, create a run entry first
    run_id = None
    if log_to_db:
        config = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "initial_cash": initial_cash,
            "max_trade_amount": max_trade_amount,
            "sma_on": sma_on,
            "sma_length": sma_length,
            "vwap_on": vwap_on,
            "vwap_threshold": vwap_threshold,
            "news_on": news_on,
        }
        summary = {}  # you can fill this in after
        run_id = log_backtest_run(config, summary)

    yf_sym = symbol.replace(".", "-")
    try:
        df = yf.Ticker(yf_sym).history(
            start=start_date, end=end_date, interval="1d", auto_adjust=False
        )
    except Exception as e:
        logger.error(f"Fetch failed for {symbol}: {e}")
        return [], 0.0

    if df is None or df.empty:
        logger.warning(f"No data for {symbol}, skipping.")
        return [], 0.0

    # compute indicators + VWAP
    df = calculate_indicators(df)
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    vwap_ser = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    df["VWAP_Diff"] = df["Close"] - vwap_ser

    trades = []
    cash = initial_cash
    position = 0

    for i in range(1, len(df)):
        price = df["Open"].iat[i] if "Open" in df.columns else df["Close"].iat[i]

        if sma_on:
            sma = df["Close"].iloc[: i + 1].rolling(sma_length).mean().iat[-1]
            if price <= sma:
                continue

        if vwap_on and df["VWAP_Diff"].iat[i] < vwap_threshold:
            continue

        if news_on and not _has_headlines(fetch_latest_headlines(symbol)):
            continue

        raw_qty = (min(cash, max_trade_amount) // price).item() if hasattr(
            (min(cash, max_trade_amount) // price), "item"
        ) else min(cash, max_trade_amount) // price
        qty = int(raw_qty)
        if qty <= 0:
            continue

        # BUY
        cash -= qty * price
        position += qty
        trades.append(
            {
                "symbol": symbol,
                "action": "BUY",
                "date": str(df.index[i]),
                "qty": qty,
                "price": price,
                "pnl": 0.0,
            }
        )
        if log_to_db and run_id:
            log_backtest_trade(run_id, symbol, "BUY", price, qty, df.index[i], 0.0)

    # SELL any remaining
    net_pnl = 0.0
    if position > 0:
        final_price = df["Close"].iat[-1]
        cash += position * final_price
        net_pnl = cash - initial_cash
        trades.append(
            {
                "symbol": symbol,
                "action": "SELL",
                "date": str(df.index[-1]),
                "qty": position,
                "price": final_price,
                "pnl": round(net_pnl, 2),
            }
        )
        if log_to_db and run_id:
            log_backtest_trade(
                run_id, symbol, "SELL", final_price, position, df.index[-1], round(net_pnl, 2)
            )

    return trades, float(net_pnl)

# alias for dashboard
backtest_scanner = backtest




# alias for your Flask app
backtest_scanner = backtest
