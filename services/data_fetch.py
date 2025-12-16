# services/data_fetch.py
# Small HTTP helper with timeout + safe JSON handling.

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests


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
