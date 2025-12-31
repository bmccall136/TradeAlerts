# services/data_fetch.py
# Small HTTP helper with timeout + safe JSON handling.
# ALSO supports passing a SYMBOL (e.g., "AAPL") to fetch daily bars via yfinance.

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


# --- DAILY BARS (Yahoo) -------------------------------------------------------
def fetch_data(symbol: str, period: str = "1d", interval: str = "1m"):
    import pandas as pd
    import yfinance as yf

    sym = (symbol or "").strip().upper()
    if not sym:
        return pd.DataFrame()

    df = yf.download(
        tickers=sym,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,   # IMPORTANT: lock old behavior
        actions=False,
        group_by="column",
        threads=False,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # Flatten MultiIndex like ('Close','AAPL') -> 'Close'
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    # Normalize column names
    cols = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
    # cols maps normalized_name -> original_name

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    c_open = pick("open")
    c_high = pick("high")
    c_low  = pick("low")
    c_close = pick("close", "adj_close")  # use Close if present; fallback to Adj Close
    c_vol  = pick("volume")

    if not all([c_open, c_high, c_low, c_close, c_vol]):
        # If yfinance changes again, fail safe instead of returning NaNs
        return pd.DataFrame()

    out = df[[c_open, c_high, c_low, c_close, c_vol]].copy()
    out.columns = ["open", "high", "low", "close", "volume"]

    # Force numeric + drop unusable rows
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["close"])

    return out
# --- HTTP FETCH (JSON/TEXT) ---------------------------------------------------
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
    Returns parsed JSON when possible, otherwise returns raw text.
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


# --- compat shim: market_service expects this name ----------------------------
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

    Supports any of these call styles:
      - fetch_data_with_timeout("AAPL")
      - fetch_data_with_timeout(symbol="AAPL")
      - fetch_data_with_timeout(url="https://...")
      - fetch_data_with_timeout("https://...")

    Behavior:
      - If the chosen value looks like http/https -> HTTP fetch (JSON/text)
      - Otherwise -> treat as ticker symbol and return daily bars (yfinance)
    """
    # Resolve the intended input (prefer explicit kwargs)
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

    return fetch_data(chosen, period=period, interval=interval)

# --- LIVE SAFE: VWAP from E*TRADE quote (no yfinance for price) ---------------
def fetch_intraday_vwap(symbol: str, broker=None):
    """
    Return (vwap, last_price) using E*TRADE quote fields when available.

    - No Yahoo/yfinance usage for last price.
    - broker is optional; if not provided we import the E*TRADE quote helper.
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
