#!/usr/bin/env python3
import os
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv
from services.market_service import fetch_etrade_price

load_dotenv('.env')

# Setup logging to file and console
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler('scanner.log')
fh.setLevel(logging.INFO)
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(ch)

# Configuration
SYMBOLS_FILE     = 'sp500_symbols.txt'
ALERT_ENDPOINT   = 'http://127.0.0.1:5000/api/alerts'
SCAN_INTERVAL    = 60    # seconds between full scans
ALERT_COOLDOWN   = timedelta(minutes=30)

def load_symbols(path=SYMBOLS_FILE):
    with open(path) as f:
        return [line.strip().upper() for line in f if line.strip()]

def is_market_open():
    now = datetime.now()
    # Mon–Fri, 9:30–16:00
    return not (
        now.weekday() >= 5 or
        now.hour < 9 or
        (now.hour == 9 and now.minute < 30) or
        now.hour >= 16
    )

def fetch_intraday(symbol):
    """Fetch 5 days of 5‑minute intraday data for a single symbol."""
    try:
        df = yf.download(
            tickers=symbol,
            period='5d',
            interval='5m',
            progress=False,
            threads=False
        )
        df = df.dropna(how='all')
        return df if not df.empty else None
    except Exception as e:
        print(f"[{symbol}] Intraday download error: {e}")
        return None

def send_alert(payload):
    try:
        resp = requests.post(ALERT_ENDPOINT, json=payload, timeout=5)
        resp.raise_for_status()
        logging.info(f"ALERT SENT {payload['symbol']} {payload['signal']} @ {payload['price']}")
    except Exception as e:
        print(f"Failed to send alert for {payload['symbol']}: {e}")

def main():
    symbols     = load_symbols()
    last_alerts = {}
    print(f"--- Scanner Started: {len(symbols)} symbols ---")

    while True:
        if not is_market_open():
            ts = datetime.now().strftime('%H:%M:%S')
            print(f"[{ts}] Market closed, sleeping 900s.")
            time.sleep(900)
            continue

        now = datetime.now()
        print(f"[{now.strftime('%H:%M:%S')}] Scanning {len(symbols)} symbols...")

        for symbol in symbols:
            # enforce cooldown
            if symbol in last_alerts and (now - last_alerts[symbol]) < ALERT_COOLDOWN:
                continue

            df = fetch_intraday(symbol)
            if df is None:
                continue

            latest_close = df['Close'].iloc[-1]
            avg_close = df['Close'].mean()
            cond = latest_close > avg_close
            if (hasattr(cond, 'any') and not cond.any()) or (not hasattr(cond, 'any') and not cond):
                continue

            # fetch E*TRADE price
            try:
                price = fetch_etrade_price(symbol)
                logging.info(f"{symbol} E*TRADE price returned: {price}")
            except Exception as e:
                print(f"[{symbol}] E*TRADE error: {e}")
                continue

            payload = {
                'symbol':    symbol,
                'signal':    'OPPORTUNIST',
                'price':     round(price, 2),
                'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
            }
            send_alert(payload)
            last_alerts[symbol] = now

        ts_end = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts_end}] Scan complete, sleeping {SCAN_INTERVAL}s.")
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    main()