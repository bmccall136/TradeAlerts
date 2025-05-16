import yfinance as YF
import time
import logging
import sqlite3
import warnings
import requests
from datetime import datetime, time as dtime

# Suppress pandas future warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Parameters
CONFIDENCE_THRESHOLD = 75.0
SIM_DB_PATH = '/tradealerts/simulation.db'
MARKET_OPEN = dtime(hour=9, minute=30)
MARKET_CLOSE = dtime(hour=16, minute=0)
ALERT_ENDPOINT = 'http://127.0.0.1:5000/api/alerts'
SCAN_INTERVAL = 300  # seconds (5 minutes)

def get_symbols():
    try:
        with open('sp500_symbols.txt') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error("sp500_symbols.txt not found.")
        return []

def get_scalar(x):
    try:
        return float(x.item())
    except:
        return float(x)

def calculate_confidence(signals):
    return sum(signals) / len(signals) * 100

def is_held(symbol):
    conn = sqlite3.connect(SIM_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM holdings WHERE symbol = ?", (symbol,))
    held = cur.fetchone() is not None
    conn.close()
    return held

def wait_for_market_open():
    now = datetime.now().time()
    if now < MARKET_OPEN or now > MARKET_CLOSE:
        logging.info("Market closed, sleeping for 60 seconds.")
        time.sleep(60)
        wait_for_market_open()

def post_alert(symbol, price, label, confidence, vwap):
    payload = {
        'symbol': symbol,
        'name': symbol,
        'signal': label,
        'confidence': confidence,
        'price': price,
        'vwap': vwap,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }
    try:
        response = requests.post(ALERT_ENDPOINT, json=payload)
        response.raise_for_status()
        logging.info("Posted alert for %s via POST", symbol)
    except requests.HTTPError as e:
        if e.response.status_code == 405:
            try:
                response = requests.get(ALERT_ENDPOINT, params=payload)
                response.raise_for_status()
                logging.info("Posted alert for %s via GET fallback", symbol)
            except Exception as ge:
                logging.error("Failed GET fallback for %s: %s", symbol, ge)
        else:
            logging.error("Failed POST for %s: %s", symbol, e)
    except Exception as exc:
        logging.error("Error posting alert for %s: %s", symbol, exc)

def analyze_symbol(symbol):
    df = YF.download(symbol, period='1d', interval='5m', auto_adjust=True, progress=False)
    if df.empty:
        return None

    close = get_scalar(df['Close'].iloc[-1])

    # Compute VWAP and coerce to float
    raw_vwap = (df['Close'] * df['Volume']).sum() / df['Volume'].sum()
    vwap = get_scalar(raw_vwap)

    # MACD
    exp1 = df['Close'].ewm(span=12).mean()
    exp2 = df['Close'].ewm(span=26).mean()
    macd_series = exp1 - exp2
    signal_line = macd_series.ewm(span=9).mean()
    macd_last = get_scalar(macd_series.iloc[-1])
    macd_prev = get_scalar(macd_series.iloc[-2])
    sig_last = get_scalar(signal_line.iloc[-1])
    sig_prev = get_scalar(signal_line.iloc[-2])

    # RSI
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(window=14).mean() / down.rolling(window=14).mean()
    rsi_last = get_scalar((100 - (100 / (1 + rs))).iloc[-1])

    # Bollinger Bands
    bb_mid = df['Close'].rolling(window=20).mean()
    bb_std = df['Close'].rolling(window=20).std()
    bb_last = get_scalar((bb_mid + 2 * bb_std).iloc[-1])

    # Volume Spike
    vol_last = get_scalar(df['Volume'].iloc[-1])
    vol_avg5 = get_scalar(df['Volume'].rolling(window=5).mean().iloc[-1])

    signals = [
        macd_last > sig_last,
        rsi_last > 50,
        close > bb_last,
        vol_last > vol_avg5
    ]
    confidence = calculate_confidence(signals)

    # Sell logic
    macd_down = (macd_prev > sig_prev) and (macd_last < sig_last)
    sell_signal = (rsi_last >= 78) and macd_down and ((macd_last - sig_last) < -0.2)

    return {
        'symbol': symbol,
        'close': close,
        'confidence': confidence,
        'sell': sell_signal,
        'vwap': vwap
    }

def classify_alert(confidence, sell):
    if sell:
        return 'SELL'
    if confidence >= 100.0:
        return 'Prime'
    return 'Sharpshooter'

def scan_once(symbols):
    sent = []
    for symbol in symbols:
        time.sleep(0.1)
        result = analyze_symbol(symbol)
        if not result:
            continue

        is_buy = result['confidence'] >= CONFIDENCE_THRESHOLD
        is_sell = result['sell']
        if is_sell and not is_held(symbol):
            continue
        if not (is_buy or is_sell):
            continue

        label = classify_alert(result['confidence'], is_sell)
        logging.info("Symbol=%s, Price=%.2f, Filter=%s, Confidence=%.1f%%",
                     result['symbol'], result['close'], label, result['confidence'])
        post_alert(result['symbol'], result['close'], label, result['confidence'], result['vwap'])
        sent.append((result['symbol'], label))
    logging.info("Scan complete: %d alerts sent", len(sent))

def main():
    symbols = get_symbols()
    if not symbols:
        return
    while True:
        wait_for_market_open()
        logging.info("Market open; scanning %d symbols", len(symbols))
        scan_once(symbols)
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    main()
