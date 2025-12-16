# C:\TradeAlerts\services\market_service.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Iterable, List, Tuple

import pandas as pd

# HISTORICAL ONLY (bars for indicators). Live price comes from E*TRADE.
from .data_fetch import fetch_data_with_timeout
from services.etrade_service import fetch_etrade_quote

from services.indicators import (
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_volume_multiplier,
    compute_vwap,
    daily_range_pct,
    gap_up_pct,
)

log = logging.getLogger("market")


def get_symbols(path: str) -> List[str]:
    """
    Load symbols from a local file path (preferred).
    Each line: SYMBOL or SYMBOL,anything...
    Returns uppercase, dot -> dash normalized (BRK.B -> BRK-B).
    """
    if not path:
        return []

    if os.path.exists(path):
        out: List[str] = []
        with open(path, encoding="utf-8") as f:
            for ln in f:
                s = (ln.strip().split(",")[0] if ln else "").strip()
                if not s:
                    continue
                out.append(s.replace(".", "-").upper())
        return out

    # If the file is missing, fail loudly-ish but safely.
    log.warning("[SYMS] symbols file not found: %s", path)
    return []


def analyze_symbol(symbol: str, settings) -> tuple[float | None, list[str], bool]:
    """
    LIVE analyzer.
    Returns: (price_live, triggers, passed)

    - price_live: ALWAYS from E*TRADE (no yfinance price fallback)
    - bars: fetched via fetch_data_with_timeout() for indicator inputs
    """
    # allow dict or object settings
    s = settings if isinstance(settings, dict) else getattr(settings, "__dict__", {})

    # 1) Intraday bars (for VWAP / volume, etc.)
    df = fetch_data_with_timeout(symbol)
    if df is None or df.empty:
        logger.warning("[DATA] %s: no intraday bars -> skip", symbol)
        return (None, [], False)

    # normalize intraday columns
    df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns]

    # 2) Daily bars (for SMA/ATR/range/gap, etc.)
    df_daily = fetch_data_with_timeout(symbol, period="60d", interval="1d")
    if df_daily is None or df_daily.empty:
        logger.warning("[DATA] %s: no daily bars -> skip", symbol)
        return (None, [], False)

    df_daily.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df_daily.columns]

    # 3) Live price (E*TRADE ONLY)
    try:
        price_live = float(fetch_etrade_quote(symbol))
    except Exception as e:
        logger.warning("[E*TRADE] %s: quote failed (%s) -> skip", symbol, e)
        return (None, [], False)

    if price_live <= 0:
        return (None, [], False)

    triggers: list[str] = []

    # ----------------------------
    # Pull series for indicators
    # ----------------------------
    close_i = df.get("close")
    if close_i is None:
        return (None, [], False)

    # flatten multi-column close if it happens
    if hasattr(close_i, "iloc") and getattr(close_i, "ndim", 1) > 1:
        close_i = close_i.iloc[:, 0]

    close_d = df_daily.get("close")
    high_d = df_daily.get("high")
    low_d = df_daily.get("low")

    if close_d is None or high_d is None or low_d is None:
        return (None, [], False)

    # ----------------------------
    # Indicator toggles
    # ----------------------------
    # SMA
    sma_on = bool(s.get("sma_on", False) or s.get("price_sma_on", False) or s.get("require_sma20", False))
    sma_len = int(s.get("sma_length", 20))
    if sma_on:
        try:
            sma_val = float(compute_sma(close_d, sma_len))
            if price_live > sma_val:
                triggers.append(f"Price>SMA({sma_len})")
        except Exception:
            pass

    # RSI (optional)
    if bool(s.get("rsi_on", False)):
        try:
            rsi_len = int(s.get("rsi_len", s.get("rsi_length", 14)))
            rsi_over = float(s.get("rsi_overbought", 70))
            rsi_series = compute_rsi(close_d, rsi_len)
            rsi_val = float(rsi_series.iloc[-1])
            if rsi_val >= rsi_over:
                triggers.append("RSI")
        except Exception:
            pass

    # MACD
    if bool(s.get("macd_on", False)) or "macd" in [str(x).lower() for x in (s.get("req") or s.get("required") or [])]:
        try:
            fast = int(s.get("macd_fast", 12))
            slow = int(s.get("macd_slow", 26))
            sig = int(s.get("macd_signal", 9))
            macd_line, signal = compute_macd(close_d, fast, slow, sig)
            if float(macd_line.iloc[-1]) > float(signal.iloc[-1]):
                triggers.append("MACD")
        except Exception:
            pass

    # Bollinger (optional)
    if bool(s.get("bb_on", False)):
        try:
            bb_len = int(s.get("bb_length", 20))
            bb_std = float(s.get("bb_std", 2))
            up, mid, lowb = compute_bollinger_bands(close_d, bb_len, bb_std)
            if price_live > float(up.iloc[-1]):
                triggers.append("BB")
        except Exception:
            pass

    # Volume multiplier (optional)
    if bool(s.get("vol_on", False)) or "vol" in [str(x).lower() for x in (s.get("req") or s.get("required") or [])]:
        try:
            thresh = float(s.get("vol_multiplier", 1.5))
            vol_ratio = float(compute_volume_multiplier(df))
            if vol_ratio >= thresh:
                triggers.append("VOL")
        except Exception:
            pass

    # VWAP threshold (optional)
    if bool(s.get("vwap_on", False)) or "vwap" in [str(x).lower() for x in (s.get("req") or s.get("required") or [])]:
        try:
            vwap_threshold = float(s.get("vwap_threshold", 0.0))
            vwap_val = float(compute_vwap(df, vwap_threshold))
            # mark trigger if above vwap by threshold
            if (price_live - vwap_val) >= vwap_threshold:
                triggers.append("VWAP")
        except Exception:
            pass

    # ATR / range / gap are optional and do not affect req filtering unless you later require them
    if bool(s.get("atr_on", False)):
        try:
            atr_len = int(s.get("atr_len", 14))
            atr_val = float(compute_atr(df_daily, period=atr_len))
            if atr_val > 0:
                triggers.append(f"ATR{atr_len}")
        except Exception:
            pass

    if bool(s.get("range_on", False)):
        try:
            rp = float(daily_range_pct(df_daily))
            if rp > 0:
                triggers.append("RANGE")
        except Exception:
            pass

    if bool(s.get("gap_on", False)):
        try:
            gp = float(gap_up_pct(df_daily))
            if gp > 0:
                triggers.append("GAP")
        except Exception:
            pass

    # ----------------------------
    # PASS/FAIL logic
    # ----------------------------
    # Basic definition: passed if it produced any triggers.
    # live_loop applies the stricter req filters after this anyway.
    passed = len(triggers) > 0

    return (price_live, triggers, passed)
