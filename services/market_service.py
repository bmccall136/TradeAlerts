# services/market_service.py
import json
import logging
from datetime import datetime
import yfinance as yf
from .alert_service import insert_alert

logger = logging.getLogger(__name__)

def get_symbols(simulation=False):
    # … your existing symbol‐list logic …
    with open('sp500_symbols.txt') as f:
        return [line.strip() for line in f if line.strip()]

def fetch_data(sym, period='5d', interval='1d'):
    return yf.Ticker(sym).history(period=period, interval=interval)

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig

def analyze_symbol(sym):
    df = fetch_data(sym)
    if df.empty:
        raise ValueError(f"No data for {sym}")

    close = df['Close'].iloc[-1]
    macd, macd_signal = calculate_macd(df['Close'])
    rsi = compute_rsi(df['Close'])            # assume compute_rsi returns a Series
    vol = df['Volume'].iloc[-1]
    bb_up, bb_mid, bb_dn = compute_bollinger(df['Close'])  # returns 3 Series

    # only look at the last point of each Series
    macd_now, sig_now = macd.iloc[-1], macd_signal.iloc[-1]
    rsi_now = rsi.iloc[-1]
    bb_up_now, bb_dn_now = bb_up.iloc[-1], bb_dn.iloc[-1]

    # your signal logic — ALL using `.iloc[-1]` or plain scalars
    triggers = []
    if macd_now > sig_now:
        triggers.append('MACD')
    if rsi_now < 30:
        triggers.append('RSI')
    if vol > df['Volume'].rolling(20).mean().iloc[-1]:
        triggers.append('VOL')
    if close > bb_up_now or close < bb_dn_now:
        triggers.append('BB')

    if not triggers:
        return None

    confidence = min(100.0, len(triggers) / 4 * 100)
    spark = json.dumps(df['Close'].tolist())
    alert = {
        'symbol': sym,
        'price': close,
        'filter_name': 'Prime',
        'confidence': confidence,
        'spark': spark,
        'triggers': ",".join(triggers)
    }
    insert_alert(**alert)
    logger.info(f"→ {sym} | Prime | ${close:.2f} | {confidence:.1f}%")
    return alert

# helpers: RSI & Bollinger
def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.ewm(com=period-1, adjust=False).mean()
    ma_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def compute_bollinger(series, window=20, num_std=2):
    mid = series.rolling(window).mean()
    std = series.rolling(window).std()
    return mid + num_std * std, mid, mid - num_std * std
