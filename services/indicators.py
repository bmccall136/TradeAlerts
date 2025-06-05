# services/indicators.py

import pandas as pd

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


def compute_rsi(
    series: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Compute the RSI (Relative Strength Index) over the given period.
    Returns a Pandas Series of length equal to `series`.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)


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
