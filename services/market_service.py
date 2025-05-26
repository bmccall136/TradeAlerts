import json
import logging
import yfinance as yf

from .alert_service import insert_alert
from .news_service import news_sentiment
from .indicators import calculate_macd, compute_rsi, compute_bollinger

logger = logging.getLogger(__name__)

def get_symbols(simulation=False):
    with open('sp500_symbols.txt') as f:
        return [line.strip() for line in f if line.strip()]

def fetch_data(sym, period='1d', interval='5m'):
    return yf.Ticker(sym).history(period=period, interval=interval)

def analyze_symbol(sym):
    df = fetch_data(sym)
    if df.empty:
        return None

    close_price = df['Close'].iloc[-1]
    info = yf.Ticker(sym).info
    name = info.get("shortName", sym)
    macd_line, sig_line = calculate_macd(df['Close'])
    rsi_series = compute_rsi(df['Close'])
    vol = df['Volume'].iloc[-1]
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    bb_up, bb_mid, bb_dn = compute_bollinger(df['Close'])

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

    # only fetch news for Prime alerts to conserve free calls
    if base_count >= 3:
        sentiment = news_sentiment(sym)
        if sentiment > 0.05:
            triggers.append('News 📰')
        alert_type = 'Prime'
    else:
        return None

    spark = json.dumps(df['Close'].tolist())

    alert = {
        'symbol': sym,
        'alert_type': alert_type,
        'price': float(close_price),
        'triggers': ",".join(triggers),
        'sparkline': spark,
        'name': name
    }
    insert_alert(**alert)
    return alert
