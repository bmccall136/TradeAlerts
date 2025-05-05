
import os
import time
import requests
import yfinance as yf
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv('.env')

SYMBOLS_FILE = 'sp500_symbols.txt'
symbols = [s.strip().replace('.', '-') for s in open(SYMBOLS_FILE) if s.strip()]

MAX_ALERTS = 10
SCAN_INTERVAL = 30
last_alerts = {}

def is_market_open():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or (now.hour == 9 and now.minute < 30) or now.hour >= 16:
        return False
    df = yf.Ticker('AAPL').history(period='1d', interval='5m')
    return not df.empty and df.index[-1].date() == now.date()

def calculate_rsi(close_prices, period=14):
    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(close_prices):
    ema12 = close_prices.ewm(span=12, adjust=False).mean()
    ema26 = close_prices.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calculate_vwap(df):
    v = df['Volume']
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * v).cumsum() / v.cumsum()

def calculate_atr(df, period=14):
    high = df['High']; low = df['Low']; close = df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def two_bar_vwap_confirmation(df):
    vwap = calculate_vwap(df)
    last2 = df['Close'].iloc[-2:]
    return (last2 > vwap.iloc[-2:]).all(), vwap.iloc[-1]

def volume_spike(df):
    vol = df['Volume']
    avg20 = vol.rolling(20).mean().iloc[-1]
    return vol.iloc[-1] >= 1.2 * avg20

def trend_ok(df):
    ema50 = df['Close'].ewm(span=50, adjust=False).mean()
    ema100 = df['Close'].ewm(span=100, adjust=False).mean()
    return ema50.iloc[-1] > ema100.iloc[-1]

def atr_ok(df):
    atr = calculate_atr(df)
    open_atr = atr.iloc[0]
    return atr.iloc[-1] <= 1.2 * open_atr

def rsi_pullback(df):
    rsi = calculate_rsi(df['Close'])
    last2 = rsi.iloc[-2:]
    return (50 < last2.iloc[0] < 70) and (last2.iloc[-1] > 60)

print('--- Fullmode Scanner (Strict SELL first, real sparkline, full alert data) Started ---')

while True:
    if not is_market_open():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Market closed. Sleeping 15 min.")
        time.sleep(900)
        continue

    now = datetime.now()
    print(f"[{now.strftime('%H:%M:%S')}] Scanning {len(symbols)} symbols...")

    alert_count = 0
    stats = {'prime': 0, 'sharpshooter': 0, 'opportunist': 0, 'sell': 0}

    for symbol in symbols:
        try:
            if symbol in last_alerts and (now - last_alerts[symbol]).total_seconds() < 1800:
                continue

            ticker = yf.Ticker(symbol)
            df = ticker.history(period='5d', interval='5m')
            if df.empty or len(df) < 30:
                continue

            macd, signal = calculate_macd(df['Close'])
            vwap_ok, vwap_last = two_bar_vwap_confirmation(df)
            vol_ok = volume_spike(df)
            trend = trend_ok(df)
            atr_good = atr_ok(df)
            rsi_good = rsi_pullback(df)
            rsi_val = calculate_rsi(df['Close']).iloc[-1]
            macd_cross = macd.iloc[-2] < signal.iloc[-2] and macd.iloc[-1] > signal.iloc[-1]
            macd_down = macd.iloc[-2] > signal.iloc[-2] and macd.iloc[-1] < signal.iloc[-1]
            macd_drop_strength = macd.iloc[-1] - signal.iloc[-1]
            latest_price = df['Close'].iloc[-1]

            passes = sum([macd_cross, vwap_ok, vol_ok, trend, atr_good, rsi_good])

            signal_type = None
            buy_sell = "BUY"

            if rsi_val >= 78 and macd_down and macd_drop_strength < -0.2:
                signal_type = 'sell'
                buy_sell = "SELL"
            else:
                if passes == 6:
                    signal_type = 'prime'
                elif passes >= 4:
                    signal_type = 'sharpshooter'
                elif passes >= 2:
                    signal_type = 'opportunist'

            if not signal_type:
                continue

            print(f"[{symbol}] {passes}/6 passes -> {signal_type.upper()} | Price: {latest_price:.2f}")

            if signal_type:
                stats[signal_type] += 1
                try:
                    full_name = ticker.info.get('shortName', symbol)
                except:
                    full_name = symbol

                sparkline = ",".join([str(round(x, 2)) for x in df['Close'].tail(6)])

                if alert_count < MAX_ALERTS:
                    alert_id = f"{symbol}_{now.strftime('%Y%m%d_%H%M%S')}"
                    icon = {
                        'prime': '💎',
                        'sharpshooter': '🎯',
                        'opportunist': '👍',
                        'sell': '🔥'
                    }.get(signal_type, '')

                    payload = {
                        'symbol': symbol,
                        'name': full_name,
                        'signal': f"{icon} {signal_type.capitalize()}",
                        'confidence': 100,
                        'price': round(latest_price, 2),
                        'timestamp': now.strftime("%Y-%m-%d %H:%M:%S"),
                        'sparkline': sparkline,
                        'type': signal_type,
                        'buy_sell': buy_sell,
                        'vwap': round(vwap_last, 2),
                        'triggers': 'MACD,VWAP,RSI,VOLUME,TREND,ATR',
                        'chart_url': f"https://finance.yahoo.com/quote/{symbol}/chart",
                        'alert_id': alert_id
                    }
                    requests.post('http://localhost:5000/alerts', json=payload)
                    print(f"[{now.strftime('%H:%M:%S')}] {signal_type.upper()} Alert sent for {symbol}")
                    last_alerts[symbol] = now
                    alert_count += 1

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error processing {symbol}: {e}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete. Sleeping {SCAN_INTERVAL}s.")
    print(f"[SUMMARY] Prime: {stats['prime']} | Sharpshooter: {stats['sharpshooter']} | Opportunist: {stats['opportunist']} | Sell: {stats['sell']}")
    time.sleep(SCAN_INTERVAL)
