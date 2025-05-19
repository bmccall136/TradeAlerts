# services/market_service.py

import json
import logging
import yfinance as yf

from .alert_service import insert_alert
from .news_service import news_sentiment

# make sure you have these in your project under services/indicators.py
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
    macd_line, sig_line    = calculate_macd(df['Close'])
    rsi_series            = compute_rsi(df['Close'])
    vol                   = df['Volume'].iloc[-1]
    avg_vol               = df['Volume'].rolling(20).mean().iloc[-1]
    bb_up, bb_mid, bb_dn  = compute_bollinger(df['Close'])

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

    # only fetch news for Prime alerts to conserve your free calls
    if base_count >= 3:
        sentiment = news_sentiment(sym)
        if sentiment > 0.05:
            triggers.append('News 📰')

    # assign alert type based on number of technical triggers
    if base_count >= 3:
        alert_type = 'Prime'
        confidence = 100
    elif base_count == 2:
        alert_type = 'Sharpshooter'
        confidence = 75
    else:
        # no alert for fewer than 2 triggers
        return None

    # bump confidence for strong positive sentiment
    if sentiment is not None and sentiment > 0.05:
        confidence = min(100, confidence + 10)

    # prepare sparkline data
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

    info_extra = f" | NewsSentiment={sentiment:.2f}" if sentiment is not None else ""
    logger.info(f"→ {sym} | {alert_type} | ${close_price:.2f} | {confidence}%{info_extra}")

    return alert
