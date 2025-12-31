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

def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    # Wilder's ADX
    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean().replace(0, pd.NA)

    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)

    denom = (plus_di + minus_di).replace(0, pd.NA)
    dx = (100 * (plus_di - minus_di).abs() / denom)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx.fillna(0.0)

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

# --- compat shim: live_loop expects analyze_symbol_live -----------------------
def analyze_symbol_live(symbol: str, *args, **kwargs):
    """
    Compatibility wrapper: older/newer live_loop imports analyze_symbol_live.
    Route to whichever analyzer exists in this module.
    """
    # common candidates in different versions
    if "analyze_symbol" in globals() and callable(globals().get("analyze_symbol")):
        return globals()["analyze_symbol"](symbol, *args, **kwargs)

    if "analyze" in globals() and callable(globals().get("analyze")):
        return globals()["analyze"](symbol, *args, **kwargs)

    if "scan_symbol" in globals() and callable(globals().get("scan_symbol")):
        return globals()["scan_symbol"](symbol, *args, **kwargs)

    raise ImportError(
        "market_service has no analyze_symbol/analyze/scan_symbol to alias for analyze_symbol_live"
    )

def analyze_symbol(symbol: str, settings) -> tuple[float | None, list[str], bool]:
    """
    LIVE analyzer.
    Returns: (price_live, triggers, passed)

    - price_live: ALWAYS from E*TRADE (no yfinance price fallback)
    - bars: fetched via fetch_data_with_timeout() for indicator inputs
    """
    # allow dict or object settings
    s = settings if isinstance(settings, dict) else getattr(settings, "__dict__", {})
    # --- bulletproof required list (accept legacy + current keys)
    _raw_req = (s.get("required_filters") or s.get("required") or s.get("req") or [])
    req_list = [str(x).strip().lower()
                for x in (_raw_req if isinstance(_raw_req, (list, tuple)) else [_raw_req])
                if str(x).strip()]

    log.warning("[DEBUG] settings keys=%s required=%s", sorted(list(s.keys())), req_list)


    # --- bulletproof required list (accept legacy + current keys)
    _raw_req = (s.get("required_filters") or s.get("required") or s.get("req") or [])
    req_list = [str(x).strip().lower()
                for x in (_raw_req if isinstance(_raw_req, (list, tuple)) else [_raw_req])
                if str(x).strip()]

    # 1) Intraday bars (for VWAP / volume, etc.)
    df = fetch_data_with_timeout(symbol=symbol)

    if df is None or df.empty:
        log.warning("[DATA] %s: no intraday bars -> skip", symbol)
        return (None, [], False)

    # normalize intraday columns
    df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns]

    # 2) Daily bars (for SMA/ATR/range/gap, etc.)
    df_daily = fetch_data_with_timeout(symbol, period="60d", interval="1d")
    if df_daily is None or df_daily.empty:
        log.warning("[DATA] %s: no daily bars -> skip", symbol)
        return (None, [], False)

    df_daily.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df_daily.columns]
    log.warning("[DEBUG] intraday: rows=%s cols=%s", getattr(df, "shape", None), list(getattr(df, "columns", []))[:12])
    log.warning("[DEBUG] daily:    rows=%s cols=%s", getattr(df_daily, "shape", None), list(getattr(df_daily, "columns", []))[:12])

    # show last few values so we know if series are empty/nan
    try:
        log.warning("[DEBUG] daily close tail=%s", list(df_daily["close"].tail(5).astype(float).round(4)))
    except Exception as e:
        log.warning("[DEBUG] daily close tail failed: %s", e)

    try:
        log.warning("[DEBUG] intraday close tail=%s", list(df["close"].tail(5).astype(float).round(4)))
    except Exception as e:
        log.warning("[DEBUG] intraday close tail failed: %s", e)


    # 3) Live price (E*TRADE ONLY)
    try:
        price_live = float(fetch_etrade_quote(symbol))
    except Exception as e:
        log.warning("[E*TRADE] %s: quote failed (%s) -> skip", symbol, e)
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
    sma_len = int(s.get("price_sma_len", s.get("sma_length", 20)))
    if sma_on:
        try:
            sma_val = float(compute_sma(close_d, sma_len))
            if price_live > sma_val:
                triggers.append(f"Price>SMA({sma_len})")
                triggers.append(f"price>sma{sma_len}")
                triggers.append(f"price>sma({sma_len})")

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
    if bool(s.get("macd_on", False)) or ("macd" in req_list):
        try:
            fast = int(s.get("macd_fast", 12))
            slow = int(s.get("macd_slow", 26))
            sig = int(s.get("macd_signal", 9))
            macd_line, signal = compute_macd(close_d, fast, slow, sig)
            if float(macd_line.iloc[-1]) > float(signal.iloc[-1]):
                triggers.append("MACD")
        except Exception:
            pass
    
    # ADX (optional / supports required_filters containing "adx")
    if bool(s.get("adx_on", False)) or ("adx" in req_list):
        try:
            adx_len = int(s.get("adx_len", 14))
            adx_thr = float(s.get("adx_threshold", 25))
            adx_series = compute_adx(high_d, low_d, close_d, adx_len)
            adx_val = float(adx_series.iloc[-1])
            if adx_val >= adx_thr:
                # live_loop checks tokens like startswith("adx") or contains "adx>="
                triggers.append(f"ADX>={adx_thr:g}")
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
    if bool(s.get("vol_on", False)) or ("vol" in req_list) or ("volume" in req_list):
        try:
            thresh = float(s.get("vol_multiplier", 1.5))
            vol_ratio = float(compute_volume_multiplier(df))
            if vol_ratio >= thresh:
                triggers.append("VOL")
        except Exception:
            pass

    # VWAP threshold (optional)
    if bool(s.get("vwap_on", False)) or ("vwap" in req_list):
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
    log.warning("[DEBUG] price_live=%s", price_live)
