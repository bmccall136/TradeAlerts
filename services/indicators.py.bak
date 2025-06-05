# services/indicators.py

import pandas as pd

def calculate_macd(series: pd.Series, fast=12, slow=26, signal=9):
    """
    Returns (macd_line, signal_line) for the price series.
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def compute_rsi(series: pd.Series, period=14):
    """
    Returns the RSI series.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)

def compute_bollinger(series: pd.Series, window=20, num_std=2):
    """
    Returns (upper_band, mid_band, lower_band) as three series.
    """
    mid = series.rolling(window).mean()
    std = series.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower
