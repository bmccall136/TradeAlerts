#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import logging.handlers  # keep this here too
import json
import time
import math
import sys
import random
import logging.handlers
from pathlib import Path
from datetime import datetime, timezone, timedelta
from env_alias_shim import ensure_env_aliases
ensure_env_aliases()
# Timeouts: (connect, read) in seconds
DEFAULT_TIMEOUT = (3.05, 10.0)

# ---------------------------------------
# Logging
# ---------------------------------------
LOG = logging.getLogger("sell-guard")
if not LOG.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    LOG.addHandler(h)
LOG.setLevel(logging.INFO)

log_dir = Path(r"C:\TradeAlerts\logs")
log_dir.mkdir(parents=True, exist_ok=True)
if not any(isinstance(h, logging.FileHandler) for h in LOG.handlers):
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "sell_guard.log",
        maxBytes=10_000_000,
        backupCount=7,
        encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    LOG.addHandler(fh)

import logging, sys
# Optional aggregator helper; guard already uses E*TRADE quotes.
try:
    import requests
    def http_get(url, **kwargs):  # only used if aggregator path is hit
        return requests.get(url, timeout=kwargs.pop("timeout", 10), **kwargs)
except Exception:
    # If requests isn't available, just never use the aggregator.
    def http_get(*a, **k):
        raise NameError("http_get not available")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s sell-guard: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,   # <- wipes any previously attached handlers
)
LOG = logging.getLogger("sell-guard")
LOG.propagate = False

# (Optional for back-compat if older code still uses `log`)
log = LOG

# ---- WRITE-ONLY CIRCUIT + SELL QUEUE ---------------------------------------
from datetime import datetime, timedelta
from typing import Callable, Optional, Any, List

class CircuitOpen(Exception): pass

class _WriteCircuit:
    def __init__(self, base=90, cap=600):
        self.base = base
        self.cap = cap
        self.fail_count = 0
        self.open_until: Optional[datetime] = None
        self.last_reason = ""

    def seconds_left(self) -> int:
        if not self.open_until: return 0
        return max(0, int((self.open_until - datetime.utcnow()).total_seconds()))

    def is_open(self) -> bool:
        return self.seconds_left() > 0

    def open(self, reason: str):
        self.fail_count += 1
        dur = min(self.cap, int(self.base * (1.6 ** (self.fail_count - 1))))
        dur = max(dur, 60)
        self.open_until = datetime.utcnow() + timedelta(seconds=dur)
        self.last_reason = reason
        logging.warning("E*TRADE circuit OPEN for %ss due to %s", dur, reason)

    def close(self):
        if self.is_open():
            logging.info("E*TRADE circuit CLOSED")
        self.fail_count = 0
        self.open_until = None
        self.last_reason = ""

    def half_open_ok(self) -> bool:
        return self.is_open() and self.seconds_left() <= 10

WRITE_CB = _WriteCircuit()

def _is_server_side(e: Exception) -> tuple[bool, str]:
    status = getattr(getattr(e, "response", None), "status_code", None)
    body = getattr(getattr(e, "response", None), "text", "") or ""
    code = ""
    try:
        if body.strip().startswith("{"):
            code = str(json.loads(body).get("code", ""))
        elif "code" in body:
            import re
            m = re.search(r"code[\"=\s:]+(\d+)", body)
            code = m.group(1) if m else ""
    except Exception:
        pass
    if status and int(status) >= 500:
        return True, f"{status}/code{code or '?'}"
    if code == "100":
        return True, f"{status or 'NA'}/code100"
    return False, f"{status or 'NA'}/code{code or '?'}"

def write_call(fn: Callable[[], Any]) -> Any:
    if WRITE_CB.is_open():
        if WRITE_CB.half_open_ok():
            logging.info("E*TRADE circuit HALF-OPEN: probing with one write call…")
        else:
            raise CircuitOpen(f"circuit open, {WRITE_CB.seconds_left()}s left")
    try:
        result = fn()
        WRITE_CB.close()
        return result
    except Exception as e:
        server_side, reason = _is_server_side(e)
        if server_side:
            WRITE_CB.open(reason or "server error")
        raise

class PendingSell:
    __slots__ = ("symbol","qty","side","limit_px","creator","created_at")
    def __init__(self, symbol:str, qty:int, side:str, limit_px:Optional[float], creator:str):
        from datetime import datetime
        self.symbol = symbol; self.qty = qty; self.side = side
        self.limit_px = limit_px; self.creator = creator
        self.created_at = datetime.utcnow()

PENDING_SELLS: List[PendingSell] = []

def enqueue_sell(symbol:str, qty:int, side:str, limit_px:Optional[float], why:str):
    PENDING_SELLS.append(PendingSell(symbol, qty, side, limit_px, creator=why))
    LOG.error("%s SELL queued (%s) – will retry when circuit closes", symbol, why)

# ---------------------------------------
# Credentials env alias shim (use your existing names)
# ---------------------------------------
def _strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
        return v[1:-1]
    return v

def _ensure_env_aliases():
    alias_map = {
        # target                     # fallbacks (in order)
        "ETRADE_CONSUMER_KEY":   ["ETRADE_API_KEY", "CONSUMER_KEY"],
        "ETRADE_CONSUMER_SECRET":["ETRADE_API_SECRET", "CONSUMER_SECRET"],
        "ETRADE_OAUTH_TOKEN":    ["OAUTH_TOKEN"],
        "ETRADE_OAUTH_SECRET":   ["OAUTH_TOKEN_SECRET"],
        # Optional: if you’ve set an ACCOUNT_ID_KEY yourself
        "ETRADE_ACCOUNT_ID_KEY": ["ACCOUNT_ID_KEY"],
    }
    set_any = False
    for target, sources in alias_map.items():
        if not os.environ.get(target):
            for s in sources:
                val = os.environ.get(s)
                if val:
                    os.environ[target] = _strip_quotes(val)
                    set_any = True
                    break
    if set_any:
        logging.getLogger("sell-guard").info("Applied env alias shim for trading credentials")

# Load .env first so aliases have something to map from
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Map your existing env names (CONSUMER_KEY / ETRADE_API_KEY, etc.) to what the code expects
_ensure_env_aliases()

# ---------------------------------------
# E*TRADE service wrapper
# ---------------------------------------
try:
    from services import etrade_service as et  # preferred (package layout)
except Exception:
    import etrade_service as et  # fallback to local module


# ---------------------------------------
# Config
# ---------------------------------------

_DEFAULTS = {
    "mode": "live",             # "live" | "shadow"
    "target_bps": 1_000_000,    # 10000.00% → disables TP by default; set lower to enable
    "stop_bps": 100,            # -1.00%
    "max_hold_mins": 60,
    "throttle_ms": 3000,
    "limit_from": "last",       # "bid" | "last" | "mid"
    "limit_offset_bps": 0,
    "blocklist": [],
    # fallback to MARKET when API is flaky for risk exits only
    # optional add-on: place a protective stop once hold minutes exceed this
    "sell_protect_after_mins": None,  # e.g., 60. Set to None to disable.
    "circuit_open_seconds": 180,
    "max_place_attempts": 1,
    "min_stop_gap_cents": 2,
    "normalize_tick": 0.01,
    "market_fallback_for": ["SELL_STOP", "TIMEOUT"]
}
import time
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = timezone.utc  # fallback

# --- Heartbeat config/state ---
HEARTBEAT_SECS = 30  # how often to log a 'loop alive' heartbeat
_last_beat_monotonic: float | None = None

# ——— at top ———
import requests
from requests.adapters import HTTPAdapter, Retry
def fresh_client_id(prefix: str, symbol: str) -> str:
    import time
    return f"{prefix}-{symbol.lower()}-{int(time.time()*1000)}"

def preview_then_place(symbol: str, qty: int, price: float | None, price_type: str):
    aid = account_id_key()
    coid = fresh_client_id("sg", symbol)
    prev = preview_equity_order(
        aid, symbol, qty, price,
        action="SELL",
        price_type=price_type,
        order_term="GOOD_FOR_DAY",
        market_session="REGULAR",
        client_order_id=coid,
    )
    # handle preview errors here (1037, 1011, etc.)
    return place_equity_order(prev, qty)

# KEEP THIS version (already in your file, later down)
def drain_pending_sells(place_fn):
    if not PENDING_SELLS:
        return
    keep = []
    for ps in PENDING_SELLS:
        try:
            write_call(lambda: place_fn(ps.symbol, ps.qty, ps.side, ps.limit_px))
            LOG.info("%s SELL placed from queue", ps.symbol)          # <-- LOG.*
        except CircuitOpen:
            time.sleep(0.4 + random.random()*0.4)
            keep.append(ps)
        except Exception as e:
            s = str(e).lower()
            if ("'code': 100" in s) or ('"code": 100' in s) or ("service is not currently available" in s):
                LOG.warning("%s queued SELL: venue unavailable (code100). Keeping in queue.", ps.symbol)  # <-- LOG.*
                keep.append(ps)
            else:
                LOG.error("%s queued SELL failed permanently: %r", ps.symbol, e)
    PENDING_SELLS.clear()
    PENDING_SELLS.extend(keep)
def heartbeat(now: datetime | None = None, account_id: str | None = None, logger=None):
    """
    Emits a 'loop alive' message at most once every HEARTBEAT_SECS.
    Uses time.monotonic() for robustness against wall-clock jumps.
    You can optionally pass 'account_id' for richer logs.
    """
    global _last_beat_monotonic
    t = time.monotonic()

    # first beat ever
    if _last_beat_monotonic is None:
        _last_beat_monotonic = t
        if logger:
            logger.info("⏱ heartbeat: loop alive (account=%s)", account_id or "?")
        else:
            print(f"⏱ heartbeat: loop alive (account={account_id or '?'})")
        return

    if (t - _last_beat_monotonic) >= HEARTBEAT_SECS:
        _last_beat_monotonic = t
        if logger:
            logger.info("⏱ heartbeat: loop alive (account=%s)", account_id or "?")
        else:
            print(f"⏱ heartbeat: loop alive (account={account_id or '?'})")
def _mk_session():
    s = requests.Session()
    # robust retries for transient 5xx
    retries = Retry(
        total=3, backoff_factor=0.6,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PUT")
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s

# create once and reuse
_SESSION = _mk_session()

def _get(url, params=None, headers=None, timeout=DEFAULT_TIMEOUT):
    resp = _SESSION.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp

def _post(url, data=None, json=None, headers=None, timeout=DEFAULT_TIMEOUT):
    resp = _SESSION.post(url, data=data, json=json, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp
def _load_cfg(base_dir=r"C:\TradeAlerts"):
    candidates = ["sell_guard_settings.json", "sell_guard.settings.json", "live_settings.json"]
    for name in candidates:
        p = os.path.join(base_dir, name)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                if isinstance(data, dict):
                    data = data.get("sell_guard", data.get("scalp", data))
                return data, p
    return {}, None

# Load config once at import
_CFG, _CFG_PATH = _load_cfg(r"C:\TradeAlerts")
LOG.info("config source: %s", _CFG_PATH or "<defaults>")
# After: _CFG, _CFG_PATH = _load_cfg(...)
WRITE_CB.base = int(_CFG.get("circuit_open_seconds", 90))

# ---------------------------------------
# Helpers
# ---------------------------------------
# --- helper near your other error helpers ---
TRANSIENT_HTTP = {500, 502, 503, 504}
TRANSIENT_ETRADE_CODES = {100}  # service not available
def is_code100(err: Exception | str) -> bool:
    s = str(err).lower()
    return ('"code": 100' in s) or ("'code': 100" in s) or ("service is not currently available" in s)
_last_code100_notice = 0
def maybe_banner_code100():
    global _last_code100_notice
    now = time.time()
    if now - _last_code100_notice > 60:
        LOG.warning("Broker venue unavailable (code100). Orders will be queued until circuit closes.")
        _last_code100_notice = now

def _is_transient(err):
    try:
        return (getattr(err, "http_status", None) in TRANSIENT_HTTP) or (getattr(err, "code", None) in TRANSIENT_ETRADE_CODES)
    except Exception:
        return False

def _session_label():
    # simple label: REG vs EXT depending on wall clock (does not query market-hours API)
    now_et = datetime.now().astimezone()
    hhmm = now_et.hour * 100 + now_et.minute
    return "REG" if 930 <= hhmm <= 1600 else "EXT"

def _bps_to_mult(bps):
    return 1.0 + (bps / 10_000.0)

def _dig_bid_last(node):
    def visit(n):
        if isinstance(n, dict):
            b = n.get("bid")
            l = n.get("lastPrice") or n.get("lastTrade") or n.get("last")
            if b is not None or l is not None:
                return b, l
            for v in n.values():
                r = visit(v)
                if r: return r
        elif isinstance(n, (list, tuple)):
            for v in n:
                r = visit(v)
                if r: return r
        return None
    return visit(node) or (None, None)

def _current_bid_last(sym):
    try:
        q = et.get_quote(sym, detailFlag="ALL")
        return _dig_bid_last(q)
    except Exception:
        return (None, None)

def _sell_limit_from_cfg(last, bid, ask, limit_from="last", offset_bps=0):
    if last is None and limit_from == "last":
        return None
    if limit_from == "bid":
        base = bid
    elif limit_from == "mid":
        if bid is None or ask is None:
            return None
        base = (bid + ask) / 2.0
    else:
        base = last
    if base is None:
        return None
    return float(round(base * _bps_to_mult(offset_bps), 2))

def _extract_order_id(resp):
    try:
        # Typical E*TRADE shape: {'PlaceOrderResponse': {'Order': {'orderId': '...'}}}
        for k in ("PlaceOrderResponse", "PreviewOrderResponse", "OrderResponse", "Order"):
            if isinstance(resp, dict) and k in resp:
                resp = resp[k]
        if isinstance(resp, dict):
            oid = resp.get("orderId") or resp.get("orderNumber") or resp.get("orderIdString")
            if oid:
                return str(oid)
    except Exception:
        pass
    return "?"



# Small utils
from datetime import datetime, timedelta, timezone

_ET = timezone(timedelta(hours=-5))  # Eastern Time

def _today_et():
    return datetime.now(_ET).date()

def _prev_business_days(n, end=None):
    d = end or _today_et()
    out = []
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return list(reversed(out))

def pdt_window_dates():
    # rolling 5 BUSINESS days (include today if weekday)
    today = _today_et()
    ds = [today] if today.weekday() < 5 else []
    ds = _prev_business_days(5 - len(ds), end=today) + ds
    return set(ds)

def recompute_pdt_counts(executed_orders_payload: dict) -> dict:
    """Return {YYYY-MM-DD: daytrade_count} ONLY for the current PDT window."""
    win = pdt_window_dates()
    orders = (executed_orders_payload.get("OrdersResponse") or {}).get("Order") or []
    by_date = {}
    for o in orders:
        for d in (o.get("OrderDetail") or []):
            ts = (d.get("executedTime") or d.get("placedTime") or 0) / 1000.0
            dt = datetime.fromtimestamp(ts, tz=_ET).date()
            if dt not in win:
                continue
            for ins in (d.get("Instrument") or []):
                sym = (ins.get("Product") or {}).get("symbol") or ""
                act = (ins.get("orderAction") or "").upper()
                by_date.setdefault(dt, {}).setdefault(sym, set()).add(act)
    counts = {}
    for dt, sym_actions in by_date.items():
        counts[dt.isoformat()] = sum(1 for acts in sym_actions.values()
                                     if "BUY" in acts and "SELL" in acts)
    return counts

def _round_down_to_tick(px: float, tick: float = 0.01) -> float:
    return math.floor((px + 1e-9) / tick) * tick

def _is_2084(err: Exception) -> bool:
    # Robustly sniff "stop must be ≥ $0.01 below bid" validation errors
    msg = str(err)
    return ("'code': 2084" in msg) or ('"code": 2084' in msg)

def _sleep_backoff(try_idx: int) -> float:
    # 2.0s * 1.6^(n-1) with ~±15% jitter
    base = 2.0 * (1.6 ** (try_idx - 1))
    jitter = base * random.uniform(-0.15, 0.15)
    delay = max(0.5, base + jitter)
    time.sleep(delay)
    return delay


def preview_then_place_market_sell(aid, symbol, qty: int):
    """
    Preview + place a plain MARKET sell.
    """
    symbol_api = _api_symbol(symbol)
    prv = et.preview_equity_order(
        aid, symbol_api, int(qty), None,
        price_type="MARKET", action="SELL"
    )
    return et.place_equity_order(prv, qty=int(qty))

def _strict_stop_for_sell(entry: float, bid: float | None, last: float | None,
                          stop_bps: int, cushion: float = 0.02) -> tuple[float | None, float | None]:
    """
    Return (stop_price, base_price).
    base_price = entry * (1 - stop_bps/10000). We then choose the min of [base, bid, last]
    and push the stop at least `cushion` below it, rounded to cents. Ensures >= $0.02 below bid/last.
    """
    if entry is None or stop_bps is None:
        return None, None
    base = float(entry) * (1.0 - float(stop_bps) / 10_000.0)

    refs = [x for x in (bid, last, base) if x is not None]
    if not refs:
        return None, None

    anchor = min(refs)
    # push below anchor; always ensure ≥ 0.02 below current bid if bid is present
    raw = anchor - max(cushion, 0.02)
    # avoid float fuzz around pennies
    stop_px = round(raw + 1e-9, 2)

    # If rounding caused us to be within 0.01 of bid, push one more cent
    if bid is not None and (stop_px > 0) and (stop_px >= round(float(bid) - 0.01, 2)):
        stop_px = round(float(bid) - 0.02, 2)

    if stop_px <= 0:
        return None, anchor

    return stop_px, base

def _reason_is_1037(e: Exception) -> bool:
    return "'code': 1037" in str(e)

# Normalize symbols for E*TRADE API (e.g., BF.B → BF/B)
def _api_symbol(sym: str) -> str:
    return sym.replace("BF.B", "BF/B")

# ---------------------------------------
# Circuits
# ---------------------------------------
_quote_circuit_until = 0.0     # seconds epoch

def quote_circuit_open() -> bool:
    return time.time() < _quote_circuit_until

def open_quote_circuit(seconds: int):
    global _quote_circuit_until
    _quote_circuit_until = time.time() + seconds
    LOG.warning("quote REST 500; circuit opened for %ds", seconds)
#---------------------------------------
# E*TRADE ops (preview/place) wrappers
# ---------------------------------------
def preview_then_place_limit_sell(aid, symbol, qty, limit_px, retries=None, base_delay=2.0):
    if retries is None:
        retries = int(_CFG.get("max_place_attempts", 1))

    symbol_api = _api_symbol(symbol)
    last_exc = None
    for i in range(1, retries + 1):
        try:
            prv = et.preview_equity_order(aid, symbol_api, int(qty), float(limit_px),
                                          price_type="LIMIT", action="SELL")
            placed = et.place_equity_order(prv, qty=int(qty))
            return placed
        except Exception as e:
            last_exc = e
            if _reason_is_code100(e) or _reason_is_1037(e):
                # Let write_call handle breakers; 1037 = real constraint; both re-raise.
                raise
            raise
    if last_exc:
        raise last_exc
def place_stop_market_sell(aid, symbol, qty, stop_px):
    """
    Arm STOP (market) SELL. E*TRADE STOP preview requires stopPrice in the body.
    """
    symbol_api = _api_symbol(symbol)
    prv = et.preview_equity_order(
        aid, symbol_api, int(qty), None,
        price_type="STOP", action="SELL",
        stop_price=float(stop_px)   # <-- key fix
    )
    return et.place_equity_order(prv, qty=int(qty))

# ---------------------------------------
# Quotes
# ---------------------------------------

def fetch_quotes(symbols, detail="INTRADAY"):
    """
    Return {SYM: {'last': float|None, 'bid': float|None, 'ask': float|None}}.
    Uses get_quotes (bulk) then fills gaps with get_quote (single).
    """
    out = {}
    if not symbols:
        return out
    if quote_circuit_open():
        left = int(_quote_circuit_until - time.time())
        LOG.info("E*TRADE quotes unstable; skipping tick (circuit open, %ds left)", max(0, left))
        return out

    def _put(sym, last=None, bid=None, ask=None):
        if not sym:
            return
        s = str(sym).replace("BF/B", "BF.B").upper()
        rec = out.setdefault(s, {"last": None, "bid": None, "ask": None})
        if last is not None: rec["last"] = float(last)
        if bid  is not None: rec["bid"]  = float(bid)
        if ask  is not None: rec["ask"]  = float(ask)

    def _dig(node):
        if node is None:
            return
        if isinstance(node, dict):
            # common E*TRADE shapes
            for k in ("QuoteResponse", "quoteResponse", "QuoteData", "quotes", "Quote", "All", "all"):
                if k in node:
                    _dig(node[k])

            sym  = node.get("symbol") or (node.get("Product") or {}).get("symbol")
            last = (node.get("lastPrice") or node.get("lastTrade") or node.get("last"))
            bid  = node.get("bid")
            ask  = node.get("ask")

            # 'All' block often has the values too
            allb = node.get("All") or node.get("all") or {}
            last = last or allb.get("lastPrice") or allb.get("lastTrade")
            bid  = bid  or allb.get("bid")
            ask  = ask  or allb.get("ask")

            if sym and (last is not None or bid is not None or ask is not None):
                _put(sym, last, bid, ask)

            for v in node.values():
                _dig(v)

        elif isinstance(node, (list, tuple)):
            for v in node:
                _dig(v)

    # -------- bulk first --------
    try:
        if hasattr(et, "get_quotes"):
            data = et.get_quotes(symbols, detailFlag="ALL")
        else:
            # fallback: join string if someone implements quotes(string)
            data = et.quotes(",".join(symbols), detail="ALL")  # may raise (and that’s fine)
        _dig(data)
    except Exception as e:
        if "500" in str(e):
            open_quote_circuit(60)
            return out
        LOG.warning("quote fetch failed: %s", e)

    # -------- fill gaps with singles --------
    missing = [s for s in symbols if s.upper() not in out or out[s.upper()].get("last") is None]
    for s in missing:
        try:
            if hasattr(et, "get_quote"):
                one = et.get_quote(s, detailFlag="ALL")
                _dig(one)
        except Exception as e:
            LOG.warning("single quote for %s failed: %s", s, e)

    return out

# ---------------------------------------
# Positions / symbols
# ---------------------------------------
# --- entry-price fallback (FIFO-ish) -----------------------------------------
def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def _penny_floor(x: float) -> float:
    return math.floor(float(x) * 100.0) / 100.0

def _safe_sell_stop(bid: float | None, entry: float, stop_bps: int) -> float:
    # raw stop from entry and bps
    raw = round(float(entry) * _bps_to_mult(-abs(stop_bps)), 2)
    # broker rule: for SELL stop, must be at least $0.01 *below* current bid
    if bid is not None:
        raw = min(raw, float(bid) - 0.01)
    # tick-size compliance
    return _penny_floor(raw)

def _iter_dicts_with_symbol(node):
    # walk any E*TRADE portfolio shape and yield dicts that have a "symbol"
    if isinstance(node, dict):
        if "symbol" in node:
            yield node
        for v in node.values():
            yield from _iter_dicts_with_symbol(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _iter_dicts_with_symbol(v)

def fifo_entry_from_trades(account_id_key: str, symbol: str) -> float | None:
    """
    Best-effort entry price for currently held shares.
    Order of attempts:
      1) Pull avg/paid/lot-weighted price from positions
      2) Fall back to VWAP of recent BUY executions for this symbol
    Returns a 2-dec float or None.
    """
    # 1) Positions -> obvious fields -> lots VWAP
    try:
        pos = et.get_positions() or []
        for p in _iter_dicts_with_symbol(pos):
            if str(p.get("symbol")) == symbol:
                # common field names we’ve seen from E*TRADE
                for k in ("pricePaid", "averagePrice", "avgPrice", "purchasePrice", "entryPrice"):
                    v = _safe_float(p.get(k))
                    if v:
                        return round(v, 2)
                lots = p.get("lots") or p.get("Lot") or []
                tot = 0.0
                qty = 0.0
                for lot in lots if isinstance(lots, (list, tuple)) else []:
                    q = _safe_float(lot.get("quantity") or lot.get("qty"))
                    px = _safe_float(lot.get("purchasePrice") or lot.get("price") or lot.get("pricePaid"))
                    if q and px:
                        tot += q * px
                        qty += q
                if qty > 0 and tot > 0:
                    return round(tot / qty, 2)
    except Exception as e:
        LOG.debug("fifo_entry_from_trades: positions path failed: %s", e)
    # ...after: positions = get_positions(...) and managed = [...]
    # Rebuild PDT window counts fresh each loop
    payload     = et.list_executed_orders(days=30)   # plenty; we'll filter by window
    pdt_counts  = recompute_pdt_counts(payload)      # { 'YYYY-MM-DD': count }
    pdt_total   = sum(pdt_counts.values())
    win_sorted  = sorted(pdt_counts.keys())
    log.info(f"PDT 5-biz-day window (ET): { (win_sorted[0]+' -> '+win_sorted[-1]) if win_sorted else 'none' }  count={pdt_total}")

    # (Optional) stash into state if other parts need it
    state["pdt_counts"] = pdt_counts
    state["pdt_total"]  = pdt_total

    # 2) Recent executions VWAP of BUYs (lightweight fallback)
    try:
        execs = et.recent_executions_as_trades(200) or []
        buys = [t for t in execs
                if str(t.get("symbol")) == symbol and str(t.get("action", "")).upper().startswith("BUY")]
        tot = 0.0
        qty = 0
        for t in buys:
            q  = int(t.get("qty") or t.get("quantity") or 0)
            px = _safe_float(t.get("price_paid") or t.get("price"))
            if q and px:
                tot += q * px
                qty += q
        if qty > 0 and tot > 0:
            return round(tot / qty, 2)
    except Exception as e:
        LOG.debug("fifo_entry_from_trades: executions path failed: %s", e)

    return None
# ---------------------------------------------------------------------------
def _reason_is_code100(err: Exception) -> bool:
    s = str(err).lower()
    return (" code': 100" in s) or ('"code": 100' in s) or ("service is not currently available" in s)

def list_symbols_from_positions(aid, blocklist):
    import inspect
    syms, tried = [], []
    candidates = ("get_positions", "positions", "portfolio", "list_positions", "holdings", "portfolio_positions")

    def _dig(n):
        if n is None: return
        if isinstance(n, dict):
            s = (n.get("symbol")
                 or n.get("Product", {}).get("symbol")
                 or n.get("instrument", {}).get("symbol"))
            if s:
                s = s.replace("BF/B", "BF.B")
                syms.append(s)
            for v in n.values():
                _dig(v)
        elif isinstance(n, list):
            for v in n:
                _dig(v)

    for attr in candidates:
        fn = getattr(et, attr, None)
        if not callable(fn):
            continue
        tried.append(attr)
        try:
            params = inspect.signature(fn).parameters
            data = fn(aid) if len(params) >= 1 else fn()
            _dig(data)
            if syms:
                LOG.info("positions via %s -> %d symbol(s)", attr, len(syms))
                break
        except Exception as e:
            LOG.warning("positions via %s failed: %s", attr, e)

    uniq, seen = [], set()
    for s in syms:
        if s in seen or (blocklist and s in blocklist):
            continue
        seen.add(s)
        uniq.append(s)

    if not uniq:
        LOG.warning("No symbols found from positions; SELL GUARD will idle. Tried: %s", ",".join(tried) or "none")
    return uniq
def _debug_glimpse_position(aid, symbol):
    try:
        data = et.get_positions(aid)
    except Exception:
        return
    keys = set()
    def visit(n):
        if isinstance(n, dict):
            s = (n.get("symbol") or (n.get("Product") or {}).get("symbol"))
            if s and s.replace("BF/B","BF.B").upper() == symbol.upper():
                keys.update(n.keys())
            for v in n.values(): visit(v)
        elif isinstance(n, (list, tuple)):
            for v in n: visit(v)
    visit(data)
    if keys:
        LOG.info("%s position keys: %s", symbol, ",".join(sorted(keys)))

# --- Hold-time estimator (for protect_after / logging) -----------------------
def _parse_ms(val) -> int:
    """Robust convert: epoch s/ms, ISO, or 'YYYY-MM-DD HH:MM:SS' -> ms."""
    from datetime import datetime, timezone
    try:
        if val is None:
            return 0
        if isinstance(val, (int, float)):
            v = float(val)
            return int(v if v > 10_000_000_000 else v * 1000)  # ms vs s
        s = str(val).strip()
        if not s:
            return 0
        if s.isdigit():
            v = float(s)
            return int(v if v > 10_000_000_000 else v * 1000)
        if " " in s and "T" not in s:
            s = s.replace(" ", "T")
        if "Z" not in s and "+" not in s:
            s += "Z"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0

# --- ET time + Regular Trading Hours helpers ---------------------------------
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # fallback handled below

def _now_et():
    try:
        return datetime.now(tz=ZoneInfo("America/New_York")) if ZoneInfo else datetime.now()
    except Exception:
        return datetime.now()

def _is_us_trading_day(dt):
    return dt.weekday() < 5  # Mon–Fri (holiday calendar omitted)

def _as_hhmm(v, default: int) -> int:
    """
    Normalize a variety of inputs to HHMM as int.
    Accepts: 930, "930", "09:30", "9:30", "0930". Falls back to default on error.
    """
    try:
        if v is None:
            return int(default)
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip()
        if ":" in s:
            hh, mm = s.split(":", 1)
            hh = int(hh)
            mm = int(mm)
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                return int(default)
            return hh * 100 + mm
        # plain digits like "0935" or "935"
        n = int(s)
        return n
    except Exception:
        return int(default)


def _is_rth_now(start_hhmm=930, end_hhmm=1600) -> bool:
    """True if now(ET) is within [start_hhmm, end_hhmm]. Accepts 930/'930'/'09:30'."""
    def _coerce(v, default=930):
        try:
            s = str(v).strip()
            if ":" in s:
                hh, mm = s.split(":", 1)
                return int(hh) * 100 + int(mm)
            return int(s)
        except Exception:
            return int(default)

    now = _now_et()
    if not _is_us_trading_day(now):
        return False

    start = _coerce(start_hhmm, 930)
    end   = _coerce(end_hhmm, 1600)
    hhmm  = now.hour * 100 + now.minute
    LOG.debug("sell window check: start=%04d end=%04d now=%04d", start, end, hhmm)
    return start <= hhmm <= end
def _estimate_hold_minutes(aid: str, symbol: str, lookback_days: int = 90) -> int | None:
    """
    Walk trades chronologically; track position size by FIFO adds/consumes.
    Return minutes since the last time size went from <=0 to >0 for this symbol.
    If flat -> None.
    """
    s = symbol.upper().replace("BF/B", "BF.B")

    # How many shares are we actually free to sell? (if 0, consider flat)
    try:
        free = int(et.available_to_sell(aid, s) or 0)
    except Exception:
        free = 0
    if free <= 0:
        return None

    # Pull trades (prefer transactions; fallback to executions)
    trades = []
    try:
        if hasattr(et, "transactions_as_trades"):
            trades = et.transactions_as_trades(lookback_days) or []
    except Exception:
        trades = []
    if not trades:
        try:
            trades = et.recent_executions_as_trades(1000) or []
        except Exception:
            trades = []

    # Chronological (oldest->newest)
    trades = sorted(trades, key=lambda t: _parse_ms(t.get("time_ms") or t.get("time_utc") or t.get("time")))

    pos = 0
    opened_ms = None
    for t in trades:
        if (t.get("symbol") or "").upper().replace("BF/B", "BF.B") != s:
            continue
        side = (t.get("action") or "").upper()
        try:
            qty = int(float(t.get("qty") or 0))
        except Exception:
            qty = 0
        tms = _parse_ms(t.get("time_ms") or t.get("time_utc") or t.get("time"))

        if qty <= 0:
            continue

        if side == "BUY":
            prev = pos
            pos += qty
            if prev <= 0 and pos > 0:
                opened_ms = tms  # (re)opened here
        elif side == "SELL":
            pos -= qty
            if pos <= 0:
                opened_ms = None  # flat again; next BUY will reopen

    if pos <= 0 or opened_ms is None:
        return None

    # minutes since opened
    now_ms = int(_now_et().timestamp() * 1000)
    mins = max(0, int((now_ms - opened_ms) / 60000))
    return mins

def available_to_sell(aid, symbol) -> int:
    try:
        return int(et.available_to_sell(aid, _api_symbol(symbol)) or 0)
    except Exception as e:
        LOG.warning("available_to_sell failed for %s: %s", symbol, e)
        return 0

def position_entry_price(aid, symbol, _positions_cache=[None]) -> float | None:
    """
    Best-effort dig for average/basis price from positions.
    Falls back to FIFO-from-trades if positions have no price.
    """
    sym_target = symbol.replace("BF/B", "BF.B").upper()

    # Cache positions per run so we don't hammer the API
    if _positions_cache[0] is None:
        getters = ("positions", "portfolio", "holdings", "list_positions", "get_positions")
        for g in getters:
            fn = getattr(et, g, None)
            if callable(fn):
                try:
                    _positions_cache[0] = fn(aid)
                    break
                except Exception:
                    pass

    data = _positions_cache[0]

    # all the price-ish keys we see in the wild
    PRICE_KEYS = {
        "pricePaid", "purchasePrice", "avgPrice", "averagePrice",
        "costPerShare", "costBasisPerShare", "costBasis", "totalCost",
        "price", "unitPrice", "lotPrice"
    }

    def _to_f(x):
        try:
            if x is None: return None
            return float(str(x).replace(",", ""))
        except Exception:
            return None

    found = []
    def fifo_entry_from_trades(aid, symbol, days=60) -> float | None:
        """
        Build current lots from trades (BUY adds, SELL consumes FIFO)
        and return weighted avg cost for remaining shares up to inv qty.
        """
        sym = symbol.upper()
        # how many shares are we actually long?
        try:
            inv_qty = int(et.available_to_sell(aid, sym) or 0)
        except Exception:
            inv_qty = 0
        if inv_qty <= 0:
            return None

        # pull trades
        trades = []
        try:
            if hasattr(et, "transactions_as_trades"):
                trades = et.transactions_as_trades(days) or []
        except Exception:
            trades = []
        if not trades:
            try:
                # generous count; wrapper typically accepts a max size
                trades = et.recent_executions_as_trades(1000) or []
            except Exception:
                trades = []

        # chrono asc
        def _tms(t):
            v = t.get("time_ms") or t.get("time_utc") or t.get("time") or 0
            from datetime import datetime, timezone
            try:
                if isinstance(v, (int, float)):
                    return int(v if v > 10_000_000_000 else v * 1000)
                s = str(v)
                if " " in s and "T" not in s:
                    s = s.replace(" ", "T")
                if "Z" not in s and "+" not in s:
                    s += "Z"
                return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                return 0

        trades = sorted(trades, key=_tms)

        # FIFO stack: [qty, px]
        lots = []
        for t in trades:
            if (t.get("symbol") or "").upper() != sym:
                continue
            side = (t.get("action") or "").upper()
            try:
                q = int(float(t.get("qty") or 0))
                px = float(t.get("price") or t.get("price_paid") or 0)
            except Exception:
                continue
            if q <= 0 or px <= 0:
                continue
            if side == "BUY":
                lots.append([q, px])
            elif side == "SELL":
                remain = q
                while remain > 0 and lots:
                    lq, lpx = lots[0]
                    take = min(remain, lq)
                    lq -= take; remain -= take
                    if lq == 0:
                        lots.pop(0)
                    else:
                        lots[0][0] = lq

        # compute weighted avg for remaining qty up to inv_qty
        if not lots:
            return None
        qty_left = inv_qty
        cost = 0.0
        sh = 0
        for lq, lpx in lots:
            take = min(qty_left, lq)
            if take <= 0:
                break
            cost += take * lpx
            sh += take
            qty_left -= take
        if sh <= 0:
            return None
        return round(cost / sh, 4)

    def visit(n):
        if n is None:
            return
        if isinstance(n, dict):
            # symbol on this node?
            s = (n.get("symbol")
                 or (n.get("Product") or {}).get("symbol")
                 or (n.get("instrument") or {}).get("symbol"))
            if s:
                s_norm = s.replace("BF/B", "BF.B").upper()
                if s_norm == sym_target:
                    # scan known price keys
                    for k in PRICE_KEYS:
                        v = n.get(k)
                        f = _to_f(v)
                        if f and f > 0:
                            found.append(f)
                            break
            for v in n.values():
                visit(v)
        elif isinstance(n, (list, tuple)):
            for v in n:
                visit(v)

    visit(data)

    if found:
        return found[0]

    # No price in positions? fall back to FIFO-from-trades
    return fifo_entry_from_trades(aid, sym_target)

# ---------------------------------------
# Main
# ---------------------------------------

def main():
    LOG.info("env: ETRADE_ENV=%s  PYTHONPATH=%s",
             os.getenv("ETRADE_ENV", "production"), os.getenv("PYTHONPATH"))
    now = int(time.time())
    heartbeat(now)
    LOG.debug("tick: polling positions & quotes…")

    mode = str(_CFG.get("mode", "live")).lower()
    tp_bps = int(_CFG.get("target_bps", _DEFAULTS["target_bps"]))
    stop_bps = int(_CFG.get("stop_bps", _DEFAULTS["stop_bps"]))
    max_hold_mins = int(_CFG.get("max_hold_mins", _DEFAULTS["max_hold_mins"]))
    limit_from = str(_CFG.get("limit_from", _DEFAULTS["limit_from"])).lower()
    offset_bps = int(_CFG.get("limit_offset_bps", 0))
    poll_s = max(1.0, float(_CFG.get("throttle_ms", 3000)) / 1000.0)
    blocklist = list(_CFG.get("blocklist", []))
    market_fb_for = set(map(str.upper, _CFG.get("market_fallback_for", [])))
    # replace your protect_after block with this:
    protect_after = _CFG.get("protect_after_mins", _CFG.get("sell_protect_after_mins", None))
    try:
        protect_after = int(protect_after) if protect_after is not None else None
    except Exception:
        protect_after = None

    aid = et.account_id_key()
    LOG.info("[LIVE] Using accountIdKey=%s", aid)
    heartbeat(int(time.time()), aid)   # seed heartbeat with account id

    last_syms_log = 0.0
    LOG.info(
    "[CFG] mode=%s tp=%d bps stop=%d bps max_hold=%dm limit_from=%s offset=%d bps throttle=%.1fs ext_hours=%s fallback=%s",
    mode, tp_bps, stop_bps, max_hold_mins, limit_from, offset_bps, poll_s,
    _CFG.get("use_extended_hours", False),
    ",".join(sorted(market_fb_for)) or "—"
)
    # ---- interpret your config names ----
    avoid_pdt = bool(_CFG.get("avoid_daytrades", True))
    intraday_stop_ok = bool(_CFG.get("allow_intraday_stoploss", False))

    # convert min_hold_days to minutes (6.5h = 390m per RTH day)
    hold_days = int(_CFG.get("min_hold_days", 0))
    min_hold_minutes = int(_CFG.get("min_hold_minutes", hold_days * 390))

    # optional sell window (keeps exits in RTH and away from the open/close)
    sell_win_start = str(_CFG.get("sell_window_start_et", "09:35"))
    sell_win_end   = str(_CFG.get("sell_window_end_et",   "15:55"))

    while True:
        start = time.time()
        heartbeat(
            now=datetime.now(tz=ET),
            account_id=(acct.get("account_id") if 'acct' in locals() else None),
            logger=LOG
        )

        # SYMBOLS from positions
        syms = list_symbols_from_positions(aid, blocklist)
        if syms and (time.time() - last_syms_log > 5.0):
            LOG.info("Managing %d symbol(s): %s", len(syms), ",".join(syms))
            last_syms_log = time.time()

        if not syms:
            time.sleep(poll_s)
            continue

        # QUOTES
        qs = fetch_quotes(syms, detail="INTRADAY")
        missing = [s for s in syms if s not in qs or qs[s].get("last") is None]
        if missing:
            LOG.warning("No last price for: %s", ",".join(missing))

        # DECISIONS
        for s in syms:
            q    = qs.get(s, {})
            last = q.get("last"); bid = q.get("bid"); ask = q.get("ask")

            # entry price & hold minutes
            entry = position_entry_price(aid, s)
            if entry is None:
                entry = fifo_entry_from_trades(aid, s)  # FIFO fallback

            try:
                hold_mins = _estimate_hold_minutes(aid, s)
            except Exception as _e:
                LOG.debug("hold-mins failed for %s: %s", s, _e)
                hold_mins = None

            # Skip if we can't compute signals
            if entry is None or last is None:
                LOG.info("Skip %s: missing price(s) entry=%s last=%s", s, entry, last)
                continue

            pnl_mult = (float(last) / float(entry)) if entry else 0.0
            pnl_bps  = int(round((pnl_mult - 1.0) * 10_000))

            # compute SELL signals
            do_stop    = pnl_bps <= -abs(stop_bps)
            do_tp      = (tp_bps < 1_000_000) and (pnl_bps >= tp_bps)
            do_timeout = (hold_mins is not None and max_hold_mins > 0 and hold_mins >= max_hold_mins)

            # optional protective stop after X minutes regardless of P&L
            if protect_after is not None and protect_after > 0 and hold_mins is not None:
                if hold_mins >= protect_after:
                    do_stop = True

            # compute limit price from cfg
            lim = _sell_limit_from_cfg(last, bid, ask, limit_from=limit_from, offset_bps=offset_bps)

            # free/reserved
            free = available_to_sell(aid, s)
            if free <= 0:
                LOG.info("Skip %s SELL: free=0 (reserved by open sell order)", s)
                continue

            # One-line decision trace
            hold_txt = (f"{hold_mins}m" if hold_mins is not None else "?")
            lim_txt  = ("—" if lim is None else f"{lim:.2f}")
            LOG.info(
                "[SG] %s: last=%.2f entry=%.2f pnl=%+d bps (tp=%d stop=%d) hold=%s lim=%s free=%d -> stop=%s tp=%s timeout=%s",
                s, float(last), float(entry), int(pnl_bps), tp_bps, stop_bps, hold_txt, lim_txt, int(free),
                bool(do_stop), bool(do_tp), bool(do_timeout)
            )

            # 1) Enforce “no day trades”: skip sells until min_hold_minutes unless intraday stop is allowed
            pdt_block = (avoid_pdt and hold_mins is not None and hold_mins < min_hold_minutes)
            if pdt_block and not intraday_stop_ok:
                LOG.info("%s PDT guard: hold=%dm < %dm — skipping all sells today", s, hold_mins, min_hold_minutes)
                continue

            # 2) Keep sells inside RTH window unless ext hours enabled
            if not _CFG.get("use_extended_hours", False) and not _is_rth_now(sell_win_start, sell_win_end):
                LOG.info("%s outside sell window %s–%s ET; deferring any sells", s, sell_win_start, sell_win_end)
                continue

            # ---------------------------
            # 1) HARD STOP (2084-aware)
            # ---------------------------
            allow_stop_now = (
                do_stop
                and stop_bps > 0
                and free > 0
                and last is not None
                and (intraday_stop_ok or not pdt_block)
            )

            if allow_stop_now:
                stop_px, base_px = _strict_stop_for_sell(entry, bid, last, stop_bps, cushion=0.02)
                if stop_px is None:
                    LOG.debug("%s skip STOP: could not compute valid stop (entry=%s bid=%s last=%s base=%s)",
                              s, entry, bid, last, base_px)
                else:
                    LOG.debug("%s stop calc: entry=%s bid=%s last=%s base=%.2f -> stop=%.2f",
                              s, entry, bid, last, base_px or float('nan'), stop_px)
                    try:
                        placed = write_call(lambda: place_stop_market_sell(aid, s, free, stop_px))
                        LOG.info("%s ARM HARD STOP placed -> %s", s, placed)
                        continue
                    except Exception as e:
                        if _is_2084(e):
                            for buf in (0.03, 0.04):
                                q = et.get_quote(s, detailFlag="ALL")
                                bid2 = (q.get("All") or {}).get("bid") or q.get("bid")
                                if bid2:
                                    adj = round(float(bid2) - buf, 2)
                                    if adj > 0:
                                        try:
                                            LOG.warning("%s STOP 2084 -> adjust to %.2f (buf=%.2f) & retry", s, adj, buf)
                                            placed = write_call(lambda: place_stop_market_sell(aid, s, free, adj))
                                            LOG.info("%s ARM HARD STOP placed (after 2084 adjust buf=%.2f) -> %s", s, buf, placed)
                                            break
                                        except Exception as e2:
                                            if not _is_2084(e2):
                                                raise
                            else:
                                LOG.error("%s STOP failed after 2x 2084 adjusts", s)
                        # (fallback path continues below)
                        # Last-ditch MARKET only if configured
                        if "SELL_STOP" in market_fb_for or "TIMEOUT" in market_fb_for:
                            if WRITE_CB.is_open():
                                enqueue_sell(s, free, "SELL", None, why="circuit open; skip STOP MARKET fallback")
                                LOG.info("%s SELL deferred: circuit open; skipping STOP-MARKET fallback", s)
                            else:
                                try:
                                    LOG.warning("%s STOP MARKET fallback", s)
                                    placed = write_call(lambda: preview_then_place_market_sell(aid, s, free))
                                    LOG.info("%s STOP MARKET placed -> %s", s, placed)
                                    continue
                                except CircuitOpen as ce:
                                    enqueue_sell(s, free, "SELL", None, why=f"STOP MARKET fallback: {ce}")
                                except Exception as e2:
                                    if is_code100(e2):
                                        enqueue_sell(s, free, "SELL", None, why="code100 during STOP MARKET fallback")
                                    else:
                                        LOG.error("%s STOP MARKET fallback failed: %s", s, e2)


            # ---------------------------
            # 2) SELL TARGET (TP / TIMEOUT)
            # ---------------------------
            if (do_tp or do_timeout) and not pdt_block:
                if lim is None:
                    LOG.debug("%s skip SELL_TARGET: no bid/last for limit calc", s)
                else:
                    why = "TP" if (do_tp and not do_timeout) else ("TIMEOUT" if do_timeout and not do_tp else "TP+TIMEOUT")
                    try:
                        placed = write_call(lambda: preview_then_place_limit_sell(aid, s, free, lim))
                        LOG.info("%s %s LIMIT placed -> %s", s, why, placed)
                    # inside the SELL TARGET exception block
                    except CircuitOpen as ce:
                        enqueue_sell(s, free, "SELL", lim, why=str(ce))
                    except Exception as e:
                        if is_code100(e):
                            maybe_banner_code100()
                            enqueue_sell(s, free, "SELL", lim, why="code100 during place")
                            LOG.warning("%s SELL queued (code100 during place)", s)
                            continue

        # pacing
        elapsed   = time.time() - start
        sleep_for = max(0.0, poll_s - elapsed)
        # Try to flush queued sells (fires as soon as circuit closes)
        drain_pending_sells(lambda sym, qty, side, px:
            et.place_equity_order(
                et.preview_equity_order(aid, _api_symbol(sym), int(qty), px,
                                        price_type=("LIMIT" if px is not None else "MARKET"),
                                        action=side),
                qty=int(qty)
            )
        )

        if sleep_for > 0:
            time.sleep(sleep_for)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOG.info("sell-guard: interrupted by user")
