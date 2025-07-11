import os
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from dotenv import load_dotenv; load_dotenv(override=True)
import yfinance as yf
import pandas as pd

from services.etrade_service import fetch_etrade_quote
from services.indicators import (
    compute_sma,
    compute_rsi,
    # calculate_macd() is the real name in indicators.py
    calculate_macd    as compute_macd,
    # compute_bollinger() is the real name in indicators.py
    compute_bollinger as compute_bollinger_bands,
    compute_volume_multiplier,
    compute_vwap,
)

from services.news_service import fetch_latest_headlines

logger = logging.getLogger(__name__)


def fetch_data_with_timeout(sym, period='1d', interval='5m', timeout=10):
    def _fetch():
        try:
            return yf.download(
                sym,
                period=period,
                interval=interval,
                auto_adjust=False,
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


def _has_headlines(src):
    if hasattr(src, "empty"):
        return not src.empty
    try:
        return len(src) > 0
    except Exception:
        return False


def _match_tags(conds):
    return [tag for cond, tag in conds if cond]

from services.settings_schema import SimulationSettings

from typing import Dict, Any
from services.settings_schema import SimulationSettings
from services.indicators      import (
    compute_sma,
    compute_rsi,
    compute_macd,           # alias for calculate_macd
    compute_bollinger_bands,# alias for compute_bollinger
    compute_volume_multiplier,
    compute_vwap,
)
from services.trading_helpers import (
     buy_stock,
     set_cash,
     insert_trade,
     insert_or_update_holding,
     compute_qty,
     )
from services.etrade_service  import fetch_etrade_quote
from services.risk_management import enforce_wash_sale, enforce_settlement
import yfinance as yf
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger("market")

def analyze_symbol(symbol: str, settings: SimulationSettings) -> Dict[str, Any]:
    """
    Run all toggles and indicators for `symbol` under simulation settings,
    fetches price & quantity, applies filters, and returns an alert payload dict.
    """
    # 1) Unpack settings
    s = settings.__dict__

    # 2) Fetch intraday bars (for SMA, RSI, MACD, BB, VWAP, volume)
    df = fetch_data_with_timeout(symbol)
    if df is None or df.empty:
        logger.warning(f"[DATA] {symbol}: no intraday bars → skip")
        return {}

    # 3) Fetch daily bars (for range, gap, ATR, etc)
    df_daily = fetch_data_with_timeout(symbol, period='60d', interval='1d')
    if df_daily is None or df_daily.empty:
        logger.warning(f"[DATA] {symbol}: no daily bars → skip")
        return {}

    close_col = df['Close']
    if isinstance(close_col, pd.DataFrame):
        # multi-column case: pick the first column
        close_series = close_col.iloc[:, 0]
    else:
        close_series = close_col

    # 4) “Live” price: always use E*TRADE, but fallback to bar-close on error
    try:
        price_live = fetch_etrade_quote(symbol)
        logger.info(f"[E*TRADE] {symbol}: price = {price_live:.2f}")
    except Exception as e:
        # if E*TRADE fails, fall back
        fallback = float(close_series.iat[-1])
        logger.warning(f"[E*TRADE] {symbol}: fetch failed ({e}) — using close={fallback:.2f}")
        price_live = fallback

    logger.debug(f"[PRICE] {symbol}: price_live = {price_live:.2f}")

    # 5) Run indicators and collect tags
    tags = []

    # use our squeezed series for all further indicator calls
    close = close_series
    high  = df_daily['High'].iloc[-1]
    low   = df_daily['Low'].iloc[-1]
    prev_close = df_daily['Close'].shift(1).iloc[-1]

    # — SMA —
    if s.get("sma_on"):
        sma_val = compute_sma(close, s["sma_length"])
        if price_live > sma_val:
            tags.append(f"SMA 📈({s['sma_length']})")

    # — RSI —
    if s.get("rsi_on"):
        rsi_series = compute_rsi(close, s["rsi_len"])
        rsi_val = rsi_series.iloc[-1]
        if rsi_val > s["rsi_overbought"]:
            tags.append("RSI 📈")

    # — MACD —
    if s.get("macd_on"):
        macd_line, signal = compute_macd(
            close,
            s["macd_fast"],
            s["macd_slow"],
            s["macd_signal"],
        )
        if macd_line.iloc[-1] > signal.iloc[-1]:
            tags.append("MACD 🚀")

    # — Bollinger Bands —
    if s.get("bb_on"):
        up, mid, lowb = compute_bollinger_bands(
            close, s["bb_length"], s["bb_std"]
        )
        if price_live > up.iloc[-1]:
            tags.append("BB 📈")

    # — Volume Multiplier —
    if s.get("vol_on"):
        vol_ratio = compute_volume_multiplier(df, s["vol_multiplier"])
        if vol_ratio >= s["vol_multiplier"]:
            tags.append(f"VOL 🔊({vol_ratio:.1f}×)")

    # — VWAP Threshold —
    if s.get("vwap_on"):
        vwap_val = compute_vwap(df, s["vwap_threshold"])
        if price_live - vwap_val >= s["vwap_threshold"]:
            tags.append("VWAP+ 💰")

    # — Risk / wash‐sale / settlement (if you use them) —
    # enforce_wash_sale, enforce_settlement can be called here if desired

    # 6) Compute trade quantity under simulation
    qty = compute_qty(settings, price_live)

     # 7) Build the payload dictionary
    payload = {
        "symbol":    symbol,
        "price":     price_live,
        "qty":       qty,
        "timestamp": datetime.utcnow().isoformat(),
        # keep the raw list so we can count it
        "triggers":  tags,
    }


    logger.info(f"[SIM] ALERT {symbol}: {tags}")
    return payload

def get_symbols(simulation=False, clean_path='sp500_symbols_clean.txt'):
    if simulation:
        try:
            with open(clean_path) as f:
                return [l.strip().upper() for l in f if l.strip()]
        except FileNotFoundError:
            logger.warning(f"'{clean_path}' not found → no symbols")
            return []
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
        fallback = os.path.join(os.path.dirname(__file__), 'symbols.txt')
        return [l.strip().upper() for l in open(fallback) if l.strip()]
