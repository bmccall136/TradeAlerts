# File: services/market_service.py

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

logger = logging.getLogger(__name__)


def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    """
    Attempt to fetch intraday data (1d/5m) from Yahoo Finance with a timeout.
    Returns a Pandas DataFrame or None on failure.
    """
    def _fetch():
        try:
            return yf.download(
                sym,
                period=period,
                interval=interval,
                progress=False,
                threads=False
            )
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
    1) Read all 11‐12 indicator settings from DB:
       - match_count
       - sma_length
       - rsi_len, rsi_overbought, rsi_oversold
       - macd_fast, macd_slow, macd_signal
       - bb_length, bb_std
       - vol_multiplier
       - vwap_threshold
       - news_on
    2) Download 1d/5m bars from Yahoo
    3) Fetch current E*TRADE price
    4) Compute each indicator:
       • SMA, RSI, MACD, BB, Volume, VWAP
    5) Count how many of the SIX primary triggers are true
    """

    # ── A) Load settings from DB ──
    settings = get_all_indicator_settings()
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

    # ── B) Download price data ──
    df = fetch_data_with_timeout(sym)
    if df is None or df.empty:
        logger.error(f"[SKIP] {sym}: no intraday data")
        return None

    # ── C) Fetch last price from E*TRADE ──
    try:
        etrade_price = fetch_etrade_quote(sym)
    except Exception as e:
        logger.error(f"[SKIP] {sym}: E*TRADE error {e}")
        return None
    if not etrade_price or etrade_price == 0.0:
        logger.error(f"[SKIP] {sym}: invalid E*TRADE price")
        return None
    logger.info(f"{sym}: Price = ${etrade_price:.2f}")

    # ── D) Fetch company name ──
    try:
        info = yf.Ticker(sym).info
        company_name = info.get('longName') or info.get('shortName') or sym
    except:
        company_name = sym

    # ── E) Compute “classic” indicators ──

    price_series = None
    try:
        # Ensure price_series is a single‐column Series:
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            price_series = close.iloc[:, 0]
        else:
            price_series = close
    except Exception as e:
        logger.error(f"[ERROR] {sym}: cannot extract Close prices: {e}")
        return None

    # 1) SMA (period = sma_length)
    sma_val = compute_sma(price_series, length=sma_length)

    # 2) RSI (period = rsi_len)
    rsi_series = compute_rsi(price_series, period=rsi_len)
    rsi_val = rsi_series.iloc[-1]

    # 3) MACD (fast/slw/signal)
    macd_line, sig_line = calculate_macd(
        price_series,
        fast=macd_fast,
        slow=macd_slow,
        signal=macd_signal
    )

    # 4) Bollinger Bands (window = bb_length, num_std = bb_std)
    bb_up, bb_mid, bb_dn = compute_bollinger(
        price_series,
        window=bb_length,
        num_std=bb_std
    )

    # ── F) Compute Volume trigger ──
    try:
        vol_col = df['Volume']
        if isinstance(vol_col, pd.DataFrame):
            vol_series = vol_col.iloc[:, 0]
        else:
            vol_series = vol_col

        vol_current = vol_series.iloc[-1]
        avg_vol_20  = vol_series.rolling(window=20).mean().iloc[-1]
        vol_trigger = (vol_current >= vol_multiplier * avg_vol_20)
    except Exception as e:
        logger.error(f"[ERROR] {sym}: cannot compute Volume trigger: {e}")
        vol_trigger = False
        vol_current = 0.0
        avg_vol_20  = 0.0

    # ── G) Compute VWAP trigger ──
    latest_vwap     = 0.0
    vwap_diff_value = 0.0
    vwap_trigger    = False

    try:
        # Extract single‐column Series for High, Low, Close, Volume
        high = df['High']
        if isinstance(high, pd.DataFrame):
            high = high.iloc[:, 0]

        low = df['Low']
        if isinstance(low, pd.DataFrame):
            low = low.iloc[:, 0]

        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        vol_col = df['Volume']
        if isinstance(vol_col, pd.DataFrame):
            vol_col = vol_col.iloc[:, 0]

        # Calculate Typical Price (TP) and TP * Volume (TPV)
        tp  = (high + low + close) / 3.0
        tpv = tp * vol_col

        # Cumulative sums
        cum_tpv = tpv.cumsum()
        cum_vol = vol_col.cumsum()

        # VWAP series
        vwap_series = cum_tpv / cum_vol

        latest_vwap     = vwap_series.iloc[-1]
        vwap_diff_value = etrade_price - latest_vwap
        vwap_trigger    = (vwap_diff_value >= vwap_threshold)

    except Exception as e:
        logger.error(f"[WARN] {sym}: VWAP calculation failed: {e}")
        vwap_trigger = False
        vwap_diff_value = 0.0
        latest_vwap = 0.0

    # ── H) Now count how many primary triggers are true ──
    primary_triggers = []
    last_price = price_series.iloc[-1]

    # 1) SMA
    if last_price > sma_val:
        primary_triggers.append('SMA')

    # 2) RSI overbought/oversold
    if rsi_val > rsi_ob:
        primary_triggers.append('RSI_OB')
    elif rsi_val < rsi_os:
        primary_triggers.append('RSI_OS')

    # 3) MACD
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        primary_triggers.append('MACD')

    # 4) Bollinger Bands
    if last_price > bb_up.iloc[-1] or last_price < bb_dn.iloc[-1]:
        primary_triggers.append('BB')

    # 5) Volume
    if vol_trigger:
        primary_triggers.append('VOLUME')

    # 6) VWAP
    if vwap_trigger:
        primary_triggers.append('VWAP')

    # If fewer than match_count triggers fire, skip
    if len(primary_triggers) < match_count:
        logger.info(f"[SKIP] {sym}: {len(primary_triggers)} < {match_count} triggers")
        return None

    # ── I) Build display_triggers and insert alert ──
    display_triggers = []
    if last_price > sma_val:
        display_triggers.append('SMA 🟡')
    if rsi_val > rsi_ob:
        display_triggers.append('RSI 📈')
    elif rsi_val < rsi_os:
        display_triggers.append('RSI 📉')
    if macd_line.iloc[-1] > sig_line.iloc[-1]:
        display_triggers.append('MACD 🚀')
    if last_price > bb_up.iloc[-1] or last_price < bb_dn.iloc[-1]:
        display_triggers.append('BB 📈')
    if vol_trigger:
        display_triggers.append(f'VOL 🔊 ({vol_current/avg_vol_20:.2f}×)')
    if vwap_trigger:
        display_triggers.append(f'VWAP+ (${vwap_diff_value:.2f})')

    # Optional: News if enabled
    if news_on:
        from services.news_service import fetch_sentiment_for
        try:
            sentiment = fetch_sentiment_for(sym)
            if sentiment > 0.2 or sentiment < -0.2:
                display_triggers.append('News 📰')
        except Exception as e:
            logger.error(f"[WARN] {sym}: News fetch failed: {e}")

    # Generate sparkline
    spark_svg = generate_sparkline(price_series.tolist())
    alert_payload = {
        'symbol':    sym,
        'price':     etrade_price,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name':      company_name,
        'vwap':      round(latest_vwap, 2),
        'vwap_diff': round(vwap_diff_value, 2),
        'triggers':  ",".join(display_triggers),
        'sparkline': spark_svg
    }
    insert_alert(**alert_payload)
    logger.info(f"[ALERT] {sym}: {display_triggers}")

    return alert_payload

def get_symbols(simulation=False):
    """
    Returns a list of symbols to scan.
    By default, this will fetch the current S&P 500 tickers from Wikipedia.
    If that fails (no Internet, changed page layout, etc.), it will fall back
    to reading 'symbols.txt' (one ticker per line), or finally to a hard-coded list.
    """

    # 1) Try to scrape the S&P 500 list from Wikipedia
    try:
        # URL of the Wikipedia page that lists S&P 500 constituents
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        # pandas will parse all <table> tags and return a list of DataFrames
        tables = pd.read_html(url, header=0)
        # The first table on that page is the S&P 500 constituents table
        sp500_table = tables[0]
        # The column name is usually "Symbol" (some pages call it "Ticker symbol")
        if 'Symbol' in sp500_table.columns:
            tickers = sp500_table['Symbol'].astype(str).str.replace('.', '-', regex=False).tolist()
        elif 'Ticker symbol' in sp500_table.columns:
            tickers = sp500_table['Ticker symbol'].astype(str).str.replace('.', '-', regex=False).tolist()
        else:
            # If the column name changed, just take the first column
            tickers = sp500_table.iloc[:, 0].astype(str).tolist()

        # Make sure each ticker is uppercase and stripped
        tickers = [sym.strip().upper() for sym in tickers if sym.strip()]
        if tickers:
            return tickers

    except Exception as e:
        # If anything goes wrong (no connection, parse error, etc.), we fall through to next step
        print(f"[WARN] Could not fetch S&P 500 from Wikipedia: {e}")

    # 2) If scraping failed, look for 'symbols.txt' one per line
    fallback = ['AAPL', 'MSFT', 'GOOG', 'TSLA']  # as a last resort
    path = os.path.join(os.path.dirname(__file__), '..', 'symbols.txt')
    try:
        with open(path, 'r') as f:
            lines = [line.strip().upper() for line in f if line.strip()]
            return lines if lines else fallback
    except FileNotFoundError:
        return fallback
