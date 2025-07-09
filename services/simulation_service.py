import time
import pandas as pd
import logging
from pathlib import Path

from services.trading_helpers import (
    set_cash,
    get_cash,
)
from services.market_service import fetch_data_with_timeout
from services.etrade_service import fetch_etrade_quote
from requests.exceptions import HTTPError
import pandas_market_calendars as mcal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import webbrowser
from flask import url_for
# make sure Python can find dashboard.py on your PYTHONPATH
import sys, os
sys.path.append(os.getcwd())



logger     = logging.getLogger("sim")
sim_logger = logger
_sim_stop  = False


# define ET
ET = ZoneInfo("America/New_York")

nyse = mcal.get_calendar("NYSE")

def seconds_until_open():
    now = datetime.now(ET)
    schedule = nyse.schedule(start_date=now.date(), end_date=(now + timedelta(days=2)).date())
    # find the next open time after now
    for idx, row in schedule.iterrows():
        open_dt = row.market_open.tz_convert(ET)
        close_dt = row.market_close.tz_convert(ET)
        if now < open_dt:
            return (open_dt - now).total_seconds()
        elif open_dt <= now <= close_dt:
            return 0
    return 24*3600  # fallback

def run_simulation_loop(settings, symbols):
    logger.info(f"[sim] starting run with settings={settings}")
    set_cash(settings.starting_cash)
    logger.info(f"[sim] seed cash: {get_cash():.2f}")
    logger.info(f"[sim] will scan {len(symbols)} symbols")

    while not _sim_stop:
        # wait for market open...
        wait = seconds_until_open()
        if wait > 0:
            logger.info(f"Market closed — sleeping {wait/60:.1f} min")
            time.sleep(min(wait, 60))
            continue

        # ─── ENTRY PASS ───────────────────────────────────
        for sym in symbols:
            try:
                price_live = float(fetch_etrade_quote(sym))
            except HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    logger.warning(f"[sim] {sym}: 401 → launching OAuth flow")
                    webbrowser.open("http://localhost:5000/etrade/auth")
                    return
                logger.warning(f"[sim] {sym}: price fetch failed ({e})")
                continue

            # initialize filter lists
            decisions = []
            reasons   = []

            # pull bars if any indicator is on
            df = None
            if any([
                settings.sma_on,
                settings.rsi_on,
                settings.rsi_slope_on,
                settings.macd_hist_on,
                settings.bb_on,
                settings.vwap_on,
                settings.news_on,
            ]):
                df = fetch_data_with_timeout(sym, period='1d', interval='1m')
                if df is None or df.empty:
                    logger.warning(f"[sim] {sym}: no market data for indicators")
                    continue

            # ─── now individual checks ───
            if settings.sma_on:
                sma = df['Close'].rolling(settings.sma_length).mean().iloc[-1]
                ok  = price_live > sma
                decisions.append(ok)
                reasons.append(f"SMA pass? {ok}")

            # SMA
            if settings.sma_on:
                sma = df['Close'].rolling(settings.sma_length).mean().iloc[-1]
                ok  = price_live > sma
                decisions.append(ok)
                reasons.append(f"SMA({settings.sma_length}) pass? {ok}")

            # RSI oversold
            if settings.rsi_on:
                delta   = df['Close'].diff()
                up      = delta.clip(lower=0)
                down    = -delta.clip(upper=0)
                rs      = up.ewm(span=settings.rsi_len).mean() / down.ewm(span=settings.rsi_len).mean()
                rsi_ser = 100 - (100 / (1 + rs))
                latest  = rsi_ser.iloc[-1]
                ok      = latest < settings.rsi_oversold
                decisions.append(ok)
                reasons.append(f"RSI({settings.rsi_len})={latest:.1f} pass? {ok}")

            # RSI slope
            if settings.rsi_slope_on:
                delta   = df['Close'].diff()
                up      = delta.clip(lower=0)
                down    = -delta.clip(upper=0)
                rs      = up.ewm(span=settings.rsi_len).mean() / down.ewm(span=settings.rsi_len).mean()
                rsi_ser = 100 - (100 / (1 + rs))
                slope   = rsi_ser.diff().iloc[-1]
                ok      = slope > 0
                decisions.append(ok)
                reasons.append(f"RSI slope pass? {ok}")

            # MACD histogram
            if settings.macd_hist_on:
                exp1     = df['Close'].ewm(span=settings.macd_fast).mean()
                exp2     = df['Close'].ewm(span=settings.macd_slow).mean()
                macd     = exp1 - exp2
                signal   = macd.ewm(span=settings.macd_signal).mean()
                hist     = macd - signal
                raw_hist = hist.iloc[-1]

                # always coerce to float
                try:
                    latest_hist = float(raw_hist)
                except (TypeError, ValueError):
                    # fallback in case it's a zero-dim pandas object
                    latest_hist = raw_hist.item() if hasattr(raw_hist, 'item') else float(raw_hist)

                ok = latest_hist > 0
                decisions.append(ok)
                reasons.append(f"MACD hist={latest_hist:.2f} pass? {ok}")


            # Bollinger-breakout
            if settings.bb_on:
                mb    = df['Close'].rolling(settings.bb_length).mean().iloc[-1]
                std   = df['Close'].rolling(settings.bb_length).std().iloc[-1]
                raw_upper = mb + settings.bb_std * std
                # coerce to float if it's a 1-element Series
                upper = raw_upper.item() if hasattr(raw_upper, 'item') else float(raw_upper)
                ok    = price_live > upper
                decisions.append(ok)
                reasons.append(f"BB upper={upper:.2f} pass? {ok}")

            # VWAP
            if settings.vwap_on:
                vol       = df['Volume']
                tp        = (df['High'] + df['Low'] + df['Close']) / 3
                vwap_ser  = (tp * vol).cumsum() / vol.cumsum()
                raw_vwap  = vwap_ser.iloc[-1]

                # pull scalar out of possible 1-element Series
                if hasattr(raw_vwap, 'item'):
                    latest_vwap = raw_vwap.item()
                else:
                    latest_vwap = float(raw_vwap)

                ok = (price_live - latest_vwap) > settings.vwap_threshold
                decisions.append(ok)
                reasons.append(f"VWAP={latest_vwap:.2f} pass? {ok}")


            # single‐entry guard
            if settings.single_entry_only and sym in positions:
                continue

            # unwrap any pandas booleans/series
            decisions = [(d.iloc[0] if hasattr(d, 'iloc') else d) for d in decisions]
            # Log exactly which checks failed
            if decisions and not all(decisions):
                logger.debug(
                    f"{sym}: "
                    + ", ".join(reasons)
                    + f"  →  passing? {all(decisions)}"
                )

            if not decisions or not all(decisions):
                continue

            # calculate qty & buy
            qty = calculate_qty(settings, {'price': price_live})
            if qty < 1:
                continue
            try:
                buy_stock(sym, qty, price_live)
                logger.info(f"BUY  {sym} x{qty} @ {price_live:.2f}")
                positions[sym] = {
                    'entry_time': datetime.utcnow(),
                    'qty':        qty,
                    'entry_price': price_live,
                    'peak_price': price_live,
                    'price':      price_live
                }
            except ValueError as e:
                logger.warning(f"skip BUY {sym}: {e}")

        # ─── exit logic ──────────────────────────────────────
        for sym, pos in list(positions.items()):
            price_live  = float(fetch_etrade_quote(sym))
            entry_price = pos['entry_price']

            # stop‐loss
            if settings.stop_loss_pct and price_live <= entry_price * (1 - settings.stop_loss_pct):
                sell_stock(sym, pos['qty'], price_live)
                logger.info(f"STOP-LOSS SELL {sym} @ {price_live:.2f}")
                positions.pop(sym)
                continue

            # take‐profit
            if settings.take_profit_pct and price_live >= entry_price * (1 + settings.take_profit_pct):
                sell_stock(sym, pos['qty'], price_live)
                logger.info(f"TAKE-PROFIT SELL {sym} @ {price_live:.2f}")
                positions.pop(sym)
                continue


            # 3) UPDATE PEAK for trailing-stop
            if price_live > pos['peak_price']:
                pos['peak_price'] = price_live

            # 4) EXISTING TRAILING-STOP
            if getattr(settings, 'use_trailing_stop', False):
                if price_live <= pos['peak_price'] * (1 - settings.trailing_stop_pct):
                    sell_stock(sym, pos['qty'], price_live)
                    logger.info(f"TRAILING-STOP SELL {sym} x{pos['qty']} @ {price_live:.2f}")
                    positions.pop(sym)
                    continue

            # 5) TIME-BASED EXIT (as before)
            entry = pos['entry_time']
            if getattr(settings, 'sell_after_days', None) and entry:
                if (datetime.utcnow() - entry).days >= settings.sell_after_days:
                    sell_stock(sym, pos['qty'], price_live)
                    logger.info(f"TIME-STOP SELL {sym} x{pos['qty']} @ {price_live:.2f}")
                    positions.pop(sym)
                    continue


        # wait until next poll
        time.sleep(getattr(settings, 'poll_interval', 60))

def stop_simulation():
    """Signal the running simulation loop to exit on next iteration."""
    global _sim_stop
    _sim_stop = True

# ── helpers ─────────────────────────────────────────────────────

def load_symbols():
    """Load the list of symbols from your SP500 file."""
    p = Path(__file__).parent.parent / "sp500_symbols.txt"
    return [s.strip() for s in p.read_text().splitlines() if s.strip()]

def calculate_qty(settings, data):
    """
    Turn max_per_trade into whole‐share qty based on latest price.
    Expects `data['price']` to be the live price.
    """
    try:
        price   = float(data.get("price") if isinstance(data, dict) else getattr(data, "price", 0))
        max_amt = float(settings.max_per_trade)
        if price <= 0:
            return 0
        qty = int(max_amt // price)
        return qty        # no fallback to 1
    except Exception as e:
        logging.error(f"[sim] calculate_qty error: {e}")
        return 0         # safest: treat errors as zero

def evaluate_exit(pos, settings):
    price = pos['price']
    entry = pos['entry_price']
    # 1) stop‐loss
    if settings.stop_loss_pct and price <= entry * (1 - settings.stop_loss_pct/100):
        return True
    # 2) take‐profit
    if settings.take_profit_pct and price >= entry * (1 + settings.take_profit_pct/100):
        return True
    # 3) trailing‐stop
    if settings.use_trailing_stop:
        peak = pos['peak_price']
        if price <= peak * (1 - settings.trailing_stop_pct):
            return True
    # 4) time‐based
    return False


