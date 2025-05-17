import json
import logging
import yfinance as yf
from .alert_service import insert_alert
from .news_service import news_sentiment

logger = logging.getLogger(__name__)

def get_symbols(simulation=False):
    with open('sp500_symbols.txt') as f:
        return [line.strip() for line in f if line.strip()]

def fetch_data(sym, period='1d', interval='5m'):
    """
    Fetch recent intraday data for a symbol.
    """
    return yf.Ticker(sym).history(period=period, interval=interval)

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, sig_line

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

def analyze_symbol(sym):
    # Fetch price data
    df = fetch_data(sym, period='1d', interval='5m')
    if df.empty:
        return None

    close_price = df['Close'].iloc[-1]
    macd_line, sig_line = calculate_macd(df['Close'])
    rsi_series = compute_rsi(df['Close'])
    vol = df['Volume'].iloc[-1]
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    bb_up, bb_mid, bb_dn = compute_bollinger(df['Close'])

    # Traditional triggers
    triggers = []
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        triggers.append('MACD 🚀')
    if rsi_series.iloc[-1] < 30:
        triggers.append('RSI 📉')
    if vol > avg_vol:
        triggers.append('VOL 🔊')
    if close_price > bb_up.iloc[-1] or close_price < bb_dn.iloc[-1]:
        triggers.append('BB 📈')

    base_count = len(triggers)
    sentiment = None

    # Fetch news sentiment if at least 2 triggers
    if base_count >= 2:
        sentiment = news_sentiment(sym)
        if sentiment > 0.05:
            triggers.append('News 📰')

    # Determine alert type and confidence
    if base_count >= 3:
        alert_type = 'Prime'
        confidence = 100
    elif base_count == 2:
        alert_type = 'Sharpshooter'
        confidence = 75
    else:
        return None  # fewer than 2 triggers, no alert

    # Bump confidence for positive news sentiment
    if sentiment and sentiment > 0.05:
        confidence = min(100, confidence + 10)

    spark = json.dumps(df['Close'].tolist())
    alert = {
        'symbol': sym,
        'price': close_price,
        'filter_name': alert_type,
        'confidence': confidence,
        'spark': spark,
        'triggers': ",".join(triggers)
    }

    insert_alert(**alert)

    if sentiment is not None:
        logger.info(f"→ {sym} | {alert_type} | ${close_price:.2f} | {confidence:.1f}% | NewsSentiment={sentiment:.2f}")
    else:
        logger.info(f"→ {sym} | {alert_type} | ${close_price:.2f} | {confidence:.1f}%")

    return alert
