# sell_guard.py  — LIVE sell guard with hold/ladder rules (Ben 2025-11-03)
from __future__ import annotations

import json, logging, os, sys, time, random, string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Tuple

try:
    from zoneinfo import ZoneInfo
    ETZ = ZoneInfo("America/New_York")
except Exception:
    ETZ = None

LOG = logging.getLogger("sell-guard")
LOG.setLevel(logging.INFO)
for h in list(LOG.handlers): LOG.removeHandler(h)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(asctime)s,%(msecs)03d %(levelname)s sell-guard: %(message)s",
                                   datefmt="%Y-%m-%d %H:%M:%S"))
LOG.addHandler(_sh)

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)

from services import etrade_service as et  # your wrapper
from services import live_guardrails as gr  # we’ll read opened_at

def j(x): 
    try: return json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception: return str(x)

def f(x, d=0.0):
    try: return float(x)
    except Exception: return d

def now_et():
    if ETZ: return datetime.now(ETZ)
    return datetime.now(UTC)

def rand_id(prefix: str, n: int = 6) -> str:
    return f"{prefix}{''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(n))}"

DEFAULTS = {
  "mode": "live",
  "normalize_tick": 0.01,
  "sell_window_start_et": "09:35",
  "sell_window_end_et": "15:55",
  "throttle_ms": 30_000,
  "use_extended_hours": False,
  "market_fallback_for": ["SELL_STOP","TIMEOUT"],
  "max_place_attempts": 4,
  "sell_guard": {
    "allow_intraday_stoploss": True,
    "avoid_daytrades": True,
    "blocklist": [],
    "force_symbols": [],
    "force_without_entry": False,
    "limit_from": "bid",
    "limit_offset_bps": 0,
    "max_hold_mins": 1_000_000,
    "min_hold_days": 1,
    "min_hold_minutes": 390,
    "normalize_tick": 0.01,
    "sell_protect_after_mins": None,
    "sell_window_start_et": "09:35",
    "sell_window_end_et": "15:55",
    "stop_bps": 100,
    "target_bps": 200,
    "use_extended_hours": False,
    "circuit_fail_threshold": 2,
    "circuit_open_seconds": 480,
    "max_place_attempts": 4
  }
}

def load_settings() -> Dict[str, Any]:
    path = os.environ.get("SELL_GUARD_SETTINGS") or os.path.join(HERE, "sell_guard_settings.json")
    LOG.info("Using SELL_GUARD_SETTINGS=%s", path)
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except FileNotFoundError:
        user = {}
    # merge but prefer NESTED values
    merged = dict(DEFAULTS)
    merged["sell_guard"] = dict(DEFAULTS["sell_guard"])
    # bring user top-level keys (rare)
    for k, v in user.items():
        if k != "sell_guard":
            merged[k] = v
    # bring nested last (so nested wins)
    if "sell_guard" in user and isinstance(user["sell_guard"], dict):
        merged["sell_guard"].update(user["sell_guard"])
    return merged

# ----- quotes / account helpers ------------------------------------------------
def get_acct_key() -> str:
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k: return str(k)
        except Exception: pass
    if hasattr(et, "account_id_key") and et.account_id_key:
        return str(et.account_id_key)
    raise RuntimeError("Could not determine account_id_key")

def preview(acct_key, sym, qty, price_type, limit_or_none):
    return et.preview_equity_order(
        acct_key, sym, qty,
        (limit_or_none if price_type == "LIMIT" else None),
        action="SELL", price_type=price_type,
        order_term="GOOD_FOR_DAY", market_session="REGULAR",
    )

def _mk_min_order(symbol, action, qty, qty_type, price_type, order_term, limit_price, market_session):
    o = {
        "orderTerm": order_term,
        "priceType": price_type,
        "Instrument": [{
            "Product": {"securityType": "EQ", "symbol": symbol},
            "orderAction": action,
            "quantityType": qty_type,
            "quantity": int(qty),
        }],
    }
    if market_session: o["marketSession"] = market_session
    if price_type == "LIMIT": o["limitPrice"] = float(limit_price)
    return o

def _extract_core(prev: dict, qty_override: int | None):
    pr = (prev or {}).get("PreviewOrderResponse") or {}
    acct_num = str(pr.get("accountId") or "").strip()
    orders = pr.get("Order") or []
    if not orders: raise RuntimeError("preview missing Order[]")
    o0 = orders[0]
    i0 = (o0.get("Instrument") or [{}])[0]
    sym = (i0.get("Product") or {}).get("symbol") or ""
    qty = int(qty_override if qty_override is not None else i0.get("quantity") or 0)
    price_type = o0.get("priceType") or "MARKET"
    limit_price = o0.get("limitPrice")
    order_term = o0.get("orderTerm") or "GOOD_FOR_DAY"
    market_sess = o0.get("marketSession") or "REGULAR"
    qty_type = i0.get("quantityType") or "QUANTITY"
    pid = pr.get("previewId") or ((pr.get("PreviewIds") or [{}])[0].get("previewId"))
    if not pid: raise RuntimeError("previewId not found")
    return acct_num, sym, "SELL", qty, qty_type, price_type, limit_price, order_term, market_sess, int(pid)

def _place_variants(prev: dict, qty_override=None, force_price_type=None, force_limit=None):
    acct_num, sym, action, qty, qty_type, price_type, limit_price, order_term, market_sess, pid = _extract_core(prev, qty_override)
    if force_price_type: price_type = force_price_type
    if force_limit is not None: limit_price = force_limit
    coid = rand_id(prefix=f"{sym.upper()}")
    base_no_sess = _mk_min_order(sym, action, qty, qty_type, price_type, order_term, limit_price, None)
    base_with_sess = _mk_min_order(sym, action, qty, qty_type, price_type, order_term, limit_price, market_sess)

    yield acct_num, { "PlaceOrderRequest": { "orderType":"EQ", "clientOrderId":coid,
            "PreviewIds":[{"previewId":pid}], "Order":[dict(base_with_sess)] } }
    yield acct_num, { "PlaceOrderRequest": { "orderType":"EQ", "clientOrderId":coid,
            "PreviewIds":[{"previewId":pid}], "marketSession":market_sess, "Order":[dict(base_no_sess)] } }

def _epost(path, body):
    return et._epost(path, body)

def place_with_adaptive_variants(acct_key, sym, qty, price_type, limit_or_none, max_outer, debug=False) -> bool:
    for outer in range(1, max_outer+1):
        prev = preview(acct_key, sym, qty, price_type, limit_or_none)
        numeric_path = None
        for acct_num, body in _place_variants(prev, qty_override=qty, force_price_type=price_type, force_limit=limit_or_none):
            key_path = f"/accounts/{acct_key}/orders/place.json"
            if acct_num: numeric_path = f"/accounts/{acct_num}/orders/place.json"
            try:
                _epost(key_path, body)
                LOG.info("%s SELL placed (%s)", sym, price_type)
                return True
            except Exception as e:
                msg = str(e)
                if (" 500:" in msg) or ('"code": 100' in msg) or ("'code': 100" in msg):
                    LOG.warning("Transient venue error; refreshing preview (outer=%d)", outer)
                    break
                if numeric_path:
                    try:
                        _epost(numeric_path, body); LOG.info("%s SELL placed (%s)", sym, price_type); return True
                    except Exception as e2:
                        LOG.warning("numeric path failed: %s", e2)
        time.sleep(0.8 * outer)
    return False

# ----- position + P/L info ----------------------------------------------------
def _glimpse(obj):
    try:
        if isinstance(obj, dict): return {"type":"dict","keys":list(obj.keys())[:10]}
        if isinstance(obj, list): return {"type":"list","len":len(obj)}
        return str(obj)[:120]
    except Exception: return "<glimpse-failed>"

def get_positions_any(acct_key=None):
    try: return et.get_positions(acct_key)
    except TypeError:
        try: return et.get_positions()
        except Exception as e: raise e

def iter_positions(pobj):
    """Yield (sym, qty_float, last, entry) from any of the usual E*TRADE shapes."""
    def L(x): return x if isinstance(x, list) else ([] if x is None else [x])
    if not isinstance(pobj, dict): return
    pr = pobj.get("PortfolioResponse") or {}
    for ap in L(pr.get("AccountPortfolio")):
        positions = ap.get("Position") or ap.get("position") or ap.get("Positions") or ap.get("positions")
        for p in L(positions):
            prod = p.get("Product") or p.get("product") or {}
            sym = (prod.get("symbol") or "").strip().upper()
            if not sym:
                desc = (p.get("symbolDescription") or "").strip()
                if "(" in desc and desc.endswith(")"):
                    sym = desc.split("(")[-1][:-1].strip().upper()
            qty = f(p.get("quantity") or p.get("qty") or p.get("longQuantity") or p.get("positionQty") or 0, 0.0)
            q = p.get("Quick") or {}; ins = p.get("Instrument") or {}; allf = p.get("All") or {}
            last = f(q.get("lastTrade") or ins.get("lastTrade") or allf.get("extendedHourLastTrade") or 0, 0.0)
            entry = f(p.get("pricePaid") or p.get("purchasePrice") or p.get("averagePrice") or 0, 0.0)
            if sym and qty > 0: yield sym, qty, last, entry

def opened_today(sym: str) -> bool:
    """BUY today? (PDT)"""
    try:
        for t in et.get_transactions(start="today", end="today") or []:
            tsym = (t.get("symbol") or t.get("securitySymbol") or "").strip().upper()
            side = (t.get("transactionType") or t.get("side") or "").upper()
            if tsym == sym.upper() and "BUY" in side: return True
    except Exception: pass
    return False

# ----- compute price type ------------------------------------------------------
def best_bid(symbol: str) -> float:
    try:
        q = et.fetch_etrade_quote(symbol) or {}
    except Exception:
        q = et.get_quote(symbol) or {}
    if isinstance(q, dict):
        for src in (q, q.get("All") or {}, (q.get("QuoteResponse") or {}).get("QuoteData") or {}):
            if isinstance(src, list): src = (src[0] if src else {})
            if isinstance(src, dict):
                for k in ("bid","bidPrice","bestBid"):
                    if k in src: return f(src[k], 0.0)
    return 0.0

def last_trade(symbol: str) -> float:
    try:
        q = et.fetch_etrade_quote(symbol) or {}
    except Exception:
        q = et.get_quote(symbol) or {}
    if isinstance(q, dict):
        for src in (q, q.get("All") or {}, (q.get("QuoteResponse") or {}).get("QuoteData") or {}):
            if isinstance(src, list): src = (src[0] if src else {})
            if isinstance(src, dict):
                for k in ("last","lastPrice","ltr","lastTrade"):
                    if k in src: return f(src[k], 0.0)
    return 0.0

def compute_order_params(symbol: str, cfg) -> Tuple[str, float|None]:
    pt, limit_px = "MARKET", None
    limit_from = (cfg.sg.get("limit_from") or "").lower()
    tick = float(cfg.sg.get("normalize_tick") or cfg.normalize_tick or 0.01) or 0.01
    offset_bps = int(cfg.sg.get("limit_offset_bps") or 0)
    if limit_from in ("bid","last"):
        ref = best_bid(symbol) if limit_from == "bid" else last_trade(symbol)
        if ref > 0:
            limit_px = max(0.01, round(ref * (1 - offset_bps/10_000.0), 2)) if offset_bps else max(0.01, round(ref - tick, 2))
            pt = "LIMIT"
    return pt, limit_px

# ----- config shape ------------------------------------------------------------
@dataclass
class GuardSettings:
    sell_window_start_et: str
    sell_window_end_et: str
    throttle_ms: int
    max_place_attempts: int
    market_fallback_for: List[str]
    use_extended_hours: bool
    normalize_tick: float
    sg: Dict[str, Any]

# trailing state (in-process). If you want persistence, wire sqlite/json.
TRAIL: Dict[str, Dict[str, float]] = {}  # sym -> {"hi": high_pl_pct, "trail_pct": float}

def main():
    cfg_raw = load_settings()
    LOG.info("sell_guard starting…")
    LOG.info("Settings: %s", j(cfg_raw))

    # Prefer NESTED (sell_guard.*) values first, then fallback to top-level
    sg = cfg_raw["sell_guard"]
    cfg = GuardSettings(
        sell_window_start_et = sg.get("sell_window_start_et") or cfg_raw.get("sell_window_start_et") or "09:35",
        sell_window_end_et   = sg.get("sell_window_end_et")   or cfg_raw.get("sell_window_end_et")   or "15:55",
        throttle_ms          = int( sg.get("throttle_ms", cfg_raw.get("throttle_ms", 30_000)) ),
        max_place_attempts   = int( sg.get("max_place_attempts", cfg_raw.get("max_place_attempts", 4)) ),
        market_fallback_for  = list(sg.get("market_fallback_for") or cfg_raw.get("market_fallback_for") or []),
        use_extended_hours   = bool(sg.get("use_extended_hours", cfg_raw.get("use_extended_hours", False))),
        normalize_tick       = float(sg.get("normalize_tick", cfg_raw.get("normalize_tick", 0.01))),
        sg=sg
    )

    acct_key = get_acct_key()
    LOG.info("heartbeat: loop alive (account=%s)", acct_key)

    gr.init_table()  # ensure table exists
    heartbeat_next = time.time()
    throttle = max(1, int(cfg.throttle_ms / 1000))

    def inside_window():
        try:
            etnow = now_et()
            sh, sm = map(int, cfg.sell_window_start_et.split(":"))
            eh, em = map(int, cfg.sell_window_end_et.split(":"))
            on = ((etnow.hour, etnow.minute) >= (sh, sm)) and ((etnow.hour, etnow.minute) <= (eh, em))
            return on or cfg.use_extended_hours
        except Exception:
            return True

    while True:
        tnow = time.time()
        if tnow >= heartbeat_next:
            LOG.info("heartbeat: loop alive (account=%s)", acct_key)
            heartbeat_next = tnow + 30

        if not inside_window():
            LOG.info("outside sell window; sleeping %ds", throttle)
            time.sleep(throttle); continue

        # build entry/opened_at map from guardrails
        open_map: Dict[str, datetime] = {}
        for e in gr.list_open_entries():
            try:
                dt = datetime.fromisoformat(e["opened_at"])
            except Exception:
                continue
            open_map[(e["symbol"] or "").upper()] = dt

        # positions → candidates with pl% + hold minutes
        try:
            pos = get_positions_any(acct_key)
        except Exception as e:
            LOG.warning("get_positions failed: %s", e); time.sleep(throttle); continue

        LOG.info("positions raw glimpse: %s", _glimpse(pos))
        rows: List[Tuple[str,int,float,float]] = list(iter_positions(pos))  # sym, qty, last, entry

        # apply blocklist and “force_without_entry”
        block = set(map(str.upper, cfg.sg.get("blocklist") or []))
        fwe   = bool(cfg.sg.get("force_without_entry", False))

        candidates: List[Tuple[str,int,float,float, float]] = []
        for sym, q, last, entry in rows:
            if sym in block: continue
            if not fwe and sym not in open_map:  # no recorded opened_at → skip unless allowed
                continue
            if q < 1: continue
            pl_pct = ((last - entry) / entry * 100.0) if (last > 0 and entry > 0) else 0.0
            hold_min = None
            if sym in open_map:
                try:
                    hold_min = max(0.0, (now_et() - open_map[sym].replace(tzinfo=None)).total_seconds()/60.0)
                except Exception:
                    hold_min = None
            candidates.append((sym, int(q), pl_pct, hold_min if hold_min is not None else -1.0, entry))

        LOG.info("eligible final -> %s", [(s,q) for s,q,_,_,_ in candidates])
        if not candidates:
            LOG.info("candidates: (none)")
            LOG.info("sleeping %ds", throttle); time.sleep(throttle); continue
        LOG.info("candidates: %s", ",".join(f"{s}x{q}" for s,q,_,_,_ in candidates))

        # thresholds
        stop_pct   = abs(float(cfg.sg.get("stop_bps", 100))) / 100.0
        target_pct = abs(float(cfg.sg.get("target_bps", 200))) / 100.0
        min_hold   = float(cfg.sg.get("min_hold_minutes", 0))
        max_hold   = float(cfg.sg.get("max_hold_mins", 1_000_000))
        protect_after = cfg.sg.get("sell_protect_after_mins")
        protect_after = float(protect_after) if protect_after is not None else None
        allow_intraday_stop = bool(cfg.sg.get("allow_intraday_stoploss", True))
        avoid_daytrades = bool(cfg.sg.get("avoid_daytrades", False))

        for s, qty, pl_pct, hold_min, entry_px in candidates:
            # PDT guard (optional)
            if avoid_daytrades and opened_today(s):
                LOG.info("[PDT] Skipping %s (opened today; avoid_daytrades on)", s); continue

            # STOP: allow intraday stoploss regardless of min hold
            if allow_intraday_stop and pl_pct <= -stop_pct:
                pt, lim = compute_order_params(s, cfg)
                LOG.info("[SG] %s STOP %.2f%% ≤ -%.2f%% → place %s%s", s, pl_pct, stop_pct, pt, f" {lim:.2f}" if lim else "")
                ok = place_with_adaptive_variants(acct_key, s, qty, pt, (lim if pt=="LIMIT" else None), cfg.max_place_attempts)
                if ok: LOG.info("sleeping %ds", throttle)
                continue

            # HOLD until min_hold_minutes (unless max_hold reached)
            if hold_min >= 0 and hold_min < min_hold:
                LOG.info("[HOLD] %s hold %.1f mins < %.1f mins (min_hold); no action", s, hold_min, min_hold)
                continue

            # Max hold → exit
            if hold_min >= max_hold:
                pt, lim = compute_order_params(s, cfg)
                LOG.info("[TIMEOUT] %s hold %.1f mins ≥ %.1f mins → place %s%s", s, hold_min, max_hold, pt, f" {lim:.2f}" if lim else "")
                place_with_adaptive_variants(acct_key, s, qty, pt, (lim if pt=="LIMIT" else None), cfg.max_place_attempts)
                continue

            # Ladder / trailing emulation
            now_gain = pl_pct
            hi = TRAIL.get(s, {}).get("hi", now_gain)
            hi = max(hi, now_gain)
            TRAIL.setdefault(s, {})["hi"] = hi

            armed = (protect_after is not None and hold_min >= protect_after and hi >= target_pct)
            if armed and "trail_pct" not in TRAIL[s]:
                # Arm a simple trail at half the target (e.g., target 2% -> trail 1%)
                TRAIL[s]["trail_pct"] = max(0.5, target_pct/2.0)

            if armed:
                trail = TRAIL[s]["trail_pct"]
                if now_gain <= (hi - trail):
                    pt, lim = compute_order_params(s, cfg)
                    LOG.info("[TRAIL] %s gain %.2f%% fell from hi %.2f%% by ≥ %.2f%% → place %s%s",
                             s, now_gain, hi, trail, pt, f" {lim:.2f}" if lim else "")
                    place_with_adaptive_variants(acct_key, s, qty, pt, (lim if pt=="LIMIT" else None), cfg.max_place_attempts)
                    continue
                else:
                    LOG.info("[ARMED] %s hi=%.2f%% gain=%.2f%% trail=%.2f%% (holding)", s, hi, now_gain, TRAIL[s]["trail_pct"])
                    continue

            # Not armed yet and not a stop → hold
            LOG.info("[HOLD] %s gain=%.2f%% hold=%.1f mins (waiting for protect/target/timeout)", s, now_gain, hold_min)

        LOG.info("sleeping %ds", throttle)
        time.sleep(throttle)

if __name__ == "__main__":
    main()
