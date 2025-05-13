import os
import time
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import logging

# — Logging configuration —
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)

# Load config from .env

# Symbols file, default to sp500.txt
SYMBOLS_FILE = os.getenv('SP500_FILE', 'sp500.txt')
SYMBOLS_FILE  = os.getenv('SYMBOLS_FILE', 'sp500.txt')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '300'))
API_URL       = os.getenv('API_URL', 'http://localhost:5000/api/alerts')

# Load tickers list
try:
    with open(SYMBOLS_FILE) as f:
        symbols = [s.strip().replace('.', '-') for s in f if s.strip()]
    logging.info(f"Loaded {len(symbols)} symbols from {SYMBOLS_FILE}")
except FileNotFoundError:
    logging.warning(f"Missing {SYMBOLS_FILE}, using sample list")
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']

# Indicator functions ...
# (Keep your existing compute_buy_triggers, compute_sell_trigger,
#  calculate_rsi, calculate_macd, calculate_vwap, calculate_atr, etc.)

def main():
    logging.info("— Fullmode Scanner Started (unlimited alerts) —")
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        for sym in symbols:
            # Fetch and compute logic...
            # Build payload with your alert data
            payload = {
                "symbol": sym,
                "name": sym,
                # "signal": signal_type,
                # "confidence": confidence_score,
                # "price": current_price,
                # "sparkline": sparkline_data,
                # "vwap": vwap_value,
            }
            # Log outgoing payload
            logging.debug(f"Sending payload for {sym}: {payload}")
            try:
                r = requests.post(API_URL, json=payload, timeout=10)
                # Log response status and body
                logging.debug(f"Response for {sym}: {r.status_code} {r.text}")
                r.raise_for_status()
                logging.info(f"[{now}] Alert posted: {sym}")
            except Exception as e:
                logging.error(f"[{now}] Failed posting {sym}: {e}")
            time.sleep(1)
        logging.debug(f"Sleeping for {SCAN_INTERVAL} seconds…")
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    main()
