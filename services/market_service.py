import os
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from dotenv import load_dotenv; load_dotenv(override=True)
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
    def _fetch():
        try:
            return yf.download(sym, period=period, interval=interval,
                               progress=False, threads=False)
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


def _has_headlines(source):
    if hasattr(source, "empty"):
        return not source.empty
    try:
        return len(source) > 0
    except Exception:
        return False


def _match_tags(conditions):
    """Return list of tags where condition is True."""
    return [tag for cond, tag in conditions if cond]


def analyze_symbol(sym):
    # ── A) Load settings ──
    settings     = get_all_indicator_settings()
    match_count  = settings.get('match_count', 0)

    sma_on        = bool(settings.get('sma_on', 1))
    rsi_on        = bool(settings.get('rsi_on', 1))
    macd_on       = bool(settings.get('macd_on', 1))
    bb_on         = bool(settings.get('bb_on', 1))
    vol_on        = bool(settings.get('vol_on', 1))
    vwap_on       = bool(settings.get('vwap_on', 1))
    news_on       = bool(settings.get('news_on', 0))
    rsi_slope_on  = bool(settings.get('rsi_slope_on', 0))
    macd_hist_on  = bool(settings.get('macd_hist_on', 0))
    bb_breakout_on= bool(settings.get('bb_breakout_on', 0))

    sma_length    = settings['sma_length']
    rsi_len       = settings['rsi_len']
    rsi_ob        = settings['rsi_overbought']
    rsi_os        = settings['rsi_oversold']
    macd_fast     = settings['macd_fast']
    macd_slow     = settings['macd_slow']
    macd_signal   = settings['macd_signal']
    bb_length     = settings['bb_length']
    bb_std        = settings['bb_std']
    vol_multiplier= settings['vol_multiplier']
    vwap_threshold= settings['vwap_threshold']

    # ── B) Fetch price data ──
    df = fetch_data_with_timeout(sym)
    if df is None or df.empty:
        return None

       # ── C) Fetch live price ──
    try:
        price_live = fetch_etrade_quote(sym)
    except Exception:
        return None
    if not price_live:
        return None
    # ── LOGGING ──
    logger.info(f"[PRICE]  {sym}: fetched live price = {price_live}")


    # ── D) Company name ──
    try:
        info   = yf.Ticker(sym).info
        company= info.get('longName') or info.get('shortName') or sym
    except:
        company= sym

    # ── E) Prepare close series ──
    close_col    = df['Close']
    price_series = (close_col.iloc[:,0] if isinstance(close_col, pd.DataFrame)
                    else close_col)
    last_price   = price_series.iloc[-1]

    # ── F) Compute indicators ──
    sma_val       = compute_sma(price_series, length=sma_length)
    rsi_series    = compute_rsi(price_series, period=rsi_len)
    rsi_val       = rsi_series.iloc[-1]
    macd_line, sig= calculate_macd(price_series,
                                   fast=macd_fast,
                                   slow=macd_slow,
                                   signal=macd_signal)
    bb_up, _, _   = compute_bollinger(price_series,
                                      window=bb_length,
                                      num_std=bb_std)
    rsi_slope     = rsi_series.diff().iloc[-1]
    macd_hist     = (macd_line - sig).iloc[-1]
    bb_breakout   = (last_price > bb_up.iloc[-1]
                    and price_series.iloc[-2] <= bb_up.iloc[-2])

    vol_col       = df['Volume']
    vol_series    = (vol_col.iloc[:,0] if isinstance(vol_col, pd.DataFrame)
                     else vol_col)
    vol_current   = vol_series.iloc[-1]
    avg_vol20     = vol_series.rolling(20).mean().iloc[-1]
    vol_trigger   = vol_current >= vol_multiplier * avg_vol20

    tp            = (df['High'] + df['Low'] + df['Close']) / 3
    tp            = tp.iloc[:,0] if isinstance(tp, pd.DataFrame) else tp
    vwap_ser      = (tp * vol_series).cumsum() / vol_series.cumsum()
    latest_vwap   = vwap_ser.iloc[-1]
    vwap_diff     = price_live - latest_vwap
    vwap_trigger  = vwap_diff >= vwap_threshold

    toggles_enabled = sum([
        sma_on, rsi_on, macd_on, bb_on,
        vol_on, vwap_on,
        rsi_slope_on, macd_hist_on, bb_breakout_on
    ])

    # ── G) Build & check minimum non-news triggers ──
    conds_primary = [
        (sma_on     and last_price > sma_val,            'SMA'),
        (rsi_on     and rsi_val > rsi_ob,                'RSI_OB'),
        (rsi_on     and rsi_val < rsi_os,                'RSI_OS'),
        (macd_on    and macd_line.iloc[-1] > sig.iloc[-1],'MACD'),
        (bb_on      and last_price > bb_up.iloc[-1],     'BB'),
        (vol_on     and vol_trigger,                     'VOLUME'),
        (vwap_on    and vwap_trigger,                    'VWAP'),
        (rsi_slope_on and rsi_slope > 0,                 'RSI_SLOPE'),
        (macd_hist_on and macd_hist > 0,                 'MACD_HIST'),
        (bb_breakout_on and bb_breakout,                 'BB_BREAK'),
    ]
    primary = _match_tags(conds_primary)

    required = toggles_enabled if match_count <= 0 else min(match_count, toggles_enabled)
    if len(primary) < required:
        logger.debug(f"[SKIP] {sym}: matched {primary} (<{required})")
        return None

    # ── H) Fetch news ──
    headlines = []
    if news_on:
        try:
            headlines = fetch_latest_headlines(sym)
        except Exception as e:
            logger.warning(f"[NEWS] {sym}: {e}")
        if _has_headlines(headlines):
            logger.info(f"[NEWS] {sym}: got news")

    # ── J) Build display tags ──
    conds_display = [
        (sma_on     and last_price > sma_val,          f"SMA 📈 ({sma_length})"),
        (rsi_on     and rsi_val > rsi_ob,              'RSI 📈'),
        (macd_on    and macd_line.iloc[-1] > sig.iloc[-1], 'MACD 🚀'),
        (bb_on      and last_price > bb_up.iloc[-1],   'BB 📈'),
        (vol_on     and vol_trigger,                   f"VOL 🔊 ({vol_current/avg_vol20:.2f}×)"),
        (vwap_on    and vwap_trigger,                  f"VWAP+ (${vwap_diff:.2f})"),
        (news_on    and _has_headlines(headlines),     '📰'),
        (rsi_slope_on and rsi_slope > 0,               "RSI Slope ⤴"),
        (macd_hist_on and macd_hist > 0,               "MACD Hist 📊"),
        (bb_breakout_on and bb_breakout,               "BB Breakout 💥"),
    ]
    display = _match_tags(conds_display)

    # ── K) Insert & return ──
    payload = {
        'symbol':    sym,
        'price':     price_live,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name':      company,
        'vwap':      round(latest_vwap, 2),
        'vwap_diff': round(vwap_diff, 2),
        'triggers':  ','.join(display),
    }
    # ── L) Fetch intraday or fallback to daily for sparkline ──
    try:
        intraday = yf.Ticker(sym).history(
            period='1d',
            interval='1m',
            auto_adjust=False
        )
        if intraday is not None and not intraday.empty:
            close_intraday = intraday['Close']
            if isinstance(close_intraday, pd.DataFrame):
                close_intraday = close_intraday.iloc[:, 0]
            spark_data = close_intraday.tolist()
            logger.info(f"[SPARK] {sym}: using intraday data ({len(spark_data)} pts)")
        else:
            spark_data = price_series.tolist()
            logger.info(f"[SPARK] {sym}: no intraday → daily data ({len(spark_data)} pts)")
    except Exception as e:
        spark_data = price_series.tolist()
        logger.warning(f"[SPARK] {sym}: intraday fetch failed ({e}) → daily ({len(spark_data)} pts)")

    payload['sparkline'] = generate_sparkline(spark_data)

    # ── M) Insert & return ──
    insert_alert(**payload)
    logger.info(f"[ALERT] {sym}: {display}")
    return payload

# services/market_service.py

import os
import pandas as pd

def get_symbols(simulation=False,
                clean_path='sp500_symbols_clean.txt'):
    """
    - If simulation=False (your live scanner), fall back to the wiki scrape.
    - If simulation=True (your backtest), load from the cleaned file.
    """
    if simulation:
        # backtest: only tickers that passed Yahoo data check
        try:
            with open(clean_path) as f:
                return [line.strip().upper() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"[WARN] '{clean_path}' not found, returning empty list.")
            return []

    # scanner: original live scrape
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            header=0
        )
        df_sp = tables[0]
        col   = 'Symbol' if 'Symbol' in df_sp.columns else df_sp.columns[0]
        return (df_sp[col]
                .astype(str)
                .str.replace('.', '-', regex=False)
                .str.upper()
                .tolist())
    except Exception:
        # fallback to bundled symbols.txt
        path = os.path.join(os.path.dirname(__file__), 'symbols.txt')
        if os.path.exists(path):
            return [l.strip().upper() for l in open(path) if l.strip()]
        return ['AAPL', 'MSFT', 'GOOG', 'TSLA']


