# services/indicators.py

import pandas as pd
import math

def price_above_sma(price_series: pd.Series, length: int = 20) -> bool:
    """
    Return True if the last price is above its SMA(length), given
    a pandas Series of prices.
    """
    # compute the rolling SMA over the series
    sma = price_series.rolling(window=length).mean()
    # if there isn’t enough data yet or SMA is NaN, bail out
    if len(sma) < length or pd.isna(sma.iloc[-1]):
        return False
    # compare last price to last SMA
    return price_series.iloc[-1] > sma.iloc[-1]


# services/indicators.py

def daily_range_pct(df: pd.DataFrame) -> float:
    """
    Compute the latest day’s high-low range as a percentage of the low.
    Expects df with lowercase columns ['high','low'], indexed chronologically.
    Returns a float: (High_today - Low_today) / Low_today * 100.
    """
    # pick the right columns
    high_col = 'high' if 'high' in df.columns else 'High'
    low_col  = 'low'  if 'low'  in df.columns else 'Low'

    high = df[high_col].iloc[-1]
    low  = df[low_col].iloc[-1]
    if low == 0:
        return 0.0
    return (high - low) / low * 100


def gap_up_pct(df: pd.DataFrame) -> float:
    """
    Compute the latest gap-up percentage from yesterday’s close to today’s open.
    Expects df with lowercase ['open','close'] columns, indexed chronologically.
    Returns a float: (Open_today - Close_yesterday) / Close_yesterday * 100.
    """
    # pick the right column names (lowercase-first)
    open_col  = 'open'  if 'open'  in df.columns else 'Open'
    close_col = 'close' if 'close' in df.columns else 'Close'

    # need at least two bars to compute a gap
    if len(df) < 2:
        return 0.0

    prev_close = df[close_col].iloc[-2]
    today_open = df[open_col].iloc[-1]

    if prev_close == 0:
        return 0.0

    return (today_open - prev_close) / prev_close * 100

def calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> (pd.Series, pd.Series):
    """
    Compute the MACD and signal line for the given price series.
    - fast, slow, signal: integer periods for EMAs.
    Returns (macd_line, signal_line) as Pandas Series of the same length as series.
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


import pandas as pd

def compute_rsi(obj, length):
    # if you passed a Series, just use it directly
    if isinstance(obj, pd.Series):
        close = obj
    else:
        # otherwise assume DataFrame with a "Close" column
        close = obj["Close"]
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(data, fast, slow, signal):
    """Accepts either a pd.Series of closes or a DataFrame with .columns including 'close' or 'Close'."""
    if isinstance(data, pd.Series):
        close = data
    else:
        key = 'close' if 'close' in data.columns else 'Close'
        close = data[key]

    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    sig_line  = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, sig_line

def compute_bollinger(
    series: pd.Series,
    window: int = 20,
    num_std: float = 2.0
) -> (pd.Series, pd.Series, pd.Series):
    """
    Compute Bollinger Bands:
    - window: lookback period for the SMA
    - num_std: number of standard deviations
    Returns (upper_band, middle_band, lower_band) as three Pandas Series.
    """
    middle = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    return upper, middle, lower


def compute_sma(
    series: pd.Series,
    length: int = 20
) -> float:
    """
    Compute the most recent Simple Moving Average (SMA) over `length` bars.
    Returns a single float (the last SMA value).
    """
    return series.rolling(window=length).mean().iloc[-1]


def compute_atr(
    df: pd.DataFrame,
    period: int = 14
) -> float:
    """
    Compute the most recent ATR over `period` daily bars.
    Expects df with columns ['high','low','close'] indexed by date.
    Returns a single float (the last ATR value).
    """
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    return atr


def compute_daily_range_pct(
    df: pd.DataFrame
) -> float:
    """
    Compute the high-low percent range of the most recent daily bar.
    Expects df with ['high','low','close'] and at least 2 rows.
    Returns a float (range_pct).
    """
    today = df.iloc[-1]
    prev_close = df['close'].shift(1).iloc[-1]
    range_pct = (today['high'] - today['low']) / prev_close
    return range_pct


def compute_gap_pct(
    prev_close: float,
    today_open: float
) -> float:
    """
    Compute pre-market gap percentage given yesterday's close and today's open.
    Returns a float gap_pct.
    """
    return (today_open - prev_close) / prev_close

import pandas as pd
import numpy as np
import math

def compute_vwap(
    df: pd.DataFrame,
    threshold: float = None
) -> float:
    """
    Compute the most recent VWAP (volume weighted average price)
    from a DataFrame with lower-cased columns ['high','low','close','volume'].
    
    The `threshold` argument is accepted for backwards compatibility but ignored here.
    """
    # sanity-check
    missing = [col for col in ("high","low","close","volume") if col not in df.columns]
    if missing:
        raise KeyError(f"compute_vwap: missing columns {missing} in df")

    # typical price × volume
    tp      = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol  = (tp * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()

    # avoid division by zero on the very first bars
    last_cum_vol = cum_vol.iloc[-1]
    if last_cum_vol == 0:
        return 0.0

    latest_vwap = tp_vol.iloc[-1] / last_cum_vol
    return float(latest_vwap)

import pandas as pd

def bb_bounds(df: pd.DataFrame, length: int, std: float):
    """
    Returns (upper_band, middle_band, lower_band) for Bollinger Bands.
    """
    ma  = df['close'].rolling(length).mean()
    sd  = df['close'].rolling(length).std()
    return ma + std * sd, ma, ma - std * sd

def compute_rsi(df: pd.DataFrame, length: int):
    """
    Returns a pandas Series of RSI values.
    """
    delta = df['close'].diff()
    up    = delta.clip(lower=0)
    down  = -delta.clip(upper=0)
    ma_up   = up.ewm(com=length-1, adjust=False).mean()
    ma_down = down.ewm(com=length-1, adjust=False).mean()
    rs      = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# services/indicators.py

import pandas as pd

import pandas as pd

# services/indicators.py

import pandas as pd

def compute_bollinger_bands(df_or_series, length: int, std: float):
    """
    Given either a DataFrame with a 'Close' column or a Series of closes,
    return (upper_band, middle_band, lower_band) as pd.Series.
    """
    # pick out the Close series
    if isinstance(df_or_series, pd.DataFrame):
        close = df_or_series['close']
    else:
        close = df_or_series

    # moving average and standard deviation
    ma = close.rolling(window=length).mean()
    sd = close.rolling(window=length).std()

    # bands
    upper = ma + std * sd
    lower = ma - std * sd

    return upper, ma, lower


def compute_volume_multiplier(df: pd.DataFrame, multiplier: float) -> pd.Series:
    """
    Return a boolean mask Series: True where df['Volume'] ≥ multiplier × avg_vol (20‑bar rolling).
    """
    avg_vol = df['volume'].rolling(window=20).mean()
    return df['volume'] >= multiplier * avg_vol

def compute_vwap(df: pd.DataFrame):
    """
    Volume‐weighted average price over the whole df.
    Returns a pd.Series of the same length.
    """
    vp = (df['close'] * df['Volume']).cumsum()
    v  = df['volume'].cumsum()
    return vp / v

# (You already have compute_atr, daily_range_pct, gap_up_pct, etc. defined above.)

# Make sure your __all__ (if any) includes these names, or simply rely on
# Python’s default of exporting everything that doesn’t start with “_”.
