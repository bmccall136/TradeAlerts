import os
import time
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

# Load config
load_dotenv('.env')
SYMBOLS_FILE  = os.getenv('SYMBOLS_FILE', 'sp500.txt')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '300'))
API_URL       = os.getenv('API_URL', 'http://localhost:5000/api/alerts')

# Load tickers
try:
    with open(SYMBOLS_FILE) as f:
        symbols = [s.strip().replace('.', '-') for s in f if s.strip()]
    print(f"Loaded {len(symbols)} symbols from {SYMBOLS_FILE}")
except FileNotFoundError:
    print(f"⚠️ Missing {SYMBOLS_FILE}, using sample list")
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']

# Indicator functions ...
# (keep your existing compute_buy_triggers, compute_sell_triggers, calculate_rsi, calculate_macd, calculate_vwap, calculate_atr)

def main():
    print("--- Fullmode Scanner Started (unlimited alerts) ---")
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        for sym in symbols:
            # Fetch and compute logic...
            # Build payload with alert_type, confidence etc.
            payload = {
                "symbol": sym,
                "name": sym,
                # ...
            }
            try:
                r = requests.post(API_URL, json=payload)
                r.raise_for_status()
                print(f"[{now}] Alert posted: {sym}")
            except Exception as e:
                print(f"[{now}] Failed {sym}: {e}")
            time.sleep(1)
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    main()
