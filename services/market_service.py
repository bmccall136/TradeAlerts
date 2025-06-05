# services/market_service.py

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from pathlib import Path
import sqlite3

import yfinance as yf
import pandas as pd

# Import helpers
from services.etrade_service import fetch_etrade_quote, get_etrade_price
from services.alert_service import generate_sparkline, insert_alert, get_all_indicator_settings
from services.indicators import (
    calculate_macd,
    compute_rsi,
    compute_bollinger,
    compute_sma
)

logger = logging.getLogger(__name__)


def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    """
    Attempt to fetch intraday data (1d/5m) from Yahoo Finance with a timeout.
    Returns a Pandas DataFrame or None on failure.
    """
    def _fetch():
        try:
            df_local = yf.download(
                sym,
                period=period,
                interval=interval,
                progress=False,
                threads=False
            )
            return df_local
        except Exception as e:
            logger.error(f"[ERROR] Yahoo download {sym} failed: {e}")
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_fetch)
        try:
            df = future.result(timeout=timeout)
            return df
        except FuturesTimeout:
            logger.error(f"[ERROR] Yahoo download {sym} timed out after {timeout}s")
            return None


def analyze_symbol(sym):
    """
    1) Load user‐selected indicator settings (SMA_length, RSI_length, etc.)
    2) Download intraday price data (1d/5m bars)
    3) Fetch E*TRADE last price
    4) Fetch company name via yfinance
    5) Compute indicators:
         - MACD (fast, slow, signal from settings)
         - RSI (period from settings; use overbought/oversold thresholds from settings)
         - Bollinger Bands (length & stddev from settings)
         - SMA (length from settings)
         - Volume vs. avg volume (fixed 20‐bar window)
    6) Count how many “primary” triggers (SMA, RSI, MACD, BB) are true—require ≥ num_to_match
    7) If passed, compute volume trigger, VWAP trigger, generate sparkline, insert alert
    """

    # ── A) Load user‐selected indicator settings ──
    raw_settings = get_all_indicator_settings()
    try:
        num_to_match    = int(raw_settings.get('num_to_match',    3))
        SMA_length      = int(raw_settings.get('SMA_length',      20))
        RSI_length      = int(raw_settings.get('RSI_length',      14))
        RSI_overbought  = int(raw_settings.get('RSI_overbought',  70))
        RSI_oversold    = int(raw_settings.get('RSI_oversold',    30))
        MACD_fast       = int(raw_settings.get('MACD_fast',       12))
        MACD_slow       = int(raw_settings.get('MACD_slow',       26))
        MACD_signal     = int(raw_settings.get('MACD_signal',     9))
        BB_length       = int(raw_settings.get('BB_length',       20))
        BB_stddev       = float(raw_settings.get('BB_stddev',     2.0))
        use_news        = (raw_settings.get('use_news', 'false') == 'true')
    except Exception as e:
        logger.error(f"[ERROR] Invalid indicator settings: {e}")
        # Fallback to defaults if parsing fails
        num_to_match    = 3
        SMA_length      = 20
        RSI_length      = 14
        RSI_overbought  = 70
        RSI_oversold    = 30
        MACD_fast       = 12
        MACD_slow       = 26
        MACD_signal     = 9
        BB_length       = 20
        BB_stddev       = 2.0
        use_news        = False

    # ── B) Download Yahoo Finance data (1d/5m bars) ──
    df = fetch_data_with_timeout(sym)
    if df is None or df.empty:
        logger.error(f"[SKIP] {sym}: no intraday data.")
        return None

    # ── C) Fetch latest price from E*TRADE ──
    try:
        etrade_price = fetch_etrade_quote(sym)
    except Exception as e:
        logger.error(f"[SKIP] {sym}: E*TRADE error {e}")
        return None

    if not etrade_price or etrade_price == 0.0:
        logger.error(f"[SKIP] {sym}: invalid E*TRADE price.")
        return None

    logger.info(f"{sym}: Price = ${etrade_price:.2f}")

    # ── D) Fetch company name via yfinance ──
    try:
        ticker_info = yf.Ticker(sym).info
        company_name = (
            ticker_info.get('longName')
            or ticker_info.get('shortName')
            or sym
        )
    except Exception as e:
        logger.error(f"[WARN] {sym}: no company name: {e}")
        company_name = sym

    # ── E) Compute indicators using user settings ──

    # 1) MACD (fast, slow, signal from settings)
    macd_line, sig_line = calculate_macd(
        df['Close'],
        fast=MACD_fast,
        slow=MACD_slow,
        signal=MACD_signal
    )

    # 2) RSI (period from settings)
    rsi_series = compute_rsi(df['Close'], period=RSI_length)
    rsi_val = rsi_series.iloc[-1]

    # 3) Volume (we’ll keep a 20-bar rolling avg by default)
    vol = df['Volume'].iloc[-1]
    avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]

    # 4) Bollinger Bands (length & stddev from settings)
    bb_up, bb_mid, bb_dn = compute_bollinger(
        df['Close'],
        window=BB_length,
        num_std=BB_stddev
    )

    price = df['Close'].iloc[-1]

    # 5) SMA (length from settings)
    sma_val = compute_sma(df['Close'], length=SMA_length)

    # ── F) Determine how many of the four “primary” indicators triggered ──
    # Primary indicators: SMA, RSI, MACD, BB
    primary_triggers = []

    # 1) SMA trigger: price > SMA
    if price > sma_val:
        primary_triggers.append('SMA')

    # 2) RSI trigger: overbought or oversold
    if rsi_val > RSI_overbought:
        primary_triggers.append('RSI')
    elif rsi_val < RSI_oversold:
        primary_triggers.append('RSI')

    # 3) MACD trigger: macd_line > signal_line
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        primary_triggers.append('MACD')

    # 4) BB trigger: price outside upper or lower band
    if price > bb_up.iloc[-1] or price < bb_dn.iloc[-1]:
        primary_triggers.append('BB')

    # Check if we have at least num_to_match primary triggers
    if len(primary_triggers) < num_to_match:
        logger.info(f"[SKIP] {sym}: only {len(primary_triggers)} of {num_to_match} primary indicators.")
        return None

    # ── G) Build the full “triggers” list (for storing/display) ──
    triggers = []

    # SMA
    if price > sma_val:
        triggers.append('SMA 🟡')

    # RSI
    if rsi_val > RSI_overbought:
        triggers.append('RSI 📈')
    elif rsi_val < RSI_oversold:
        triggers.append('RSI 📉')

    # MACD
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        triggers.append('MACD 🚀')

    # BB
    if price > bb_up.iloc[-1] or price < bb_dn.iloc[-1]:
        triggers.append('BB 📈')

    # Volume (this one was not “primary” in your UI, but we still display it)
    if vol > avg_vol:
        triggers.append('VOL 🔊')

    # ── H) VWAP Trigger ──
    df['TypicalPrice'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TPV'] = df['TypicalPrice'] * df['Volume']
    df['CumulativeTPV'] = df['TPV'].cumsum()
    df['CumulativeVol'] = df['Volume'].cumsum()
    df['VWAP'] = df['CumulativeTPV'] / df['CumulativeVol']

    latest_vwap = df['VWAP'].iloc[-1]
    vwap_diff_value = etrade_price - latest_vwap
    if vwap_diff_value > 0:
        triggers.append('VWAP+Diff 🚀')

    # ── I) (Optional) News trigger if use_news=True ──
    if use_news:
        from services.news_service import fetch_sentiment_for  # or whatever your news code is
        try:
            sentiment = fetch_sentiment_for(sym)
            # e.g. only add “📰” if positive or negative beyond a threshold
            if sentiment > 0.2 or sentiment < -0.2:
                triggers.append('News 📰')
        except Exception as e:
            logger.error(f"[WARN] {sym}: failed to fetch news sentiment: {e}")

    # ── J) Generate sparkline & insert the alert ──
    if len(triggers) == 0:
        # This would rarely happen since we already checked “primary” triggers,
        # but just in case all triggers were “removed” by some future condition.
        logger.info(f"[SKIP] {sym}: no triggers after final check.")
        return None

    spark_svg = generate_sparkline(df['Close'].tolist())

    alert_payload = {
        'symbol':    sym,
        'price':     etrade_price,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name':      company_name,
        'vwap':      round(latest_vwap, 2),
        'vwap_diff': round(vwap_diff_value, 2),
        'triggers':  ",".join(triggers),
        'sparkline': spark_svg
    }
    insert_alert(**alert_payload)
    logger.info(f"[ALERT] {sym}: inserted with triggers {triggers}")

    return alert_payload  # (optional, if you want to inspect it)
