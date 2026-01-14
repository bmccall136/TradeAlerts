# C:\TradeAlerts\services\data_fetch.py
# Historical candle fetch for indicators.
# LIVE last price MUST come from E*TRADE (handled elsewhere).
#
# This module supports:
#   - fetch_data(symbol, period, interval) via yfinance (historical only)
#   - fetch_json(url, ...) via requests for HTTP endpoints
#   - fetch_data_with_timeout(...) compatibility shim used by market_service
#
# Guards:
#   - If LIVE_SAFE_MODE=1 or MM_DISABLE_YF=1, symbol-based candles return empty DF
#     (prevents any external market-data calls in emergencies)

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

import pandas as pd
import requests

log = logging.getLogger("data_fetch")


def _looks_like_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _safe_empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _yf_enabled() -> bool:
    # Hard kill switch if you need to guarantee no market-data calls
    if os.getenv("LIVE_SAFE_MODE", "").strip().lower() in ("1", "true", "yes"):
        return False
    if os.getenv("MM_DISABLE_YF", "").strip().lower() in ("1", "true", "yes"):
        return False
    return True


# ── SYMBOL BAR FETCH (historical candles for indicators) ──────────────────────
def fetch_data(symbol: str, period: str = "1d", interval: str = "1m") -> pd.DataFrame:
    """
    Fetch historical candles for a symbol (for indicators only).

    Returns a pandas DataFrame (may be empty if unavailable or disabled).
    Columns typically: Open, High, Low, Close, Adj Close, Volume
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return _safe_empty_df()

    if not _yf_enabled():
        return _safe_empty_df()

    try:
        import yfinance as yf  # type: ignore
    except Exception as e:
        log.warning("yfinance not available (%s) -> returning empty DF", e)
        return _safe_empty_df()

    try:
        # Use yf.download (works for tickers + ETFs). progress False to keep logs clean.
        df = yf.download(
            tickers=sym,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if df is None or df.empty:
            return _safe_empty_df()

        # yfinance can return multi-index columns in some cases; normalize to simple columns.
        if hasattr(df.columns, "nlevels") and getattr(df.columns, "nlevels", 1) > 1:
            # Keep first level name like ('Close','SPY') -> 'Close'
            df.columns = [c[0] if isinstance(c, tuple) else str(c) for c in df.columns]

        # Ensure standard column names exist
        # (market_service lowercases later; we leave them as-is here)
        return df

    except Exception as e:
        log.warning("fetch_data(%s, period=%s, interval=%s) failed: %s", sym, period, interval, e)
        return _safe_empty_df()


# ── HTTP FETCH (JSON/TEXT) ────────────────────────────────────────────────────
def fetch_json(
    url: str,
    *,
    timeout: float = 10.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
) -> Any:
    """
    Simple HTTP fetch with timeout + safe JSON handling.
    Returns parsed JSON when possible, otherwise raw text.
    """
    m = (method or "GET").upper()
    if m == "POST":
        r = requests.post(url, headers=headers, params=params, timeout=timeout)
    else:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)

    r.raise_for_status()

    try:
        return r.json()
    except Exception:
        return r.text


# ── COMPAT SHIM (market_service dependency) ───────────────────────────────────
def fetch_data_with_timeout(
    target: Optional[str] = None,
    *,
    symbol: Optional[str] = None,
    url: Optional[str] = None,
    timeout: float = 10.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    period: str = "6mo",
    interval: str = "1d",
) -> Any:
    """
    Backward-compatible entry point.

    Behavior:
      - If input looks like http/https → HTTP fetch (fetch_json)
      - Otherwise → treat as symbol and return OHLCV DataFrame via fetch_data()

    Notes:
      - LIVE price is NOT fetched here.
      - Bars are historical for indicators only.
    """
    chosen = (symbol or url or target or "").strip()
    if not chosen:
        raise TypeError("fetch_data_with_timeout() requires a symbol or url/target")

    if _looks_like_url(chosen):
        return fetch_json(
            chosen,
            timeout=timeout,
            headers=headers,
            params=params,
            method=method,
        )

    # Symbol path
    return fetch_data(chosen, period=period, interval=interval)
