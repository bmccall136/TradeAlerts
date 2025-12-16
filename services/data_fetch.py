# services/data_fetch.py
# Small HTTP helper with timeout + safe JSON handling.

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests

# --- compat shim: market_service expects this name ----------------------------
def fetch_data_with_timeout(*args, **kwargs):
    """
    Compatibility wrapper for older/newer code paths.
    If a more specific fetch function exists in this module, use it.
    Otherwise fall back to a basic requests call with a timeout.
    """
    # Prefer an existing function if your module already has one
    if "fetch_data" in globals() and callable(globals().get("fetch_data")):
        return globals()["fetch_data"](*args, **kwargs)

    if "fetch_json" in globals() and callable(globals().get("fetch_json")):
        return globals()["fetch_json"](*args, **kwargs)

    # Last-resort fallback (keeps the app from crashing even if older code)
    import requests

    if not args:
        raise TypeError("fetch_data_with_timeout() missing required positional arg: url")

    url = args[0]
    timeout = kwargs.pop("timeout", 10)
    method = kwargs.pop("method", "GET").upper()

    headers = kwargs.pop("headers", None)
    params = kwargs.pop("params", None)
    data = kwargs.pop("data", None)
    json_body = kwargs.pop("json", None)

    if method == "POST":
        r = requests.post(url, headers=headers, params=params, data=data, json=json_body, timeout=timeout)
    else:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)

    r.raise_for_status()

    # If it looks like JSON, return JSON; else return text
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "json" in ctype:
        return r.json()
    return r.text

# --- LIVE SAFE: VWAP from E*TRADE quote (no yfinance) --------------------------

def fetch_intraday_vwap(symbol: str, broker=None):
    """
    Return (vwap, last_price) using E*TRADE quote fields when available.

    - No Yahoo/yfinance usage.
    - broker is optional; if not provided we import the E*TRADE quote helper.
    """
    try:
        if broker is None:
            # adjust this import if your quote helper lives elsewhere
            from services.etrade_service import fetch_etrade_quote  # type: ignore
            q = fetch_etrade_quote(symbol)
        else:
            q = broker.quote(symbol)

        # Be defensive about quote shapes.
        # Common paths we’ve seen in your project:
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

        # Try several likely VWAP/last paths:
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

        # Normalize to floats if possible
        last_f = float(last) if last is not None else None
        vwap_f = float(vwap) if vwap is not None else None
        return vwap_f, last_f

    except Exception:
        return None, None

# --- compat shim: used by market_service --------------------------------------
def fetch_data_with_timeout(
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

    # Try JSON first; fall back to text
    try:
        return r.json()
    except Exception:
        return r.text
