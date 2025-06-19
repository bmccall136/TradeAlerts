import yfinance as yf
import pandas as pd
from services.news_service import fetch_latest_headlines

def backtest(
    symbol,
    start_date,
    end_date,
    initial_cash,
    max_trade_amount,
    max_trade_per_stock=None,
    trailing_stop_pct=0.0,
    sell_after_days=None,
    sma_on=False,
    rsi_on=False,
    macd_on=False,
    bb_on=False,
    vwap_on=False,
    news_on=False,
    sma_length=20,
    rsi_len=14,
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    bb_length=20,
    bb_std=2.0,
    vol_multiplier=1.0,
    vwap_threshold=0.0,       # ← ensure this is here
    log_to_db=False,
):


    # 1) Fetch data
    yf_symbol = symbol.replace('.', '-')
    df = yf.Ticker(yf_symbol).history(
        start=start_date,
        end=end_date,
        interval='1d',
        auto_adjust=False,
    )

    if df is None or df.empty:
        return [], 0.0

    # Precompute VWAP diff
    high, low, vol = df['High'], df['Low'], df['Volume']
    tp = (high + low + df['Close']) / 3
    vwap_ser = (tp * vol).cumsum() / vol.cumsum()
    df['VWAP_Diff'] = df['Close'] - vwap_ser

    trades = []
    cash = initial_cash
    position = 0
    entry_price = None
    peak_price = None
    entry_index = None

    # Loop through each day
    for i in range(1, len(df)):
        row = df.iloc[i]
        date = df.index[i]
        price = row['Open'] if 'Open' in df.columns else row['Close']

        # If no position, check entry filters
        if position == 0:
            if sma_on:
                sma = df['Close'].iloc[:i+1].rolling(20).mean().iloc[-1]
                if price <= sma:
                    continue
            if vwap_on and row['VWAP_Diff'] < vwap_threshold:
                continue
            if news_on and not fetch_latest_headlines(symbol):
                continue

            # Enter position
            qty = int(min(cash, max_trade_amount) // price)
            if qty <= 0:
                continue

            cash -= qty * price
            position = qty
            entry_price = price
            peak_price = price
            entry_index = i
            trades.append({
                'symbol': symbol,
                'action': 'BUY',
                'date': str(date),
                'qty': qty,
                'price': price,
                'pnl': 0.0
            })
            continue

        # If in position, update peak for trailing stop
        peak_price = max(peak_price, price)
        stop_price = peak_price * (1 - trailing_stop_pct)

        # Check trailing stop exit
        days_held = i - entry_index
        if (trailing_stop_pct and price <= stop_price) or \
           (sell_after_days is not None and days_held >= sell_after_days):
            cash += position * price
            pnl = cash - initial_cash
            trades.append({
                'symbol': symbol,
                'action': 'SELL',
                'date': str(date),
                'qty': position,
                'price': price,
                'pnl': round(pnl, 2)
            })
            position = 0
            break  # single-entry, stop after exit

    # Final sell if still holding at end
    if position > 0:
        final_price = df['Close'].iloc[-1]
        cash += position * final_price
        pnl = cash - initial_cash
        trades.append({
            'symbol': symbol,
            'action': 'SELL',
            'date': str(df.index[-1]),
            'qty': position,
            'price': final_price,
            'pnl': round(pnl, 2)
        })

    net_pnl = cash - initial_cash
    return trades, float(net_pnl)
# at the bottom of services/backtest_service.py

def run_full_backtest(settings, symbols):
    """
    Loop through each ticker, call the single-symbol backtest(),
    and build a trades list + summary dict.
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
            trailing_stop_pct=settings.trailing_stop_pct,
            sell_after_days=settings.sell_after_days,
            sma_on=settings.sma_on,
            rsi_on=settings.rsi_on,
            macd_on=settings.macd_on,
            bb_on=settings.bb_on,
            vwap_on=settings.vwap_on,
            news_on=settings.news_on,
            sma_length=settings.sma_length,
            rsi_len=settings.rsi_len,
            macd_fast=settings.macd_fast,
            macd_slow=settings.macd_slow,
            macd_signal=settings.macd_signal,
            bb_length=settings.bb_length,
            bb_std=settings.bb_std,
            vol_multiplier=settings.vol_multiplier,
            vwap_threshold=settings.vwap_threshold,
            log_to_db=False
        )

        all_trades.extend(trades)
        summary['total_pnl']  += net_pnl
        summary['num_trades'] += len(trades)
        wins   = sum(1 for t in trades if t['action']=='SELL' and t['pnl']>0)
        losses = sum(1 for t in trades if t['action']=='SELL' and t['pnl']<=0)
        summary['wins']   += wins
        summary['losses'] += losses
        summary['by_symbol'][symbol] = {
            'pnl':    net_pnl,
            'trades': len(trades),
            'wins':   wins,
            'losses': losses
        }

    return all_trades, summary

# Alias for dashboard
backtest_scanner = backtest
