import os
import time
import requests
import yfinance as yf
from dotenv import load_dotenv
from datetime import datetime
from services.signal_service import compute_buy_triggers, compute_sell_triggers

load_dotenv('.env')
SYMBOLS_FILE  = os.getenv('SYMBOLS_FILE', 'sp500.txt')
API_URL       = os.getenv('API_URL', 'http://localhost:5000/api/alerts')
INTERVAL      = int(os.getenv('NON_MARKET_SCAN_INTERVAL', '60'))

with open(SYMBOLS_FILE) as f:
    symbols = [s.strip().replace('.', '-') for s in f if s.strip()]

IGNORED_SIGNALS = {'opportunist'}

def main():
    print("[NON‑MARKET] Scanner Started (running continuously)\n")
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for sym in symbols:
            print(f"[NON‑MARKET {now}] Scanning {sym}")
            try:
                ticker = yf.Ticker(sym)
                df = ticker.history(
                    period="1d", interval="5m",
                    auto_adjust=True, prepost=True
                )
                if df.empty:
                    print(f"[NON‑MARKET {now}] No data for {sym}, skipping.")
                    continue
            except Exception as e:
                print(f"[{now}] Error fetching {sym}: {e}")
                continue

            buys  = compute_buy_triggers(df)
            sells = compute_sell_triggers(df)
            print(f"[NON‑MARKET {now}] Triggers for {sym}: buys={buys}, sells={sells}")

            if not (buys or sells):
                print(f"[NON‑MARKET {now}] No triggers for {sym}, skipping.")
                continue

            alert_type = 'sell' if sells else buys[0]
            trigs      = sells or buys

            if alert_type in IGNORED_SIGNALS:
                print(f"[NON‑MARKET {now}] {sym} signal '{alert_type}' ignored.")
                continue

            payload = {
                "symbol":     sym,
                "name":       (ticker.info.get('longName') or
                               ticker.info.get('shortName') or sym),
                "signal":     alert_type,
                "confidence": round((len(trigs) / len(df)) * 100, 1),
                "price":      round(df['Close'].iat[-1], 2),
                "timestamp":  now,
                "sparkline":  ",".join(f"{x:.2f}" for x in df['Close'].tail(20)),
                "triggers":   trigs,
                "vwap":       round(
                    (df['Close']*df['Volume']).cumsum().iat[-1] /
                    df['Volume'].cumsum().iat[-1],
                    2
                )
            }

            print(f"[NON‑MARKET {now}] Posting alert for {sym}: {payload}")
            try:
                resp = requests.post(API_URL, json=payload)
                resp.raise_for_status()
                print(f"[NON‑MARKET {now}] ✅ Posted {sym} ({alert_type})")
            except Exception as e:
                print(f"[NON‑MARKET {now}] ❌ Failed posting {sym}: {e}")

            time.sleep(1)

        print(f"[NON‑MARKET {now}] Cycle complete; sleeping {INTERVAL}s\n")
        time.sleep(INTERVAL)

if __name__ == '__main__':
    main()
