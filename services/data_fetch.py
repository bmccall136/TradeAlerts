# services/data_fetch.py
# LIVE-SAFE data fetch utilities
#
# ❌ Yahoo / yfinance REMOVED
# ✅ HTTP fetch preserved
# ✅ E*TRADE quote VWAP preserved
# ✅ Symbol-based bar fetch is DISABLED in LIVE (returns empty DataFrame)

from __future__ import annotations

from typing import Any, Dict, Optional
import requests
import pandas as pd


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


# ── SYMBOL BAR FETCH (DISABLED) ───────────────────────────────────────────────
def fetch_data(symbol: str, period: str = "1d", interval: str = "1m"):
    """
    Historical bar fetch for symbols is DISABLED.

    Rationale:
    - Yahoo/yfinance removed
    - E*TRADE does not provide reliable historical candles for bulk scanning
    - LIVE must fail-open instead of blocking or timing out

    Callers must tolerate empty DataFrames.
    """
    return pd.DataFrame()


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

    Behavior (LIVE-SAFE):
      - If input looks like http/https → HTTP fetch
      - Otherwise (symbol) → return EMPTY DataFrame

    This prevents any Yahoo/yfinance usage while preserving API fetches.
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

    # Symbol path intentionally returns empty DataFrame
    return pd.DataFrame()


# ── LIVE SAFE: VWAP from E*TRADE quote (NO Yahoo) ─────────────────────────────
def fetch_intraday_vwap(symbol: str, broker=None):
    """
    Return (vwap, last_price) using E*TRADE quote fields only.

    - No Yahoo/yfinance
    - Safe for LIVE usage
    """
    try:
        if broker is None:
            from services.etrade_service import fetch_etrade_quote  # type: ignore
            q = fetch_etrade_quote(symbol)
        else:
            q = broker.quote(symbol)

        def _dig(d, *keys):
            cur = d
            for k in keys:
                if cur is None:
                    return None
                if isinstance(cur, dict):
                    cur = cur.get(k)
                else:
                    return None
            return cur

        last = (
            _dig(q, "All", "lastTrade")
            or _dig(q, "All", "lastTradePrice")
            or _dig(q, "QuoteResponse", "QuoteData", "All", "lastTrade")
            or _dig(q, "QuoteResponse", "QuoteData", "All", "lastTradePrice")
        )
        vwap = (
            _dig(q, "All", "vwap")
            or _dig(q, "All", "VWAP")
            or _dig(q, "QuoteResponse", "QuoteData", "All", "vwap")
            or _dig(q, "QuoteResponse", "QuoteData", "All", "VWAP")
        )

        last_f = float(last) if last is not None else None
        vwap_f = float(vwap) if vwap is not None else None
        return vwap_f, last_f

    except Exception:
        return None, None
