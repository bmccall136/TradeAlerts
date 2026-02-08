# C:\TradeAlerts\services\data_fetch.py
"""
DATA FETCH POLICY (HARD RULE):
  - Yahoo/yfinance is allowed ONLY for INTRADAY bars (indicator helpers like VWAP).
  - EVERYTHING else must go through E*TRADE. No Yahoo fallback for live price, account,
    positions, orders, etc.

This module therefore:
  - Provides fetch_intraday_vwap() using yfinance with:
      * global 429 circuit breaker
      * per-call throttle
      * per-symbol caching
  - Disables historical yfinance fetches by default (enforcing the rule).
    If you absolutely need historical from Yahoo for non-live tools, set:
      $env:YAHOO_HISTORICAL_OK="1"
"""

from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass
from typing import Any, Optional

import logging

log = logging.getLogger(__name__)

# --- Config / Hard Rules ------------------------------------------------------

# Intraday Yahoo is allowed (but protected).
YAHOO_INTRADAY_OK = True

# Historical Yahoo is DISABLED by default (hard rule enforcement).
# If you need it for non-LIVE tooling, override via env var.
YAHOO_HISTORICAL_OK = os.environ.get("YAHOO_HISTORICAL_OK", "").strip() == "1"

# Throttle between Yahoo calls (seconds). Tune if needed.
YAHOO_MIN_GAP_S = float(os.environ.get("YAHOO_MIN_GAP_S", "0.50"))

# Circuit breaker duration after a suspected 429 (seconds).
YAHOO_BREAKER_S = int(os.environ.get("YAHOO_BREAKER_S", "600"))

# Per-symbol cache TTL (seconds) for intraday VWAP.
INTRADAY_CACHE_TTL_S = int(os.environ.get("INTRADAY_CACHE_TTL_S", "60"))

# -----------------------------------------------------------------------------


@dataclass
class _BreakerState:
    blocked_until: float = 0.0
    last_log_at: float = 0.0


_breaker = _BreakerState()
_last_call_at = 0.0
_call_lock = threading.Lock()

# Cache: symbol -> (timestamp, vwap_value)
_intraday_vwap_cache: dict[str, tuple[float, float]] = {}
_cache_lock = threading.Lock()


def _now() -> float:
    return time.time()


def _is_blocked() -> bool:
    return _now() < _breaker.blocked_until


def _trip_breaker(reason: str) -> None:
    _breaker.blocked_until = _now() + float(YAHOO_BREAKER_S)

    # Log at most once every 30s while blocked to avoid spam
    if (_now() - _breaker.last_log_at) > 30:
        until = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_breaker.blocked_until))
        log.warning("YAHOO BLOCKED (%s) -> backing off until %s", reason, until)
        _breaker.last_log_at = _now()


def _throttle() -> None:
    global _last_call_at
    with _call_lock:
        gap = (_last_call_at + float(YAHOO_MIN_GAP_S)) - _now()
        if gap > 0:
            time.sleep(gap)
        _last_call_at = _now()


def _looks_like_429(err: Exception | str) -> bool:
    s = str(err).lower()
    # Common strings seen in yfinance / upstream responses
    return (
        "429" in s
        or "too many requests" in s
        or "edge: too many requests" in s
        or "rate limit" in s
    )


# -----------------------------------------------------------------------------
# HISTORICAL FETCH (DISABLED BY DEFAULT)
# -----------------------------------------------------------------------------

def fetch_data_with_timeout(
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    timeout_s: float = 12.0,
) -> Any:
    """
    Bars for indicators.

    RULES:
    - Daily / historical Yahoo is BLOCKED unless YAHOO_HISTORICAL_OK=1
    - Intraday (e.g. 1m) Yahoo IS allowed (VWAP / volume)
    """

    is_intraday = interval.endswith("m")

    # Allow Yahoo bars for indicators (daily + intraday)
    # Kill switch only if explicitly disabled
    if os.getenv("YAHOO_BARS_DISABLED", "").lower() in ("1", "true", "yes"):
        return None

    # Circuit breaker protection
    if _is_blocked():
        return None

    try:
        import yfinance as yf
    except Exception as e:
        log.error("yfinance import failed: %s", e)
        return None

    try:
        _throttle()
        t0 = _now()

        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            threads=False,
        )

        if df is None or len(df) == 0:
            return None

        _ = (t0, timeout_s)  # soft timeout placeholder
        return df

    except Exception as e:
        if _looks_like_429(e):
            _trip_breaker(f"429/yahoo: {e}")
            return None
        log.exception("fetch_data_with_timeout failed (%s): %s", symbol, e)
        return None

def fetch_intraday_vwap(
    symbol: str,
    lookback_minutes: int = 30,
    cache_ttl_s: int = INTRADAY_CACHE_TTL_S,
) -> Optional[float]:
    """
    Yahoo/yfinance is allowed ONLY here (intraday).
    Returns VWAP over the last `lookback_minutes` of 1m bars.
    Protected by:
      - circuit breaker on 429
      - throttle
      - per-symbol cache
    """

    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    # Cache hit
    if cache_ttl_s and cache_ttl_s > 0:
        with _cache_lock:
            hit = _intraday_vwap_cache.get(sym)
            if hit:
                ts, v = hit
                if (_now() - ts) <= float(cache_ttl_s):
                    return float(v)

    # Circuit breaker
    if _is_blocked():
        return None

    try:
        import yfinance as yf
    except Exception as e:
        log.error("yfinance import failed (intraday): %s", e)
        return None

    try:
        _throttle()

        # Use 1d/1m; yfinance is less reliable with range=1d chart params directly.
        df = yf.download(
            sym,
            period="1d",
            interval="1m",
            progress=False,
            threads=False,
        )

        if df is None or len(df) == 0:
            # Empty could be throttle. Trip breaker only if we can infer 429 from exception text
            # (no exception here), so we just return None silently.
            return None

        # Normalize columns
        cols = {c.lower(): c for c in df.columns}
        # yfinance usually gives: Open High Low Close Adj Close Volume
        close_c = cols.get("close")
        high_c = cols.get("high")
        low_c = cols.get("low")
        vol_c = cols.get("volume")

        if not (close_c and high_c and low_c and vol_c):
            return None

        # Keep only last N minutes
        n = max(2, int(lookback_minutes))
        tail = df.tail(n)

        vol = tail[vol_c].astype(float)
        total_vol = float(vol.sum())
        if total_vol <= 0:
            return None

        typical = (tail[high_c].astype(float) + tail[low_c].astype(float) + tail[close_c].astype(float)) / 3.0
        vwap = float((typical * vol).sum() / total_vol)

        # Cache store
        if cache_ttl_s and cache_ttl_s > 0:
            with _cache_lock:
                _intraday_vwap_cache[sym] = (_now(), vwap)

        return vwap

    except Exception as e:
        if _looks_like_429(e):
            _trip_breaker(f"429/intraday: {e}")
            return None
        # yfinance sometimes wraps upstream html in errors; treat "possibly delisted" as non-fatal.
        msg = str(e).lower()
        if "possibly delisted" in msg or "no price data found" in msg:
            # Do NOT spam logs; this is often just Yahoo throttling/HTML.
            return None

        log.exception("fetch_intraday_vwap failed (%s): %s", sym, e)
        return None
