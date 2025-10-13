# services/scan_speedups.py
from __future__ import annotations

import logging
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple, Optional

import math
import time

log = logging.getLogger("live")

# yfinance is optional; we guard imports so the module always imports cleanly
try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None  # type: ignore


# ── small utilities ───────────────────────────────────────────────────────────

def batched(seq: Sequence[str] | Iterable[str], n: int) -> Iterator[List[str]]:
    """
    Yield lists of size ≤ n from seq/iterable.
    """
    if n <= 0:
        raise ValueError("n must be > 0")
    buf: List[str] = []
    for s in seq:
        buf.append(s)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isfinite(f):
            return f
    except Exception:
        return None
    return None


# ── logging helpers ──────────────────────────────────────────────────────────

def _pretty_signal_name(t: str) -> str:
    t = (t or "").strip()
    m = t.lower().replace(" ", "")
    if m.startswith("adx"):
        return "ADX ≥ 20"
    if "macd" in m:
        return "MACD 🚀"
    if "bb" in m and "break" in m:
        return "BB breakout"
    if "rsi" in m:
        return "RSI 📈"
    if "atr" in m:
        return "ATR % ≥ 0.5%"  # generic prettifier
    if "price>sma20" in m or "price>sma(20)" in m:
        return "Price > SMA20"
    return t

def _dedupe_preserve_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def log_candidate(sym: str, price: float, triggered: List[str], scanned_i: int, total: int) -> None:
    pretty = [_pretty_signal_name(x) for x in (triggered or [])]
    pretty = _dedupe_preserve_order(pretty)
    log.info("[LIVE] ➕ candidate %-6s px=%.2f signals=%s", sym, float(price), ", ".join(pretty))

# ── fast quotes via E*TRADE + fallback to yfinance ───────────────────────────

def _parse_etrade_quote_payload(payload: Dict) -> Dict[str, float]:
    """
    Robust parser for E*TRADE /market/quote batch JSON. Returns {symbol: last_price}.
    """
    out: Dict[str, float] = {}
    if not isinstance(payload, dict):
        return out

    qd_list = (
        payload.get("QuoteResponse", {}).get("QuoteData", [])
        if isinstance(payload.get("QuoteResponse", {}), dict)
        else []
    )
    for qd in qd_list:
        try:
            sym = (qd.get("Product") or {}).get("symbol")
            if not sym:
                continue

            # E*TRADE can put pricing in a few places; try a handful of keys
            all_block = qd.get("All", {}) or {}
            intraday = qd.get("intraday", {}) or {}

            for k in ("lastTrade", "lastPrice", "adjustedFlagLastPrice", "close"):
                v = _safe_float(all_block.get(k))
                if v is not None:
                    out[sym] = v
                    break
            else:
                # look in intraday section
                for k in ("lastTrade", "lastPrice"):
                    v = _safe_float(intraday.get(k))
                    if v is not None:
                        out[sym] = v
                        break
        except Exception:
            continue
    return out


def fetch_intraday_prices_et(broker, symbols: Sequence[str]) -> Dict[str, float]:
    """
    Use E*TRADE batch quote endpoint via the existing broker session.
    Returns {symbol: last_price}.
    """
    if not symbols:
        return {}
    out: Dict[str, float] = {}
    # E*TRADE seems fine with ~100-150 per call; go conservative.
    for chunk in batched(list(symbols), 100):
        try:
            resp = broker._et.get_quotes_batch(chunk)  # type: ignore[attr-defined]
            out.update(_parse_etrade_quote_payload(resp))
        except Exception as e:
            log.debug("batch quote failed for %s: %s", chunk[:5], e)
            # fall through — we'll let fallback (below) fill any gaps
    return out


def _yf_latest_price(sym: str) -> Optional[float]:
    if yf is None:
        return None
    try:
        # Try fast path first
        t = yf.Ticker(sym)
        p = _safe_float(getattr(t, "fast_info", {}).get("last_price", None))
        if p is not None:
            return p

        # Fallback: 1d data, last non-NaN close
        hist = t.history(period="1d", interval="1m", prepost=True, raise_errors=False)
        if hist is not None and not hist.empty:
            last = hist["Close"].dropna()
            if not last.empty:
                return _safe_float(last.iloc[-1])
    except Exception:
        return None
    return None


def fetch_intraday_prices_with_fallback(broker, symbols: Sequence[str]) -> Dict[str, float]:
    """
    First try E*TRADE batch quotes; fill in any missing symbols with yfinance.
    """
    prices = fetch_intraday_prices_et(broker, symbols)
    missing = [s for s in symbols if s not in prices]
    if not missing or yf is None:
        return prices

    for s in missing:
        p = _yf_latest_price(s)
        if p is not None:
            prices[s] = p
    return prices


# ── warm yfinance caches so analyze_symbol runs faster ───────────────────────

def preload_history_yahoo(symbols: Sequence[str], months: int = 6) -> None:
    """
    Opportunistically preload recent daily history via yfinance to warm
    local/remote caches. Best-effort: errors are swallowed.
    """
    if yf is None:
        log.debug("yfinance not available; skipping preload")
        return
    syms = list(dict.fromkeys(s for s in symbols if s))  # de-dupe/preserve order
    if not syms:
        return
    # Use small batches to avoid throttling; yfinance handles lists in download
    for chunk in batched(syms, 50):
        try:
            yf.download(
                tickers=" ".join(chunk),
                period=f"{int(months)}mo",
                interval="1d",
                auto_adjust=False,
                prepost=False,
                progress=False,
                threads=True,
            )
        except Exception:
            # It's just a warmup; ignore errors to keep startup fast.
            pass
        # brief pause to be polite
        time.sleep(0.2)
