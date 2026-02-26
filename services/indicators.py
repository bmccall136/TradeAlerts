# services/indicators.py

import numpy as np
import pandas as pd


def compute_supertracker(history, fast_len, slow_len, signal_len):
    # 1) compute your two ATRs
    atr_fast = compute_atr(history, fast_len)
    atr_slow = compute_atr(history, slow_len)

    # 2) wrap floats into single‐element Series
    last_idx = history.index[-1]
    if not isinstance(atr_fast, pd.Series):
        atr_fast = pd.Series([atr_fast], index=[last_idx])
    if not isinstance(atr_slow, pd.Series):
        atr_slow = pd.Series([atr_slow], index=[last_idx])

    # 3) guard against zero‐division, coerce to float Series
    atr_slow = atr_slow.replace(0, np.nan).astype(float)
    ratio = atr_fast.astype(float).divide(atr_slow)

    # 4) oscillator
    osc = 100 * (ratio - 1)

    # 5) future‐proofed back‐fill (no more .fillna(method="bfill") warnings)
    osc = osc.ffill().bfill()

    # 6) signal line via EWMA
    sig = osc.ewm(span=signal_len, adjust=False).mean()

    return osc, sig


def compute_adx(history, length=14):
    """Compute the Average Directional Index (ADX) from OHLCV history DataFrame.
    Returns a pd.Series, same length as history['close'].
    Expects columns: 'high', 'low', 'close'.
    """
    high = history["high"]
    low = history["low"]
    close = history["close"]

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    minus_dm[low.diff() > 0] = 0
    plus_dm[high.diff() < 0] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(length, min_periods=1).mean()
    plus_di = 100 * (plus_dm.rolling(length, min_periods=1).sum() / atr)
    minus_di = 100 * (minus_dm.rolling(length, min_periods=1).sum() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(length, min_periods=1).mean()
    return adx.fillna(0)


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
def rma_tv(series, length: int):
    """
    TradingView-style RMA (Wilder smoothing) with SMA seed.
    This matches TV's ATR/ADX smoothing behavior better than pandas ewm().
    """
    s = series.astype(float).copy()
    out = s.copy() * 0.0
    out[:] = float("nan")
    if len(s) < length:
        return out

    # seed with SMA of first 'length' values
    out.iloc[length - 1] = s.iloc[:length].mean()

    # Wilder smoothing
    for i in range(length, len(s)):
        out.iloc[i] = (out.iloc[i - 1] * (length - 1) + s.iloc[i]) / length

    return out

def daily_range_pct(df: pd.DataFrame) -> float:
    """
    Compute the latest day’s high-low range as a percentage of the low.
    Expects df with lowercase columns ['high','low'], indexed chronologically.
    Returns a float: (High_today - Low_today) / Low_today * 100.
    """
    # pick the right columns
    high_col = "high" if "high" in df.columns else "High"
    low_col = "low" if "low" in df.columns else "Low"

    high = df[high_col].iloc[-1]
    low = df[low_col].iloc[-1]
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
    open_col = "open" if "open" in df.columns else "Open"
    close_col = "close" if "close" in df.columns else "Close"

    # need at least two bars to compute a gap
    if len(df) < 2:
        return 0.0

    prev_close = df[close_col].iloc[-2]
    today_open = df[open_col].iloc[-1]

    if prev_close == 0:
        return 0.0

    return (today_open - prev_close) / prev_close * 100


def calculate_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
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
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(data, fast, slow, signal):
    """Accepts either a pd.Series of closes or a DataFrame with .columns including 'close' or 'Close'."""
    if isinstance(data, pd.Series):
        close = data
    else:
        key = "close" if "close" in data.columns else "Close"
        close = data[key]

    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, sig_line


def compute_bollinger(
    series: pd.Series, window: int = 20, num_std: float = 2.0
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


def compute_sma(series: pd.Series, length: int = 20) -> float:
    """
    Compute the most recent Simple Moving Average (SMA) over `length` bars.
    Returns a single float (the last SMA value).
    """
    return series.rolling(window=length).mean().iloc[-1]


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    TradingView-style ATR (Wilder RMA) over `period` bars.
    Expects df with columns ['high','low','close'] indexed by date/time.
    Returns the last ATR value.
    """
    high = df["high"].astype(float)
    low  = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)

    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Not enough bars
    if len(tr) < period:
        return float("nan")

    atr = tr.copy()
    atr[:] = float("nan")

    # seed with SMA of first `period` TR values
    atr.iloc[period - 1] = tr.iloc[:period].mean()

    # Wilder smoothing
    for i in range(period, len(tr)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period

    return float(atr.iloc[-1])


def compute_daily_range_pct(df: pd.DataFrame) -> float:
    """
    Compute the high-low percent range of the most recent daily bar.
    Expects df with ['high','low','close'] and at least 2 rows.
    Returns a float (range_pct).
    """
    today = df.iloc[-1]
    prev_close = df["close"].shift(1).iloc[-1]
    range_pct = (today["high"] - today["low"]) / prev_close
    return range_pct


def compute_gap_pct(prev_close: float, today_open: float) -> float:
    """
    Compute pre-market gap percentage given yesterday's close and today's open.
    Returns a float gap_pct.
    """
    return (today_open - prev_close) / prev_close


import pandas as pd


def compute_vwap(df: pd.DataFrame, threshold: float = None) -> float:
    """
    Compute the most recent VWAP (volume weighted average price)
    from a DataFrame with lower-cased columns ['high','low','close','volume'].

    The `threshold` argument is accepted for backwards compatibility but ignored here.
    """
    # sanity-check
    missing = [
        col for col in ("high", "low", "close", "volume") if col not in df.columns
    ]
    if missing:
        raise KeyError(f"compute_vwap: missing columns {missing} in df")

    # typical price × volume
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol = (tp * df["volume"]).cumsum()
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
    ma = df["close"].rolling(length).mean()
    sd = df["close"].rolling(length).std()
    return ma + std * sd, ma, ma - std * sd


def compute_rsi(obj, length: int = 14):
    """
    Flexible RSI:
      - accepts a pd.Series of closes
      - OR a DataFrame containing close/Close/price/last columns
    Returns a pd.Series RSI aligned to the input series index.
    """
    import pandas as pd

    if obj is None:
        return pd.Series(dtype=float)

    # --- Get close series ---
    if hasattr(obj, "dtype") and hasattr(obj, "diff"):
        # likely a Series
        close = pd.to_numeric(obj, errors="coerce").astype(float)
    else:
        # assume DataFrame-like
        df = obj
        col = None
        for c in ("close", "Close", "price", "last", "lastPrice"):
            if hasattr(df, "columns") and c in df.columns:
                col = c
                break
        if col is None:
            raise ValueError("compute_rsi(): could not find a close/price column")
        close = pd.to_numeric(df[col], errors="coerce").astype(float)

    length = int(length) if length else 14
    if length < 2:
        length = 2

    delta = close.diff()

    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder's smoothing (EMA alpha=1/length) is common for RSI
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = pd.to_numeric(rsi, errors="coerce")
    return rsi.fillna(0.0)



# services/indicators.py

# services/indicators.py
import pandas as pd


def compute_bollinger_bands(df_or_series, length: int, std: float):
    """
    Given either a DataFrame with a 'Close' column or a Series of closes,
    return (upper_band, middle_band, lower_band) as pd.Series.
    """
    # pick out the Close series
    if isinstance(df_or_series, pd.DataFrame):
        close = df_or_series["close"]
    else:
        close = df_or_series

    # moving average and standard deviation
    ma = close.rolling(window=length).mean()
    sd = close.rolling(window=length).std()

    # bands
    upper = ma + std * sd
    lower = ma - std * sd

    return upper, ma, lower


def compute_volume_multiplier(df: pd.DataFrame, multiplier: float = 1.5, window: int = 20) -> pd.Series:
    """
    Returns a numeric ratio Series: volume / rolling_avg_volume.
    Pass condition: ratio >= multiplier.

    Fix: intraday feeds often show 0 volume for the current/last minute.
    If the last bar volume is 0, substitute the last non-zero volume from a short lookback
    so scans don't falsely fail the VOL filter.
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return pd.Series([], dtype=float)

    # Accept either 'volume' or 'Volume'
    if "volume" in df.columns:
        vol_raw = df["volume"]
    elif "Volume" in df.columns:
        vol_raw = df["Volume"]
    else:
        # no volume column -> return zeros so it never passes
        return pd.Series([0.0] * len(df), index=df.index, dtype=float)

    vol = pd.to_numeric(vol_raw, errors="coerce").astype(float).fillna(0.0)

    # If last minute volume is 0, use last non-zero from recent lookback (common on live 1m)
    try:
        if len(vol) > 2 and float(vol.iloc[-1]) == 0.0:
            tail = vol.tail(10)
            nz = tail[tail > 0]
            if len(nz) > 0:
                vol = vol.copy()
                vol.iloc[-1] = float(nz.iloc[-1])
    except Exception:
        pass

    # Rolling avg; avoid divide-by-zero
    avg = vol.rolling(window=window, min_periods=1).mean()
    avg = avg.where(avg > 0, pd.NA)

    ratio = (vol / avg).fillna(0.0).astype(float)
    return ratio

def compute_vwap(df: pd.DataFrame, threshold: float = 0.0):
    """
    Flexible VWAP:
      - accepts DataFrame with typical OHLCV columns
      - ignores 'threshold' (kept for compatibility with older call sites)
    Returns a pd.Series VWAP.
    """
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)

    cols = set(df.columns) if hasattr(df, "columns") else set()

    # If VWAP already exists, just return it
    for c in ("vwap", "VWAP"):
        if c in cols:
            return pd.to_numeric(df[c], errors="coerce").astype(float).fillna(0.0)

    # Compute VWAP from OHLCV (fallbacks included)
    close_col = "close" if "close" in cols else ("Close" if "Close" in cols else None)
    high_col  = "high"  if "high"  in cols else ("High"  if "High"  in cols else None)
    low_col   = "low"   if "low"   in cols else ("Low"   if "Low"   in cols else None)
    vol_col   = "volume" if "volume" in cols else ("Volume" if "Volume" in cols else None)

    if vol_col is None:
        raise ValueError("compute_vwap(): volume column not found")

    vol = pd.to_numeric(df[vol_col], errors="coerce").astype(float).fillna(0.0)

    if high_col and low_col and close_col:
        high = pd.to_numeric(df[high_col], errors="coerce").astype(float)
        low  = pd.to_numeric(df[low_col], errors="coerce").astype(float)
        close = pd.to_numeric(df[close_col], errors="coerce").astype(float)
        typical = (high + low + close) / 3.0
    elif close_col:
        typical = pd.to_numeric(df[close_col], errors="coerce").astype(float)
    else:
        # last resort: try price/last
        for c in ("price", "last", "lastPrice"):
            if c in cols:
                typical = pd.to_numeric(df[c], errors="coerce").astype(float)
                break
        else:
            raise ValueError("compute_vwap(): no usable price column found")

    pv = (typical.fillna(0.0) * vol)
    cum_vol = vol.cumsum().replace(0.0, pd.NA)
    vwap = pv.cumsum() / cum_vol
    vwap = pd.to_numeric(vwap, errors="coerce")
    return vwap.fillna(0.0)




