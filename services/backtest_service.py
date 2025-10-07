import pandas as pd
import yfinance as yf

from services.news_service import fetch_latest_headlines


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute RSI, MACD, and Bollinger Bands.
    """
    # Ensure Close is float
    df["Close"] = df["Close"].astype(float)
    close = df["Close"]
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))
    # MACD
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    # Bollinger Bands
    mb = close.rolling(20).mean()
    std = close.rolling(20).std()
    df["BB_MID"] = mb
    df["BB_UP"] = mb + 2 * std
    df["BB_LOW"] = mb - 2 * std
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
    df = yf.Ticker(symbol.replace(".", "-")).history(
        start=start_date, end=end_date, interval="1d", auto_adjust=False
    )
    if df is None or df.empty:
        return [], 0.0

    # Compute indicators
    df = calculate_indicators(df)
    # VWAP
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    df["VWAP_DIFF"] = df["Close"] - df["VWAP"]

    trades = []
    cash = initial_cash
    position = 0
    entry_price = 0.0

    # Loop through each day
    for idx in range(1, len(df)):
        price = df["Open"].iloc[idx] if "Open" in df.columns else df["Close"].iloc[idx]
        date = str(df.index[idx])

        # 1) EXIT: Stop-loss / Take-profit
        if position > 0:
            # Stop-loss
            if stop_loss_pct > 0 and price <= entry_price * (1 - stop_loss_pct):
                pnl = (price - entry_price) * position
                cash += position * price
                trades.append(
                    {
                        "symbol": symbol,
                        "action": "SELL",
                        "date": date,
                        "qty": position,
                        "price": price,
                        "pnl": round(pnl, 2),
                    }
                )
                position = 0
                continue
            # Take-profit
            if take_profit_pct > 0 and price >= entry_price * (1 + take_profit_pct):
                pnl = (price - entry_price) * position
                cash += position * price
                trades.append(
                    {
                        "symbol": symbol,
                        "action": "SELL",
                        "date": date,
                        "qty": position,
                        "price": price,
                        "pnl": round(pnl, 2),
                    }
                )
                position = 0
                continue

        # 2) ENTRY: Only if not in position
        if position == 0:
            # SMA filter
            if sma_on:
                sma = df["Close"].rolling(sma_length).mean().iloc[idx]
                if price <= sma:
                    continue
            # VWAP filter
            if vwap_on and df["VWAP_DIFF"].iloc[idx] < vwap_threshold:
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
            trades.append(
                {
                    "symbol": symbol,
                    "action": "BUY",
                    "date": date,
                    "qty": qty,
                    "price": price,
                    "pnl": None,
                }
            )

    # 3) FINAL SELL if still holding at end
    if position > 0:
        final_price = df["Close"].iloc[-1]
        pnl = (final_price - entry_price) * position
        cash += position * final_price
        trades.append(
            {
                "symbol": symbol,
                "action": "SELL",
                "date": str(df.index[-1]),
                "qty": position,
                "price": final_price,
                "pnl": round(pnl, 2),
            }
        )

    net_pnl = round(sum(t["pnl"] for t in trades if t["action"] == "SELL"), 2)
    return trades, net_pnl


def run_full_backtest(settings, symbols):
    """
    Iterate over symbols, call backtest(), and aggregate summary.
    Ignores the backtest()'s net_pnl and recalculates all stats
    from individual SELL-trade P/Ls.
    """
    all_trades = []
    all_sell_pnls = []
    total_win_pnl = 0.0
    total_loss_pnl = 0.0

    summary = {
        "symbols_tested": len(symbols),
        "total_pnl": 0.0,
        "num_trades": 0,
        "wins": 0,
        "losses": 0,
        # these we'll fill in after loop:
        "win_rate_pct": 0.0,
        "avg_pnl_per_trade": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "best_trade_pnl": None,
        "worst_trade_pnl": None,
        "by_symbol": {},
    }

    for symbol in symbols:
        result = backtest(
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
            stop_loss_pct=getattr(settings, "stop_loss_pct", 0.0),
            take_profit_pct=getattr(settings, "take_profit_pct", 0.0),
            log_to_db=False,
        )

        trades_symbol = result[0] if result else []
        all_trades.extend(trades_symbol)

        # extract only SELLs
        sells = [t for t in trades_symbol if t["action"] == "SELL"]
        pnls = [t["pnl"] for t in sells]

        pnl_symbol = sum(pnls)
        count_symbol = len(pnls)
        wins_symbol = sum(1 for p in pnls if p > 0)
        losses_symbol = count_symbol - wins_symbol
        win_rate_sym = (wins_symbol / count_symbol * 100) if count_symbol else 0.0
        avg_pnl_sym = (pnl_symbol / count_symbol) if count_symbol else 0.0

        # accumulate global lists
        all_sell_pnls.extend(pnls)
        total_win_pnl += sum(p for p in pnls if p > 0)
        total_loss_pnl += sum(p for p in pnls if p <= 0)

        # update grand totals
        summary["total_pnl"] += pnl_symbol
        summary["num_trades"] += count_symbol
        summary["wins"] += wins_symbol
        summary["losses"] += losses_symbol

        # per‐symbol breakdown
        summary["by_symbol"][symbol] = {
            "pnl": pnl_symbol,
            "trades": count_symbol,
            "wins": wins_symbol,
            "losses": losses_symbol,
            "win_rate_pct": round(win_rate_sym, 2),
            "avg_pnl": round(avg_pnl_sym, 2),
            "best_trade": max(pnls) if pnls else None,
            "worst_trade": min(pnls) if pnls else None,
        }

    # now compute the overall derived stats
    if summary["num_trades"]:
        summary["win_rate_pct"] = round(
            summary["wins"] / summary["num_trades"] * 100, 2
        )
        summary["avg_pnl_per_trade"] = round(
            summary["total_pnl"] / summary["num_trades"], 2
        )
    if summary["wins"]:
        summary["avg_win"] = round(total_win_pnl / summary["wins"], 2)
    if summary["losses"]:
        summary["avg_loss"] = round(total_loss_pnl / summary["losses"], 2)
    if all_sell_pnls:
        summary["best_trade_pnl"] = max(all_sell_pnls)
        summary["worst_trade_pnl"] = min(all_sell_pnls)

    return all_trades, summary


# Alias for dashboard
backtest_scanner = run_full_backtest
