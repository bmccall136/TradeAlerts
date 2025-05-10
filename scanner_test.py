import os
import time
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

# Load configuration
load_dotenv('.env')
SYMBOLS_FILE  = os.getenv('SYMBOLS_FILE', 'sp500.txt')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '300'))
# Point to the API endpoint for ingesting alerts
API_URL       = os.getenv('API_URL', 'http://localhost:5000/api/alerts')

# Load ticker list
try:
    with open(SYMBOLS_FILE) as f:
        symbols = [s.strip().replace('.', '-') for s in f if s.strip()]
    print(f"[TEST] Loaded {len(symbols)} symbols from {SYMBOLS_FILE}")
except FileNotFoundError:
    print("[TEST] ⚠️ Could not find SYMBOLS_FILE, using default list")
    symbols = ['AAPL', 'MSFT', 'GOOGL']

# Helpers for indicators
def calculate_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calculate_vwap(df):
    v  = df['Volume']
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * v).cumsum() / v.cumsum()

# Compute buy/sell triggers
def compute_buy_triggers(df):
    t = []
    if df['Close'].iat[-1] > df['Close'].iat[-2]: t.append('TREND')
    if calculate_rsi(df['Close']).iat[-1] < 30: t.append('RSI')
    macd, sig = calculate_macd(df['Close'])
    if macd.iat[-1] > sig.iat[-1] and macd.iat[-2] <= sig.iat[-2]:
        t.append('MACD')
    if df['Close'].iat[-1] > calculate_vwap(df).iat[-1]: t.append('VWAP')
    return t

def compute_sell_triggers(df):
    t = []
    if df['Close'].iat[-1] < df['Close'].iat[-2]: t.append('TREND')
    if calculate_rsi(df['Close']).iat[-1] > 70: t.append('RSI')
    macd, sig = calculate_macd(df['Close'])
    if macd.iat[-1] < sig.iat[-1] and macd.iat[-2] >= sig.iat[-2]:
        t.append('MACD')
    if df['Close'].iat[-1] < calculate_vwap(df).iat[-1]: t.append('VWAP')
    return t

def main():
    print("[TEST] Scanner (ignoring market hours) Started")
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        for sym in symbols:
            # Fetch 5-min history including pre/post market hours
            try:
                df = yf.Ticker(sym).history(
                    period="1d", interval="5m", auto_adjust=True, prepost=True
                )
                if df.empty:
                    continue
            except Exception as e:
                print(f"[{now}] Error fetching {sym}: {e}")
                continue

            buys  = compute_buy_triggers(df)
            sells = compute_sell_triggers(df)
            if sells:
                side, trigs = 'SELL', sells
            elif buys:
                side, trigs = 'BUY',  buys
            else:
                continue

            price     = df['Close'].iat[-1]
            sparkline = ",".join(f"{x:.2f}" for x in df['Close'].tail(6))

            # Compute score and alert type
            macd_line, macd_signal = calculate_macd(df['Close'])
            macd_cross = (macd_line.iat[-2] < macd_signal.iat[-2] and
                          macd_line.iat[-1] > macd_signal.iat[-1])
            rsi_ok     = calculate_rsi(df['Close']).iat[-1] > 40
            ub         = df['Close'].rolling(20).mean() + 2 * df['Close'].rolling(20).std()
            breakout   = df['Close'].iat[-1] > ub.iat[-1]
            vol_spike  = df['Volume'].iat[-1] > df['Volume'].rolling(5).mean().iat[-1]
            raw_score  = sum([macd_cross, rsi_ok, breakout, vol_spike])
            confidence = round((raw_score / 4) * 100, 0)

            if breakout and macd_cross and rsi_ok and vol_spike:
                alert_type = 'prime'
            elif macd_cross and rsi_ok:
                alert_type = 'sharpshooter'
            elif breakout:
                alert_type = 'opportunist'
            else:
                alert_type = 'sell' if side == 'SELL' else 'opportunist'

            payload = {
                "symbol":     sym,
                "name":       sym,
                "signal":     alert_type,
                "confidence": confidence,
                "price":      round(price, 2),
                "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sparkline":  sparkline,
                "type":       alert_type,
                "buy_sell":   side,
                "vwap":       round(calculate_vwap(df).iat[-1], 2),
                "triggers":   trigs,
            }

            try:
                resp = requests.post(API_URL, json=payload)
                resp.raise_for_status()
                print(f"[{now}] [TEST] {side} {alert_type} | Conf={confidence}% | {sym}")
            except Exception as e:
                print(f"[{now}] Failed {sym}: {e}")

            time.sleep(1)
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()
