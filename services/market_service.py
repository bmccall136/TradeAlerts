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
    Load settings (including on/off toggles), fetch data, compute indicators,
    require all enabled triggers (excluding news), fetch news if enabled,
    build display list, insert alert if passed.
    Returns alert_payload or None.
    """
    # ── A) Load settings ──
    settings       = get_all_indicator_settings()
    sma_on         = bool(settings.get('sma_on', 1))
    rsi_on         = bool(settings.get('rsi_on', 1))
    macd_on        = bool(settings.get('macd_on', 1))
    bb_on          = bool(settings.get('bb_on', 1))
    vol_on         = bool(settings.get('vol_on', 1))
    vwap_on        = bool(settings.get('vwap_on', 1))
    news_on        = bool(settings.get('news_on', 0))

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

    # ── E) Prepare close series ──
    close_col    = df['Close']
    price_series = close_col.iloc[:,0] if isinstance(close_col, pd.DataFrame) else close_col
    last_price   = price_series.iloc[-1]

    # ── F) Compute indicators ──
    sma_val        = compute_sma(price_series, length=sma_length)
    rsi_val        = compute_rsi(price_series, period=rsi_len).iloc[-1]
    macd_line, sig = calculate_macd(price_series, fast=macd_fast, slow=macd_slow, signal=macd_signal)
    bb_up, *_      = compute_bollinger(price_series, window=bb_length, num_std=bb_std)

    # Volume trigger
    vol_col    = df['Volume']
    vol_series = vol_col.iloc[:,0] if isinstance(vol_col, pd.DataFrame) else vol_col
    vol_current = vol_series.iloc[-1]
    avg_vol20   = vol_series.rolling(20).mean().iloc[-1]
    vol_trigger = (vol_current >= vol_multiplier * avg_vol20)

    # VWAP trigger
    tp           = (df['High'] + df['Low'] + df['Close']) / 3
    tp           = tp.iloc[:,0] if isinstance(tp, pd.DataFrame) else tp
    tpv          = tp * vol_series
    vwap_ser     = tpv.cumsum() / vol_series.cumsum()
    latest_vwap  = vwap_ser.iloc[-1]
    vwap_diff    = price_live - latest_vwap
    vwap_trigger = (vwap_diff >= vwap_threshold)

    # ── G) Build primary for indicators (exclude news) ──
    primary = []
    if sma_on and last_price > sma_val:
        primary.append('SMA')
    if rsi_on and rsi_val > rsi_ob:
        primary.append('RSI_OB')
    elif rsi_on and rsi_val < rsi_os:
        primary.append('RSI_OS')
    if macd_on and macd_line.iloc[-1] > sig.iloc[-1]:
        primary.append('MACD')
    if bb_on and last_price > bb_up.iloc[-1]:
        primary.append('BB')
    if vol_on and vol_trigger:
        primary.append('VOLUME')
    if vwap_on and vwap_trigger:
        primary.append('VWAP')

    # ── H) Require all enabled triggers (excluding news) ──
    required = sum([sma_on, rsi_on, macd_on, bb_on, vol_on, vwap_on])
    if len(primary) < required:
        logger.info(f"[SKIP] {sym}: only {len(primary)}/{required} enabled triggers")
        return None

    # ── I) Fetch news only if enabled ──
    headlines = []
    if news_on:
        try:
            headlines = fetch_latest_headlines(sym)
        except Exception as e:
            logger.warning(f"[NEWS] {sym}: {e}")
        if headlines:
            primary.append('NEWS')

    # ── J) Build display triggers ──
    display = []
    if sma_on and last_price > sma_val:
        display.append(f"SMA 📈 ({sma_length})")
    if rsi_on and rsi_val > rsi_ob:
        display.append('RSI 📈')
    if macd_on and macd_line.iloc[-1] > sig.iloc[-1]:
        display.append('MACD 🚀')
    if bb_on and last_price > bb_up.iloc[-1]:
        display.append('BB 📈')
    if vol_on and vol_trigger:
        display.append(f"VOL 🔊 ({vol_current/avg_vol20:.2f}×)")
    if vwap_on and vwap_trigger:
        display.append(f"VWAP+ (${vwap_diff:.2f})")
    if news_on and headlines:
        display.append('📰')

    # ── K) Insert and return ──
    payload = {
        'symbol':    sym,
        'price':     price_live,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name':      company,
        'vwap':      round(latest_vwap, 2),
        'vwap_diff': round(vwap_diff, 2),
        'triggers':  ','.join(display),
        'sparkline': generate_sparkline(price_series.tolist())
    }
    insert_alert(**payload)
    logger.info(f"[ALERT] {sym}: {display}")
    return payload


def get_symbols(simulation=False):
    """
    Return a list of tickers (S&P 500 or fallback).
    """
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            header=0
        )
        df_sp = tables[0]
        col   = 'Symbol' if 'Symbol' in df_sp.columns else df_sp.columns[0]
        return df_sp[col].astype(str).str.replace('.', '-', regex=False).str.upper().tolist()
    except Exception:
        path = os.path.join(__file__, '..', 'symbols.txt')
        if os.path.exists(path):
            return [l.strip().upper() for l in open(path) if l.strip()]
        return ['AAPL', 'MSFT', 'GOOG', 'TSLA']
