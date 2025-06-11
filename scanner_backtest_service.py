import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

from services.indicators import compute_sma, compute_rsi, calculate_macd, compute_bollinger
from services.news_service import fetch_latest_headlines

SP500_LIST = 'sp500_symbols.txt'

def load_symbols():
    with open(SP500_LIST) as f:
        return [line.strip() for line in f if line.strip()]

def backtest_scanner(
    start_date,
    end_date,
    initial_cash=10000,
    max_trade_per_stock=1000,
    trailing_stop_pct=0.05,
    sell_after_days=None,
    sma_on=False,
    sma_length=20,
    rsi_on=False,
    rsi_thresh=40,
    macd_on=False,
    bb_on=False,
    vwap_on=False,
    news_on=False
):
    symbols = load_symbols()
    trades = []
    cash = initial_cash

    for symbol in symbols:
        try:
            df = yf.download(symbol, start=start_date, end=end_date, interval='1d', progress=False)
            if df.empty or len(df) < 20:
                continue

            df['Date'] = df.index
            df['Close'] = df['Adj Close'] if 'Adj Close' in df else df['Close']

            if sma_on:
                df['SMA'] = compute_sma(df['Close'], length=sma_length)
            if rsi_on:
                df['RSI'] = compute_rsi(df['Close'])
            if macd_on:
                macd, signal = calculate_macd(df['Close'])
                df['MACD'] = macd
                df['Signal'] = signal
            if bb_on:
                df['UB'], df['MB'], df['LB'] = compute_bollinger(df['Close'])
            if vwap_on:
                tp = (df['High'] + df['Low'] + df['Close']) / 3
                df['VWAP'] = (tp * df['Volume']).cumsum() / df['Volume'].cumsum()
                df['VWAP_Diff'] = df['Close'] - df['VWAP']

            for i in range(1, len(df)):
                row = df.iloc[i]
                if sma_on and row['Close'] <= row.get('SMA', float('inf')):
                    continue
                if rsi_on and row.get('RSI', 0) < rsi_thresh:
                    continue
                if macd_on and row.get('MACD', 0) <= row.get('Signal', 0):
                    continue
                if bb_on and row['Close'] <= row.get('UB', 0):
                    continue
                if vwap_on and row.get('VWAP_Diff', 0) < 0:
                    continue
                if news_on and not fetch_latest_headlines(symbol):
                    continue

                buy_price = row['Close']
                buy_date = row['Date']
                qty = int(min(cash, max_trade_per_stock) // buy_price)
                if qty == 0:
                    break
                cost = qty * buy_price
                cash -= cost

                sell_price = None
                sell_date = None
                for j in range(i + 1, len(df)):
                    future_row = df.iloc[j]
                    price = future_row['Close']
                    if price <= buy_price * (1 - trailing_stop_pct):
                        sell_price = price
                        sell_date = future_row['Date']
                        break
                    if sell_after_days and (future_row['Date'] - buy_date).days >= sell_after_days:
                        sell_price = price
                        sell_date = future_row['Date']
                        break

                if not sell_price:
                    sell_price = df['Close'].iloc[-1]
                    sell_date = df['Date'].iloc[-1]

                proceeds = qty * sell_price
                pnl = proceeds - cost
                cash += proceeds

                trades.append({
                    'symbol': symbol,
                    'buy_date': str(buy_date.date()),
                    'buy_price': round(buy_price, 2),
                    'sell_date': str(sell_date.date()),
                    'sell_price': round(sell_price, 2),
                    'qty': qty,
                    'pnl': round(pnl, 2)
                })
                break

        except Exception as e:
            print(f"[{symbol}] Error: {e}")

    total_pnl = sum(t['pnl'] for t in trades)
    print(f"Total P/L: ${round(total_pnl, 2)} from {len(trades)} trades")
    for t in trades:
        print(t)

if __name__ == '__main__':
    backtest_scanner(
        start_date='2023-01-01',
        end_date='2024-01-01',
        initial_cash=10000,
        max_trade_per_stock=1000,
        trailing_stop_pct=0.05,
        sell_after_days=10,
        sma_on=True,
        rsi_on=True,
        macd_on=True,
        bb_on=False,
        vwap_on=False,
        news_on=False
    )