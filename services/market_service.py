# File: services/market_service.py

import os
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime

import yfinance as yf
import pandas as pd

from services.etrade_service import fetch_etrade_quote
from services.alert_service import (
    get_all_indicator_settings,
    insert_alert,
    generate_sparkline
)
from services.indicators import (
    calculate_macd,
    compute_rsi,
    compute_bollinger,
    compute_sma
)
from services.news_service import fetch_latest_headlines

logger = logging.getLogger(__name__)


def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    """
    Fetch intraday data from Yahoo Finance with a timeout.
    Returns a DataFrame or None on failure.
    """
    def _fetch():
        try:
            return yf.download(sym, period=period, interval=interval, progress=False, threads=False)
        except Exception as e:
            logger.error(f"[ERROR] Yahoo download {sym} failed: {e}")
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_fetch)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            logger.error(f"[ERROR] Yahoo download {sym} timed out after {timeout}s")
            return None


def analyze_symbol(sym):
    """
    Load settings, fetch data, compute indicators, count primary triggers,
    build display triggers, and insert an alert if conditions are met.
    Returns the alert payload dict or None if skipped.
    """
    # ── A) Load settings ──
    settings       = get_all_indicator_settings()
    match_count    = settings['match_count']
    sma_length     = settings['sma_length']
    rsi_len        = settings['rsi_len']
    rsi_ob         = settings['rsi_overbought']
    rsi_os         = settings['rsi_oversold']
    macd_fast      = settings['macd_fast']
    macd_slow      = settings['macd_slow']
    macd_signal    = settings['macd_signal']
    bb_length      = settings['bb_length']
    bb_std         = settings['bb_std']
    vol_multiplier = settings['vol_multiplier']
    vwap_threshold = settings['vwap_threshold']
    news_on        = settings['news_on']

    # ── B) Fetch price data ──
    df = fetch_data_with_timeout(sym)
    if df is None or df.empty:
        logger.error(f"[SKIP] {sym}: no price data")
        return None

    # ── C) Fetch live price ──
    try:
        price_live = fetch_etrade_quote(sym)
    except Exception as e:
        logger.error(f"[SKIP] {sym}: E*TRADE error {e}")
        return None
    if not price_live:
        logger.error(f"[SKIP] {sym}: invalid live price")
        return None
    logger.info(f"{sym}: Price = ${price_live:.2f}")

    # ── D) Company name ──
    try:
        info = yf.Ticker(sym).info
        company = info.get('longName') or info.get('shortName') or sym
    except Exception:
        company = sym

    # ── E) Prepare series ──
    try:
        close_col = df['Close']
        price_series = close_col.iloc[:,0] if isinstance(close_col, pd.DataFrame) else close_col
    except Exception as e:
        logger.error(f"[SKIP] {sym}: cannot extract Close series: {e}")
        return None

    # ── F) Compute indicators ──
    sma_val = compute_sma(price_series, length=sma_length)
    rsi_val = compute_rsi(price_series, period=rsi_len).iloc[-1]
    macd_line, sig_line = calculate_macd(
        price_series, fast=macd_fast, slow=macd_slow, signal=macd_signal
    )
    bb_up, bb_mid, bb_dn = compute_bollinger(
        price_series, window=bb_length, num_std=bb_std
    )

    # Volume trigger
    try:
        vol_col = df['Volume']
        vol_series = vol_col.iloc[:,0] if isinstance(vol_col, pd.DataFrame) else vol_col
        vol_current = vol_series.iloc[-1]
        avg_vol20   = vol_series.rolling(window=20).mean().iloc[-1]
        vol_trigger = vol_current >= vol_multiplier * avg_vol20
    except Exception:
        vol_trigger = False
        vol_current = 0.0
        avg_vol20   = 0.0

    # VWAP trigger
    try:
        high = df['High']; low = df['Low'];
        high = high.iloc[:,0] if isinstance(high, pd.DataFrame) else high
        low  = low.iloc[:,0] if isinstance(low, pd.DataFrame) else low
        tp  = (high + low + price_series) / 3.0
        tpv = tp * vol_series
        vwap_series = tpv.cumsum() / vol_series.cumsum()
        latest_vwap = vwap_series.iloc[-1]
        vwap_diff   = price_live - latest_vwap
        vwap_trigger = vwap_diff >= vwap_threshold
    except Exception:
        latest_vwap = 0.0
        vwap_diff   = 0.0
        vwap_trigger = False

    # ── G) Count primary triggers ──
    primary = []
    if price_series.iloc[-1] > sma_val:
        primary.append('SMA')
    if rsi_val > rsi_ob:
        primary.append('RSI_OB')
    elif rsi_val < rsi_os:
        primary.append('RSI_OS')
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        primary.append('MACD')
    if price_series.iloc[-1] > bb_up.iloc[-1] or price_series.iloc[-1] < bb_dn.iloc[-1]:
        primary.append('BB')
    if vol_trigger:
        primary.append('VOLUME')
    if vwap_trigger:
        primary.append('VWAP')
    if news_on and fetch_latest_headlines(sym):
        primary.append('NEWS')

    logger.info(f"{sym}: primary triggers = {len(primary)}, required = {match_count}")
    if len(primary) < match_count:
        logger.info(f"[SKIP] {sym}: only {len(primary)} < {match_count}, skipping alert")
        return None
    # ── H) Build display triggers & insert alert ──
    last_price = price_series.iloc[-1]
    display_triggers = []

    # 1) Bullish-only SMA display
    if last_price > sma_val:
        display_triggers.append(f"SMA 📈 ({sma_length})")

    # 2) Bullish-only RSI display
    if rsi_val > rsi_ob:
        display_triggers.append('RSI 📈')

    # 3) Bullish-only MACD
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        display_triggers.append('MACD 🚀')

    # 4) Bullish-only Bollinger Bands
    if last_price > bb_up.iloc[-1]:
        display_triggers.append('BB 📈')

    # 5) Volume
    if vol_trigger:
        display_triggers.append(f"VOL 🔊 ({vol_current/avg_vol20:.2f}×)")

    # 6) VWAP
    if vwap_trigger:
        display_triggers.append(f"VWAP+ (${vwap_diff:.2f})")

    # Optional: News icon
    if news_on and 'NEWS' in primary:
        display_triggers.append('📰')

    # Strip any stray gold-dot
    display_triggers = [t for t in display_triggers if '🟡' not in t]

    # Pack up and insert
    alert_payload = {
        'symbol':    sym,
        'price':     price_live,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name':      company,
        'vwap':      round(latest_vwap, 2),
        'vwap_diff': round(vwap_diff, 2),
        'triggers':  ','.join(display_triggers),
        'sparkline': generate_sparkline(price_series.tolist())
    }
    insert_alert(**alert_payload)
    logger.info(f"[ALERT] {sym}: {display_triggers}")

    return alert_payload


def get_symbols(simulation=False):
    """
    Return a list of tickers (S&P 500 or fallback).
    """
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            header=0
        )
        df_sp = tables[0]
        col = 'Symbol' if 'Symbol' in df_sp.columns else df_sp.columns[0]
        return df_sp[col].astype(str).str.replace('.', '-', regex=False).str.upper().tolist()
    except Exception:
        path = os.path.join(os.path.dirname(__file__), '..', 'symbols.txt')
        if os.path.exists(path):
            return [l.strip().upper() for l in open(path) if l.strip()]
        return ['AAPL', 'MSFT', 'GOOG', 'TSLA']
