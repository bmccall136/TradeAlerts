import pandas as pd
import yfinance as yf

def backtest_volume(symbol='AAPL', period='1mo', interval='5m', multipliers=None, forward_bars=1):
    if multipliers is None:
        multipliers = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    # Fetch data
    df = yf.Ticker(symbol).history(period=period, interval=interval)
    df = df.dropna()
    # Compute rolling average volume
    df['avg20_vol'] = df['Volume'].rolling(20).mean()
    results = []
    for m in multipliers:
        df['signal'] = df['Volume'] >= m * df['avg20_vol']
        # Calculate forward return
        df['forward_price'] = df['Close'].shift(-forward_bars)
        df['return'] = df['forward_price'] / df['Close'] - 1
        signals = df[df['signal']]
        if not signals.empty:
            avg_return = signals['return'].mean()
            count = signals.shape[0]
        else:
            avg_return, count = float('nan'), 0
        results.append({'multiplier': m, 'signals': count, 'avg_return': avg_return})
    return pd.DataFrame(results)

if __name__ == '__main__':
    df_results = backtest_volume()
    print(df_results.to_string(index=False))