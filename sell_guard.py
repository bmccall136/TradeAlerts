
from __future__ import annotations
# --- Windows-safe logging shim: strip unsupported %f and set our own handler ---
import logging, sys

# If anyone sets a formatter with %f later, neuter it here
_orig_formatTime = logging.Formatter.formatTime
def _sg_formatTime(self, record, datefmt=None):
    if datefmt and "%f" in datefmt:  # Windows strftime has no %f
        datefmt = datefmt.replace("%f", "")
    return _orig_formatTime(self, record, datefmt)
logging.Formatter.formatTime = _sg_formatTime

def _sg_init_logger():
    fmt     = "%(asctime)s.%(msecs)03d %(levelname)s  %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    # Kill any inherited/root handlers that might carry bad datefmt
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    log = logging.getLogger("sell-guard")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    log.addHandler(h)
    log.propagate = False
    return log

LOG = _sg_init_logger()

# sell_guard.py
# Guard that scans positions and places SELL orders for eligible holdings.
# - Reads settings from SELL_GUARD_SETTINGS env var or .\sell_guard_settings.json
# - Uses etrade_service wrappers for preview/place
# - Adaptive: retries venue 500/code 100 with fresh preview; falls back to numeric accountId
# - MARKET by default, or marketable LIMIT from bid-1 tick when configured
#
# Python 3.11+
import json
import logging
import os
import random
import string
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import datetime as _dt
from typing import Any, List, Tuple, Dict

try:
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

# --- logging (no %f; include millis) ------------------------------------------
LOG = logging.getLogger("sell-guard")
LOG.setLevel(logging.INFO)
for h in list(LOG.handlers):
    LOG.removeHandler(h)
_handler = logging.StreamHandler(sys.stdout)
_formatter = logging.Formatter(
    fmt="%(asctime)s,%(msecs)03d %(levelname)s sell-guard: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_handler.setFormatter(_formatter)
LOG.addHandler(_handler)

# --- local imports -------------------------------------------------------------
HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from services import etrade_service as et
except Exception as e:
    LOG.error("could not import etrade_service: %s", e)
    raise


# --- small utils ---------------------------------------------------------------
def j(x: Any) -> str:
    try:
        return json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(x)


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def now_et() -> datetime:
    if ET:
        return datetime.now(ET)
    return datetime.now(UTC)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def rand_id(prefix: str, n: int = 6) -> str:
    sfx = "".join(
        random.choice(string.ascii_lowercase + string.digits) for _ in range(n)
    )
    return f"{prefix}{sfx}"
# Track post-protect high watermark for trailing, per symbol
_PROTECT_STATE = {}  # sym -> {"hi": float}

# ==== BEGIN: SELL GATES HELPERS ====

def _normalize_positions(pos_obj) -> List[Dict[str, Any]]:
    """
    Flatten common E*TRADE position shapes to:
    {symbol, quantity, available, entry_price, last}
    """
    out = []
    def L(x): return x if isinstance(x, list) else ([] if x is None else [x])
    if not isinstance(pos_obj, dict):
        return out
    pr = pos_obj.get("PortfolioResponse") or {}
    for ap in L(pr.get("AccountPortfolio")):
        positions = (ap.get("Position") or ap.get("position")
                     or ap.get("Positions") or ap.get("positions"))
        for p in L(positions):
            prod = p.get("Product") or p.get("product") or {}
            sym  = (prod.get("symbol") or "").strip().upper()
            if not sym:
                desc = (p.get("symbolDescription") or "").strip()
                if "(" in desc and desc.endswith(")"):
                    sym = desc.split("(")[-1][:-1].strip().upper()
            qty = p.get("quantity") or p.get("qty") or p.get("longQty") or p.get("longQuantity") or 0
            avail = p.get("available") or p.get("availableToSell") or qty
            entry = p.get("pricePaid") or p.get("purchasePrice") or p.get("averagePrice") or 0
            q = float(qty or 0)
            if sym and q > 0:
                quick = p.get("Quick") or {}
                last  = quick.get("lastTrade") or 0
                out.append({
                    "symbol": sym,
                    "quantity": q,
                    "available": float(avail or 0),
                    "entry_price": float(entry or 0),
                    "last": float(last or 0),
                })
    return out


def _entry_price_from_positions(pos_map: Dict[str, Dict[str, Any]], sym: str) -> float | None:
    r = pos_map.get((sym or "").upper())
    if not r:
        return None
    v = float(r.get("entry_price") or 0)
    return v if v > 0 else None

def _apply_sell_protection(sym: str, entry_px: float, last_px: float, opened_ts: float, now_ts: float, cfg: dict):
    """
    Enforce post-N-minutes protection:
      - if gain < protect_min_gain_pct  -> hard stop at -1.0% (from entry)
      - if gain >= protect_trail_arm_pct -> 3% trailing off session high since protection started
    Returns a dict like {"action":"SELL", "reason":"..."} or None to keep holding.
    """
    sg = cfg.get("sell_guard", {}) if "sell_guard" in cfg else cfg

    mins = float(sg.get("sell_protect_after_mins") or 0)
    if mins <= 0:
        return None

    protect_min_gain = float(sg.get("protect_min_gain_pct", 1.5))
    trail_arm_pct    = float(sg.get("protect_trail_arm_pct", 3.0))
    trail_pct        = float(sg.get("protect_trail_pct", 3.0))
    base_stop_bps    = float(sg.get("stop_bps", 100.0))  # fallback if you want -1.0% in bps

    elapsed_min = max(0.0, (now_ts - opened_ts) / 60.0)
    if elapsed_min < mins:
        # Not in protection window yet; also reset any stale hi
        _PROTECT_STATE.pop(sym, None)
        return None

    # pct helper
    def _pct(cur, ref):
        try:
            return (cur - ref) / ref * 100.0
        except Exception:
            return 0.0

    gain_pct = _pct(last_px, entry_px)

    # 1) Not working enough -> enforce hard stop at -1.0% from entry
    if gain_pct < protect_min_gain:
        hard_stop_pct = -abs(base_stop_bps) / 100.0  # -1.0% when stop_bps=100
        if gain_pct <= hard_stop_pct:
            return {"action": "SELL", "reason": f"PROTECT_BASE_STOP({hard_stop_pct:.2f}%)", "gain_pct": round(gain_pct, 3)}
        # else: above the stop, do nothing yet
        return None

    # 2) Working well -> laddered trailing off high since protection start
    st = _PROTECT_STATE.get(sym)
    if st is None:
        st = {"hi": float(last_px)}
        _PROTECT_STATE[sym] = st
    if last_px > st["hi"]:
        st["hi"] = float(last_px)

    # Ladder: arm levels based on current gain
    #  +3% → 3% trail,  +5% → 2.5% trail,  +8% → 2.0% trail (tweak as you like)
    trail_pct_now = None
    if gain_pct >= 8.0:
        trail_pct_now = 2.0
    elif gain_pct >= 5.0:
        trail_pct_now = 2.5
    elif gain_pct >= trail_arm_pct:  # e.g., 3.0
        trail_pct_now = trail_pct     # e.g., 3.0

    if trail_pct_now is not None:
        trail_trigger = st["hi"] * (1.0 - trail_pct_now / 100.0)
        if last_px <= trail_trigger:
            return {
                "action": "SELL",
                "reason": f"PROTECT_TRAIL_LADDER({trail_pct_now:.2f}%)",
                "gain_pct": round(gain_pct, 3)
            }


def _to_epoch_ms_any(ts):
    """Accept ms, sec, or ISO; return epoch ms or None."""
    try:
        if ts is None:
            return None
        if isinstance(ts, (int, float)):
            v = float(ts)
            return int(v if v > 10_000_000_000 else v * 1000)
        s = str(ts).strip()
        if not s:
            return None
        if s.isdigit():
            v = float(s)
            return int(v if v > 10_000_000_000 else v * 1000)
        # normalize ISO
        s = s.replace(" ", "T")
        if "Z" not in s and "+" not in s:
            s += "Z"
        from datetime import datetime as _dt
        dt = _dt.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _cache_today_transactions():
    """
    Fetch today's transactions once; return (tx_today, buy_set, last_buy_ms_map).
    buy_set: set of symbols bought today.
    last_buy_ms_map: {SYM: last_buy_ms}
    """
    try:
        tx = et.get_transactions(start="today", end="today") or []
    except Exception:
        tx = []

    buy_set = set()
    last_buy_ms = {}

    for t in tx:
        if not isinstance(t, dict):
            continue
        sym = (t.get("symbol") or t.get("securitySymbol") or "").strip().upper()
        side = (t.get("transactionType") or t.get("side") or "").upper()
        if not sym:
            continue
        if "BUY" in side:
            buy_set.add(sym)
            ms = (
                _to_epoch_ms_any(t.get("time"))
                or _to_epoch_ms_any(t.get("time_ms"))
                or _to_epoch_ms_any(t.get("transactionDate"))
            )
            if ms is not None:
                prev = last_buy_ms.get(sym)
                if prev is None or ms > prev:
                    last_buy_ms[sym] = ms

    return tx, buy_set, last_buy_ms


def _opened_today_cached(sym: str, buy_set: set) -> bool:
    return (sym or "").strip().upper() in buy_set


def _minutes_since_last_buy_cached(sym: str, last_buy_ms_map: dict) -> float | None:
    symu = (sym or "").strip().upper()
    ms = last_buy_ms_map.get(symu)
    if ms is None:
        return None
    dt_buy = _dt.datetime.fromtimestamp(ms / 1000.0, tz=ET)
    return max(0.0, (now_et() - dt_buy).total_seconds() / 60.0)

# ==== END: SELL GATES HELPERS ====

def _last_buy_time_et(sym: str):
    """Return ET datetime of most-recent BUY for sym today, or None."""
    try:
        s = (sym or "").strip().upper()
        tx = et.get_transactions(start="today", end="today") or []
        best = None
        for t in tx:
            if not isinstance(t, dict): 
                continue
            tsym = (t.get("symbol") or t.get("securitySymbol") or "").strip().upper()
            side = (t.get("transactionType") or t.get("side") or "").upper()
            if tsym != s or "BUY" not in side:
                continue
            # accept ms, sec, or iso datetime
            ts = t.get("time") or t.get("time_ms") or t.get("transactionDate")
            ms = None
            try:
                if isinstance(ts, (int, float)):
                    ms = int(ts if ts > 10_000_000_000 else ts * 1000)
                elif isinstance(ts, str):
                    if ts.isdigit():
                        v = float(ts)
                        ms = int(v if v > 10_000_000_000 else v * 1000)
                    else:
                        from datetime import datetime, timezone
                        ts2 = ts.replace("Z", "+00:00").replace(" ", "T")
                        dt = datetime.fromisoformat(ts2)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        ms = int(dt.timestamp() * 1000)
            except Exception:
                ms = None
            if ms:
                from datetime import datetime
                dt = datetime.fromtimestamp(ms / 1000.0, tz=ET or UTC)
                if best is None or dt > best:
                    best = dt
        return best
    except Exception:
        return None


def _minutes_since_last_buy(sym: str) -> float | None:
    dt = _last_buy_time_et(sym)
    if not dt:
        return None
    delta = (now_et() - dt).total_seconds() / 60.0
    return max(0.0, delta)

# Conservative PDT helper: if we bought SYM today, selling it today would be a day trade
def _opened_today(sym: str) -> bool:
    try:
        s = (sym or "").strip().upper()
        # Adjust to your etrade_service API; many wrappers expose a transactions getter
        tx = et.get_transactions(
            start="today", end="today"
        )  # use your real function name
        for t in tx or []:
            if not isinstance(t, dict):
                continue
            tsym = (t.get("symbol") or t.get("securitySymbol") or "").strip().upper()
            side = (t.get("transactionType") or t.get("side") or "").upper()
            if tsym == s and "BUY" in side:
                return True
    except Exception:
        pass
    return False


# --- config -------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "mode": "live",
    "normalize_tick": 0.01,
    "sell_window_start_et": "09:35",
    "sell_window_end_et": "15:55",
    "throttle_ms": 30_000,
    "use_extended_hours": False,
    "market_fallback_for": ["SELL_STOP", "TIMEOUT"],
    "max_place_attempts": 4,
    # Sell-guard sub-config (defaults aligned to your JSON)
    "sell_guard": {
        "allow_intraday_stoploss": True,
        "avoid_daytrades": False,
        "blocklist": [],
        "force_symbols": [],
        "force_without_entry": False,     # <- match JSON
        "limit_from": "bid",
        "limit_offset_bps": 0,
        "max_hold_mins": 1_000_000,
        "min_hold_days": 0,               # <- match JSON
        "min_hold_minutes": 15,           # <- match JSON
        "normalize_tick": 0.01,
        "sell_protect_after_mins": None,
        "sell_window_start_et": "09:35",
        "sell_window_end_et": "15:55",
        "stop_bps": 100,
        "target_bps": 200,
        "use_extended_hours": False,
        "circuit_fail_threshold": 2,
        "circuit_open_seconds": 480,
        "market_fallback_for": ["SELL_STOP"],
    },
}


def load_settings() -> dict[str, Any]:
    path = os.environ.get("SELL_GUARD_SETTINGS") or os.path.join(
        HERE, "sell_guard_settings.json"
    )
    LOG.info("Using SELL_GUARD_SETTINGS=%s", path)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        LOG.warning("settings file not found; using defaults")
        cfg = {}
    # merge shallow
    merged = {**DEFAULT_SETTINGS, **cfg}
    # ensure nested sell_guard merges
    sg = {**DEFAULT_SETTINGS["sell_guard"], **(merged.get("sell_guard") or {})}
    merged["sell_guard"] = sg
    return merged


# --- account & quotes ----------------------------------------------------------
# --- Force-list probe ---------------------------------------------------------


def force_probe_candidates(acct_key: str, cfg) -> list[tuple[str, int]]:
    """
    Return [(SYMBOL, QTY)] for any force-listed symbols that actually have
    shares available_to_sell right now. Skips blocklist.
    """
    try:
        sg = cfg.sg  # your nested sell_guard dict
    except AttributeError:
        sg = {}

    block = set(map(str.upper, (sg.get("blocklist") or [])))
    force = list(map(str.upper, (sg.get("force_symbols") or [])))

    out: list[tuple[str, int]] = []
    for s in force:
        if s in block:
            continue
        try:
            avail = int(round(available_to_sell(acct_key, s)))
        except Exception as e:
            LOG.warning("[FORCE] %s available_to_sell check failed: %s", s, e)
            continue
        LOG.info("[FORCE] %s available_to_sell=%s", s, avail)
        if avail > 0:
            out.append((s, avail))
    return out


def get_acct_key() -> str:
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k:
                return str(k)
        except Exception:
            pass
    if hasattr(et, "account_id_key"):
        k = et.account_id_key
        if k:
            return str(k)
    raise RuntimeError("Could not determine account_id_key")


# --- account & quotes ----------------------------------------------------------
def available_to_sell(acct_key: str, symbol: str) -> float:
    if hasattr(et, "available_to_sell"):
        try:
            v = et.available_to_sell(acct_key, symbol)
            return float(v or 0.0)
        except Exception as e:
            LOG.warning("available_to_sell wrapper failed: %s", e)

    try:
        pos = et.get_positions(acct_key)
    except TypeError:
        pos = et.get_positions()

    for row in _normalize_positions(pos):
        if row.get("symbol") == (symbol or "").upper():
            return float(row.get("available") or row.get("quantity") or 0.0)
    return 0.0

def fetch_quote(symbol: str) -> dict[str, Any]:
    # prefer fast wrapper if present
    try:
        q = et.fetch_etrade_quote(symbol)
        if isinstance(q, dict):
            return q
    except Exception:
        pass
    try:
        g = et.get_quote(symbol)
        return g or {}
    except Exception:
        return {}


def best_bid(symbol: str) -> float:
    q = fetch_quote(symbol)
    # common shapes
    for src in (
        q,
        q.get("All") or {},
        (q.get("QuoteResponse") or {}).get("QuoteData") or {},
    ):
        if isinstance(src, list):
            src = src[0] if src else {}
        if isinstance(src, dict):
            for k in ("bid", "bidPrice", "bestBid"):
                if k in src:
                    return f(src[k], 0.0)
    return 0.0


def last_trade(symbol: str) -> float:
    q = fetch_quote(symbol)
    for src in (
        q,
        q.get("All") or {},
        (q.get("QuoteResponse") or {}).get("QuoteData") or {},
    ):
        if isinstance(src, list):
            src = src[0] if src else {}
        if isinstance(src, dict):
            for k in ("last", "lastPrice", "ltr", "lastTrade"):
                if k in src:
                    return f(src[k], 0.0)
    return 0.0


# --- preview/place core --------------------------------------------------------
def _mk_min_order(
    symbol, action, qty, qty_type, price_type, order_term, limit_price, market_session
):
    o = {
        "orderTerm": order_term,
        "priceType": price_type,
        "Instrument": [
            {
                "Product": {"securityType": "EQ", "symbol": symbol},
                "orderAction": action,
                "quantityType": qty_type,
                "quantity": int(qty),
            }
        ],
    }
    if market_session:
        o["marketSession"] = market_session
    if price_type == "LIMIT":
        o["limitPrice"] = float(limit_price)
    return o


def _extract_core(prev: dict, qty_override: int | None):
    pr = (prev or {}).get("PreviewOrderResponse") or {}
    acct_num = str(pr.get("accountId") or "").strip()
    if not acct_num:
        # Some stacks omit top-level accountId; still usable for PreviewIds
        acct_num = ""
    orders = pr.get("Order") or []
    if not orders:
        raise RuntimeError("preview missing Order[]")
    o0 = orders[0]
    instrs = o0.get("Instrument") or []
    if not instrs:
        raise RuntimeError("preview missing Instrument[]")
    i0 = instrs[0]
    prod = i0.get("Product") or {}
    symbol = str(prod.get("symbol") or "").strip()
    if not symbol:
        raise RuntimeError("preview missing Product.symbol")

    qty = int(qty_override if qty_override is not None else i0.get("quantity") or 0)
    if qty <= 0:
        raise RuntimeError("invalid quantity for place")

    price_type = o0.get("priceType") or "MARKET"
    limit_price = o0.get("limitPrice") or None
    order_term = o0.get("orderTerm") or "GOOD_FOR_DAY"
    market_sess = o0.get("marketSession") or "REGULAR"
    qty_type = i0.get("quantityType") or "QUANTITY"
    action = i0.get("orderAction") or "SELL"
    sym_desc = i0.get("symbolDescription") or ""

    pid = pr.get("previewId")
    if not pid:
        pids = pr.get("PreviewIds") or pr.get("previewIds") or []
        if isinstance(pids, list) and pids and isinstance(pids[0], dict):
            pid = pids[0].get("previewId") or pids[0].get("id")
    if not pid:
        raise RuntimeError("previewId not found in preview")
    pid_int = int(pid)
    pid_str = str(pid_int)

    return (
        acct_num,
        symbol,
        action,
        qty,
        qty_type,
        price_type,
        limit_price,
        order_term,
        market_sess,
        sym_desc,
        pid_int,
        pid_str,
    )


def _fresh_preview(acct_key, sym, qty, price_type, limit_or_none):
    return et.preview_equity_order(
        acct_key,
        sym,
        qty,
        (limit_or_none if price_type == "LIMIT" else None),
        action="SELL",
        price_type=price_type,
        order_term="GOOD_FOR_DAY",
        market_session="REGULAR",
    )


def _place_variants(
    prev: dict,
    qty_override: int | None = None,
    force_price_type: str | None = None,
    force_limit: float | None = None,
):
    (
        acct_num,
        symbol,
        action,
        qty,
        qty_type,
        price_type,
        limit_price,
        order_term,
        market_sess,
        sym_desc,
        pid_int,
        pid_str,
    ) = _extract_core(prev, qty_override)

    if force_price_type:
        price_type = force_price_type
    if force_limit is not None:
        limit_price = force_limit

    coid = rand_id(prefix=f"{symbol.upper()}")

    base_no_sess = _mk_min_order(
        symbol,
        action,
        qty,
        qty_type,
        price_type,
        order_term,
        limit_price,
        market_session=None,
    )
    base_with_sess = _mk_min_order(
        symbol,
        action,
        qty,
        qty_type,
        price_type,
        order_term,
        limit_price,
        market_session=market_sess,
    )

    # A) marketSession at order level (common)
    yield (
        acct_num,
        {
            "PlaceOrderRequest": {
                "orderType": "EQ",
                "clientOrderId": coid,
                "PreviewIds": [{"previewId": pid_int}],
                "Order": [dict(base_with_sess)],
            }
        },
    )

    # B) marketSession at top level (alt)
    yield (
        acct_num,
        {
            "PlaceOrderRequest": {
                "orderType": "EQ",
                "clientOrderId": coid,
                "PreviewIds": [{"previewId": pid_int}],
                "marketSession": market_sess,
                "Order": [dict(base_no_sess)],
            }
        },
    )


def do_place_with_adaptive_variants(
    acct_key: str,
    sym: str,
    qty: int,
    price_type: str,
    limit_or_none: float | None,
    max_outer: int,
    debug: bool = False,
) -> bool:
    """
    Re-preview before each variant group to keep previewId ultra-fresh.
    Try accountIdKey path first; if 500/code100, we refresh and retry.
    If we have *numeric* acct from preview, we also try numeric path.
    """
    for outer in range(1, max_outer + 1):
        if debug:
            LOG.info("[DBG] outer attempt %d: refreshing preview", outer)
        prev = _fresh_preview(acct_key, sym, qty, price_type, limit_or_none)

        # Build variants (will also give us numeric accountId, if present)
        placed = False
        numeric_path = None
        for acct_num, body in _place_variants(
            prev,
            qty_override=qty,
            force_price_type=price_type,
            force_limit=limit_or_none,
        ):
            key_path = f"/accounts/{acct_key}/orders/place.json"
            if acct_num:
                numeric_path = f"/accounts/{acct_num}/orders/place.json"

            # Try key path
            try:
                if debug:
                    LOG.info("%s: POST %s\n%s", "market-orderlvl", key_path, j(body))
                resp = et._epost(key_path, body)
                LOG.info(
                    "%s SELL placed (%s) orderId=%s",
                    sym,
                    price_type,
                    (
                        ((resp or {}).get("PlaceOrderResponse") or {})
                        .get("OrderIds", [{}])[0]
                        .get("orderId")
                        if (resp or {}).get("PlaceOrderResponse")
                        else "?"
                    ),
                )
                return True
            except Exception as e:
                msg = str(e)
                if (" 500:" in msg) or ("'code': 100" in msg) or ('"code": 100' in msg):
                    LOG.warning(
                        "Transient venue error; will refresh preview then retry (outer=%d)",
                        outer,
                    )
                    break  # break variants; go outer refresh
                # try numeric if we have it and this wasn’t a venue error
                if numeric_path:
                    try:
                        if debug:
                            LOG.info(
                                "%s: POST %s\n%s",
                                "market-orderlvl",
                                numeric_path,
                                j(body),
                            )
                        resp = et._epost(numeric_path, body)
                        LOG.info(
                            "%s SELL placed (%s) orderId=%s",
                            sym,
                            price_type,
                            (
                                ((resp or {}).get("PlaceOrderResponse") or {})
                                .get("OrderIds", [{}])[0]
                                .get("orderId")
                                if (resp or {}).get("PlaceOrderResponse")
                                else "?"
                            ),
                        )
                        return True
                    except Exception as e2:
                        LOG.warning("numeric path failed: %s", e2)
                # if neither worked, continue to next variant (we only have 2 core variants)
        # small backoff between outer cycles
        time.sleep(0.8 * outer)

    return False


# --- eligibility & action ------------------------------------------------------
@dataclass
class GuardSettings:
    sell_window_start_et: str
    sell_window_end_et: str
    throttle_ms: int
    max_place_attempts: int
    market_fallback_for: list[str]
    use_extended_hours: bool
    normalize_tick: float
    sg: dict[str, Any]


def _glimpse(obj):
    try:
        if isinstance(obj, dict):
            return {"type": "dict", "keys": list(obj.keys())[:10]}
        if isinstance(obj, list):
            return {"type": "list", "len": len(obj)}
        return str(obj)[:160]
    except Exception:
        return "<glimpse-failed>"


def _parse_positions_any(arr):
    out = []
    if not isinstance(arr, list):
        return out
    for p in arr:
        if not isinstance(p, dict):
            continue
        sym = (
            p.get("symbolDescription")
            or (p.get("Product") or {}).get("symbol")
            or p.get("symbol")
            or ""
        )
        qty = (
            p.get("quantity")
            or p.get("longQuantity")
            or p.get("positionQty")
            or p.get("qty")
            or 0
        )
        # last price from any of the usual places
        q = p.get("Quick") or {}
        ins = p.get("Instrument") or {}
        allf = p.get("All") or {}
        last = (
            q.get("lastTrade")
            or ins.get("lastTrade")
            or allf.get("extendedHourLastTrade")
            or 0
        )
        entry = (
            p.get("pricePaid") or p.get("purchasePrice") or p.get("averagePrice") or 0
        )

        try:
            qty_f = float(qty or 0)
        except:
            qty_f = 0.0
        try:
            last_f = float(last or 0)
        except:
            last_f = 0.0
        try:
            entry_f = float(entry or 0)
        except:
            entry_f = 0.0

        sym = (sym or "").strip().upper()
        if sym and qty_f > 0:
            pl_pct = (
                ((last_f - entry_f) / entry_f * 100.0)
                if (last_f > 0 and entry_f > 0)
                else None
            )
            # return a 3-tuple so we don’t break callers
            out.append((sym, int(qty_f), pl_pct))
    return out


def eligible_symbols(acct_key: str, cfg: GuardSettings) -> List[Tuple[str, int]]:
    block = set(map(str.upper, cfg.sg.get("blocklist") or []))
    force = set(map(str.upper, cfg.sg.get("force_symbols") or []))
    fwe   = bool(cfg.sg.get("force_without_entry", True))

    # ---- fetch positions (with/without acct_key) ----
    pos = None; err = None
    try:
        pos = et.get_positions(acct_key)
    except TypeError:
        try:
            pos = et.get_positions()
        except Exception as e:
            err = e
    except Exception as e:
        err = e

    if err:
        LOG.warning("get_positions failed: %s", err)
        return sorted([(s, 0) for s in force]) if (force and fwe) else []

    LOG.info("positions raw glimpse: %s", _glimpse(pos))

    def L(x):
        return x if isinstance(x, list) else ([] if x is None else [x])

    # ---- normalize to iterable of (symbol, qty_float) from Product/quantity ----
    def _iter_positions(pobj):
        if not isinstance(pobj, dict):
            return
        pr = pobj.get("PortfolioResponse") or {}
        for ap in L(pr.get("AccountPortfolio")):
            positions = (ap.get("Position") or ap.get("position")
                         or ap.get("Positions") or ap.get("positions"))
            for p in L(positions):
                prod = p.get("Product") or p.get("product") or {}
                sym  = (prod.get("symbol") or "").strip().upper()
                if not sym:
                    # fallback: description like "NAME (TICKER)"
                    desc = (p.get("symbolDescription") or "").strip()
                    if "(" in desc and desc.endswith(")"):
                        tick = desc.split("(")[-1][:-1].strip()
                        if tick:
                            sym = tick.upper()

                qty = (
                    p.get("quantity") or p.get("qty")
                    or p.get("longQty") or p.get("longQuantity")
                    or p.get("positionQty") or p.get("positionQuantity") or 0
                )
                try:
                    q = float(qty or 0)
                except Exception:
                    q = 0.0

                if sym and q > 0:
                    yield sym, q

    rows = list(_iter_positions(pos))
    LOG.info("normalized positions -> %s", rows)

    # ---- apply blocklist/force, dedupe, then floor to whole shares for selling ----
    merged: Dict[str, float] = {}

    if fwe and force:
        for s in sorted(force):
            if s not in block:
                merged[s] = 0.0

    for sym, q in rows:
        if sym in block:
            continue
        merged[sym] = max(float(q), merged.get(sym, 0.0))

    final: List[Tuple[str, int]] = []
    skipped_fractional = {}

    for s, q in sorted(merged.items()):
        whole = int(q)  # sell API needs whole shares
        if whole >= 1 or (fwe and s in force):
            final.append((s, whole))
        else:
            skipped_fractional[s] = q

    if skipped_fractional:
        LOG.info("eligible_symbols: skipped fractional-only holdings (whole=0): %s", skipped_fractional)

    LOG.info("eligible final -> %s", final)
    return final

def compute_order_params(
    symbol: str, cfg: GuardSettings
) -> tuple[str, float | None]:
    """
    Decide MARKET vs LIMIT and price.
    By default we do MARKET. If limit_from='bid', set limit at (bid - tick) to make it marketable.
    """
    pt = "MARKET"
    limit = None

    limit_from = (cfg.sg.get("limit_from") or "").lower()
    tick = float(cfg.sg.get("normalize_tick") or cfg.normalize_tick or 0.01) or 0.01
    offset_bps = int(cfg.sg.get("limit_offset_bps") or 0)

    if limit_from in ("bid", "last"):
        ref = best_bid(symbol) if limit_from == "bid" else last_trade(symbol)
        if ref > 0:
            if offset_bps and offset_bps != 0:
                # offset in basis points -> for SELL, price down slightly to cross
                limit = max(0.01, round(ref * (1 - offset_bps / 10_000.0), 2))
            else:
                limit = max(0.01, round(ref - tick, 2))
            pt = "LIMIT"
    return pt, limit


# --- main loop ----------------------------------------------------------------
def main():
    cfg_raw = load_settings()
    LOG.info("sell_guard starting…")
    LOG.info("Settings: %s", j(cfg_raw))

    acct_key = get_acct_key()
    LOG.info("heartbeat: loop alive (account=%s)", acct_key)

    # Lift to dataclass for convenience
    cfg = GuardSettings(
        sell_window_start_et=cfg_raw.get("sell_window_start_et")
        or cfg_raw["sell_guard"].get("sell_window_start_et")
        or "09:35",
        sell_window_end_et=cfg_raw.get("sell_window_end_et")
        or cfg_raw["sell_guard"].get("sell_window_end_et")
        or "15:55",
        throttle_ms=int(cfg_raw.get("throttle_ms") or 30_000),
        max_place_attempts=int(
            cfg_raw.get("max_place_attempts")
            or cfg_raw["sell_guard"].get("max_place_attempts")
            or 4
        ),
        market_fallback_for=list(
            cfg_raw.get("market_fallback_for")
            or cfg_raw["sell_guard"].get("market_fallback_for")
            or []
        ),
        use_extended_hours=bool(
            cfg_raw.get("use_extended_hours")
            or cfg_raw["sell_guard"].get("use_extended_hours")
            or False
        ),
        normalize_tick=float(
            cfg_raw.get("normalize_tick")
            or cfg_raw["sell_guard"].get("normalize_tick")
            or 0.01
        ),
        sg=cfg_raw["sell_guard"],
    )

    last_placed: set[str] = set()
    heartbeat_next = time.time()
    throttle = max(1, int(cfg.throttle_ms / 1000))

    while True:
        tnow = time.time()
        if tnow >= heartbeat_next:
            LOG.info("heartbeat: loop alive (account=%s)", acct_key)
            heartbeat_next = tnow + 30

        # Window check (ET)
        try:
            etnow = now_et()
            start_h, start_m = map(int, cfg.sell_window_start_et.split(":"))
            end_h, end_m = map(int, cfg.sell_window_end_et.split(":"))
            window_on = ((etnow.hour, etnow.minute) >= (start_h, start_m)) and (
                (etnow.hour, etnow.minute) <= (end_h, end_m)
            )
        except Exception:
            window_on = True

        if not window_on and not cfg.use_extended_hours:
            LOG.info("outside sell window; sleeping %ds", throttle)
            time.sleep(throttle)
            continue

        LOG.info("positions scan…")
        rows = force_probe_candidates(acct_key, cfg)

        if not rows:
            try:
                rows = eligible_symbols(acct_key, cfg)
            except Exception as e:
                LOG.error("eligible_symbols failed: %s", e)
                rows = []
        # Build a quick symbol -> position row map (for entry price)
        try:
            _pos_obj = et.get_positions(acct_key)
        except TypeError:
            _pos_obj = et.get_positions()
        _pos_rows = _normalize_positions(_pos_obj)
        _pos_map = {r["symbol"]: r for r in _pos_rows}

        LOG.info(
            "candidates: %s",
            ",".join(f"{s}x{q}" for s, q in rows) if rows else "(none)",
        )

        placed_any = False
        last_placed.clear()

        # Cache today's transactions ONCE per scan cycle
        _tx_today, _buy_today_set, _last_buy_ms_map = _cache_today_transactions()

        for s, have_qty in rows:
            if s in last_placed:
                continue

            avail = int(round(available_to_sell(acct_key, s)))
            if avail <= 0:
                LOG.info("%s: no available shares to sell", s)
                continue

            # ---- HOLD & PDT GATES (single source of truth) ----
            sg = cfg.sg
            min_hold_min   = int(sg.get("min_hold_minutes") or 0)
            min_hold_days  = int(sg.get("min_hold_days") or 0)
            avoid_dt       = bool(sg.get("avoid_daytrades", False))
            intraday_stops = bool(sg.get("allow_intraday_stoploss", False))

            # Simple PDT rule while testing: block all same-day exits if avoid_daytrades
            if avoid_dt and _opened_today_cached(s, _buy_today_set):
                LOG.info("[HOLD] %s opened today; avoid_daytrades on -> skip", s)
                continue

            # Minute hold buffer (only if we can detect a buy timestamp)
            if min_hold_min > 0:
                mins = _minutes_since_last_buy_cached(s, _last_buy_ms_map)
                if mins is not None and mins < min_hold_min:
                    LOG.info("[HOLD] %s held %.1f < %d min -> skip", s, mins, min_hold_min)
                    continue

            # Optional day hold: conservative same-day skip
            if min_hold_days > 0 and _opened_today_cached(s, _buy_today_set):
                LOG.info("[HOLD] %s same-day; min_hold_days=%d -> skip", s, min_hold_days)
                continue

            # (Optional) Add price-based exits here later:
            # if not _should_exit_by_price(s):
            #     LOG.info("[PRICE] %s not at stop/target -> skip", s)
            #     continue
            # ---- 2a: Post-N-minute protection window with laddered trailing ----
            entry_px = _entry_price_from_positions(_pos_map, s)
            last_px  = last_trade(s)  # robust getter you retained
            now_ts   = time.time()
            mins_since_buy = _minutes_since_last_buy_cached(s, _last_buy_ms_map)
            opened_ts = (now_ts - mins_since_buy * 60.0) if (mins_since_buy is not None) else None

            if entry_px and last_px and opened_ts:
                decision = _apply_sell_protection(
                    sym=s,
                    entry_px=entry_px,
                    last_px=last_px,
                    opened_ts=opened_ts,
                    now_ts=now_ts,
                    cfg=cfg.sg,
                )
                if decision is None:
                    LOG.info("[PROTECT] %s hold (no trigger); gain%% vs entry not at stop/trail", s)
                    continue
                LOG.info("[PROTECT] %s -> %s (%s)", s, decision.get("action"), decision.get("reason"))
            # If entry or opened time is unknown, fall through to normal exits (your other gates)

            pt, limit_px = compute_order_params(s, cfg)
            from services.live_guardrails import record_entry

            LOG.info(
                "[SG] %s -> free=%d -> place %s%s",
                s,
                avail,
                pt,
                f" {limit_px:.2f}" if (pt == "LIMIT" and limit_px) else "",
            )

            ok = do_place_with_adaptive_variants(
                acct_key=acct_key,
                sym=s,
                qty=avail,
                price_type=pt,
                limit_or_none=limit_px if pt == "LIMIT" else None,
                max_outer=cfg.max_place_attempts,
                debug=False,
            )
            if ok:
                placed_any = True
                last_placed.add(s)
            else:
                LOG.error("%s SELL failed (all variants)", s)

        LOG.info("sleeping %ds", throttle)
        time.sleep(throttle)


if __name__ == "__main__":
    main()
