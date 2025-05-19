import json
import logging
import yfinance as yf

from .alert_service import insert_alert
from .news_service import news_sentiment
from .indicators import calculate_macd, compute_rsi, compute_bollinger

logger = logging.getLogger(__name__)

def get_symbols(simulation=False):
    # always scan full S&P‑500 for live mode
    with open('sp500_symbols.txt') as f:
        return [s.strip() for s in f if s.strip()]

def fetch_data(sym, period='1d', interval='5m'):
    return yf.Ticker(sym).history(period=period, interval=interval)

def analyze_symbol(sym):
    df = fetch_data(sym)
    if df.empty:
        return None

    close_price = df['Close'].iloc[-1]
    macd_line, sig_line = calculate_macd(df['Close'])
    rsi_series         = compute_rsi(df['Close'])
    vol                = df['Volume'].iloc[-1]
    avg_vol            = df['Volume'].rolling(20).mean().iloc[-1]
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
    news_url  = ""

    # only fetch news for Prime candidates
    if base_count >= 3:
        sentiment, news_url = news_sentiment(sym)
        if sentiment > 0.05:
            # hyperlink the trigger text
            triggers.append(f'<a href="{news_url}" target="_blank">News 📰</a>')

    # only Prime alerts (>=3 triggers)
    if base_count < 3:
        return None

    alert_type = 'Prime'
    confidence = 100
    # boost confidence for strong sentiment
    if sentiment is not None and sentiment > 0.05:
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
    extra = f" | NewsSentiment={sentiment:.2f}" if sentiment is not None else ""
    logger.info(f"→ {sym} | {alert_type} | ${close_price:.2f} | {confidence}%{extra}")
    return alert
