import yfinance as yf
import pandas as pd
from services.news_service import fetch_latest_headlines


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute RSI, MACD, and Bollinger Bands.
    """
    # Ensure Close is float
    df['Close'] = df['Close'].astype(float)
    close = df['Close']
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    # MACD
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['MACD_SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    # Bollinger Bands
    mb = close.rolling(20).mean()
    std = close.rolling(20).std()
    df['BB_MID'] = mb
    df['BB_UP'] = mb + 2 * std
    df['BB_LOW'] = mb - 2 * std
    return df


def backtest(
    symbol: str,
    start_date: str,
    end_date: str,
    initial_cash: float,
    max_trade_amount: float,
    sma_on: bool,
    rsi_on: bool,
    macd_on: bool,
    bb_on: bool,
    vol_on: bool,
    vwap_on: bool,
    news_on: bool,
    sma_length: int,
    rsi_len: int,
    rsi_overbought: int,
    rsi_oversold: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    bb_length: int,
    bb_std: float,
    vol_multiplier: float,
    vwap_threshold: float,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    log_to_db: bool = False,
) -> (list, float):
    """
    Single-symbol backtest with optional stop-loss and take-profit.
    Returns trades list and net P&L.
    """
    # Fetch historical data
    df = yf.Ticker(symbol.replace('.', '-')).history(
        start=start_date,
        end=end_date,
        interval='1d',
        auto_adjust=False
    )
    if df is None or df.empty:
        return [], 0.0

    # Compute indicators
    df = calculate_indicators(df)
    # VWAP
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (tp * df['Volume']).cumsum() / df['Volume'].cumsum()
    df['VWAP_DIFF'] = df['Close'] - df['VWAP']

    trades = []
    cash = initial_cash
    position = 0
    entry_price = 0.0

    # Loop through each day
    for idx in range(1, len(df)):
        price = df['Open'].iat[idx] if 'Open' in df.columns else df['Close'].iat[idx]
        date = str(df.index[idx])

        # 1) EXIT: Stop-loss / Take-profit
        if position > 0:
            # Stop-loss
            if stop_loss_pct > 0 and price <= entry_price * (1 - stop_loss_pct):
                pnl = (price - entry_price) * position
                cash += position * price
                trades.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'date': date,
                    'qty': position,
                    'price': price,
                    'pnl': round(pnl, 2)
                })
                position = 0
                continue
            # Take-profit
            if take_profit_pct > 0 and price >= entry_price * (1 + take_profit_pct):
                pnl = (price - entry_price) * position
                cash += position * price
                trades.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'date': date,
                    'qty': position,
                    'price': price,
                    'pnl': round(pnl, 2)
                })
                position = 0
                continue

        # 2) ENTRY: Only if not in position
        if position == 0:
            # SMA filter
            if sma_on:
                sma = df['Close'].rolling(sma_length).mean().iat[idx]
                if price <= sma:
                    continue
            # VWAP filter
            if vwap_on and df['VWAP_DIFF'].iat[idx] < vwap_threshold:
                continue
            # News filter
            if news_on and fetch_latest_headlines(symbol).empty:
                continue

            # Determine quantity
            qty = int(min(cash, max_trade_amount) // price)
            if qty < 1:
                continue
            # BUY
            cash -= qty * price
            entry_price = price
            position = qty
            trades.append({
                'symbol': symbol,
                'action': 'BUY',
                'date': date,
                'qty': qty,
                'price': price,
                'pnl': None
            })

    # 3) FINAL SELL if still holding at end
    if position > 0:
        final_price = df['Close'].iat[-1]
        pnl = (final_price - entry_price) * position
        cash += position * final_price
        trades.append({
            'symbol': symbol,
            'action': 'SELL',
            'date': str(df.index[-1]),
            'qty': position,
            'price': final_price,
            'pnl': round(pnl, 2)
        })

    net_pnl = round(sum(t['pnl'] for t in trades if t['action']=='SELL'), 2)



def run_full_backtest(settings, symbols):
    """
    Iterate over symbols, call backtest(), and aggregate summary.
    """
    all_trades = []
    summary = {
        'total_pnl': 0.0,
        'num_trades': 0,
        'wins': 0,
        'losses': 0,
        'by_symbol': {}
    }
    for symbol in symbols:
        trades, net_pnl = backtest(
            symbol,
            settings.start_date,
            settings.end_date,
            settings.starting_cash,
            settings.max_per_trade,
            settings.sma_on,
            settings.rsi_on,
            settings.macd_on,
            settings.bb_on,
            settings.vol_on,
            settings.vwap_on,
            settings.news_on,
            settings.sma_length,
            settings.rsi_len,
            settings.rsi_overbought,
            settings.rsi_oversold,
            settings.macd_fast,
            settings.macd_slow,
            settings.macd_signal,
            settings.bb_length,
            settings.bb_std,
            settings.vol_multiplier,
            settings.vwap_threshold,
            stop_loss_pct=getattr(settings, 'stop_loss_pct', 0.0),
            take_profit_pct=getattr(settings, 'take_profit_pct', 0.0),
            log_to_db=False
        )
        all_trades.extend(trades)
        summary['total_pnl'] += net_pnl
        summary['num_trades'] += len(trades)
        wins = sum(1 for t in trades if t['action']=='SELL' and t['pnl']>0)
        losses = sum(1 for t in trades if t['action']=='SELL' and t['pnl']<=0)
        summary['wins'] += wins
        summary['losses'] += losses
        summary['by_symbol'][symbol] = {
            'pnl': net_pnl,
            'trades': len(trades),
            'wins': wins,
            'losses': losses
        }
    return all_trades, summary

# Alias for dashboard
backtest_scanner = run_full_backtest
