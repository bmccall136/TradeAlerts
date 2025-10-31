
import os
import sys
import time
import json
import logging
from typing import Any, Dict, List, Tuple, Optional

# --- Logging setup -----------------------------------------------------------
LOG = logging.getLogger("sell-guard")
LOG.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
LOG.addHandler(_handler)

# --- Settings ---------------------------------------------------------------
DEFAULT_SETTINGS_PATH = r"C:\TradeAlerts\sell_guard_settings.json"

def load_settings() -> Dict[str, Any]:
    # Env override (the launcher prints Using SELL_GUARD_SETTINGS=...)
    path = os.environ.get("SELL_GUARD_SETTINGS", DEFAULT_SETTINGS_PATH)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        LOG.warning("Settings file not found at %s; using defaults", path)
        cfg = {}
    # Accept either top-level or nested under 'sell_guard'
    sg = cfg.get("sell_guard", cfg)
    # Minimal defaults consistent with user's preferences
    return {
        "sell_guard": {
            "mode": sg.get("mode", "live"),
            "use_extended_hours": bool(sg.get("use_extended_hours", True)),
            "sell_window_start_et": sg.get("sell_window_start_et", "04:00"),
            "sell_window_end_et": sg.get("sell_window_end_et", "20:00"),
            "sell_protect_after_mins": int(sg.get("sell_protect_after_mins", 60)),
            "protect_min_gain_pct": float(sg.get("protect_min_gain_pct", 1.5)),
            "protect_trail_arm_pct": float(sg.get("protect_trail_arm_pct", 3.0)),
            "protect_trail_pct": float(sg.get("protect_trail_pct", 3.0)),
            "avoid_daytrades": bool(sg.get("avoid_daytrades", False)),
            "min_hold_days": int(sg.get("min_hold_days", 0)),
            "min_hold_minutes": int(sg.get("min_hold_minutes", 0)),
            "allow_intraday_stoploss": bool(sg.get("allow_intraday_stoploss", True)),
            "pdt_allow_stop": bool(sg.get("pdt_allow_stop", True)),
            "target_bps": int(sg.get("target_bps", 200)),
            "stop_bps": int(sg.get("stop_bps", 100)),
            "max_hold_mins": int(sg.get("max_hold_mins", 100000)),
            "limit_from": sg.get("limit_from", "bid"),
            "limit_offset_bps": int(sg.get("limit_offset_bps", 0)),
            "throttle_ms": int(sg.get("throttle_ms", 30000)),
            "blocklist": list(sg.get("blocklist", [])),
            "market_fallback_for": list(sg.get("market_fallback_for", ["SELL_STOP"])),
            "circuit_open_seconds": int(sg.get("circuit_open_seconds", 480)),
            "max_place_attempts": int(sg.get("max_place_attempts", 4)),
            "normalize_tick": float(sg.get("normalize_tick", 0.01)),
            "force_symbols": list(sg.get("force_symbols", [])),
            "circuit_fail_threshold": int(sg.get("circuit_fail_threshold", 2)),
            "force_without_entry": bool(sg.get("force_without_entry", False)),
        }
    }

# --- E*TRADE adapters (robust shape handling) --------------------------------
def _glimpse(obj: Any, maxlen: int = 300) -> str:
    try:
        s = json.dumps(obj) if not isinstance(obj, str) else obj
    except Exception:
        s = str(obj)
    return (s[:maxlen] + "…") if len(s) > maxlen else s

def _iter_positions_tree(pos: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize E*TRADE positions response to a flat list of dicts with keys:
    symbol, qty, pricePaid, dateAcquired, accountId
    Supports various 'PortfolioResponse' / 'AccountPortfolio' / 'Position' shapes.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(pos, dict):
        return out
    root = pos.get("PortfolioResponse") or pos
    acct_list = root.get("AccountPortfolio") if isinstance(root, dict) else None
    if acct_list is None:
        acct_list = root if isinstance(root, list) else []

    if not isinstance(acct_list, list):
        acct_list = [acct_list]

    for ap in acct_list:
        if not isinstance(ap, dict):
            continue
        account_id = ap.get("accountId") or ap.get("accountid") or ap.get("accountID")
        positions = ap.get("Position") or ap.get("position") or []
        if isinstance(positions, dict):
            positions = [positions]
        for pr in positions or []:
            try:
                sym = pr.get("symbolDescription") or pr.get("symbol") or pr.get("productId") or ""
                qty = pr.get("quantity") or pr.get("qty") or 0
                price_paid = pr.get("pricePaid") or pr.get("avgPrice") or pr.get("averagePrice") or None
                acquired = pr.get("dateAcquired") or pr.get("openedDate") or None
                out.append({
                    "symbol": str(sym).strip().upper(),
                    "qty": float(qty) if qty is not None else 0.0,
                    "pricePaid": float(price_paid) if price_paid is not None else None,
                    "dateAcquired": acquired,
                    "accountId": account_id,
                })
            except Exception as e:
                LOG.warning("skip malformed position: %s (%s)", _glimpse(pr), e)
    return out

def _extract_last_px_from_quote(qd: Dict[str, Any]) -> Optional[float]:
    """
    Handle various E*TRADE quote shapes to get the last trade price.
    """
    if not isinstance(qd, dict):
        return None

    # Common known nests
    q = qd.get("QuoteResponse") or qd.get("quoteResponse") or qd
    data = q.get("QuoteData") or q.get("quoteData") or q.get("data") or q

    # If data is a list, try the first
    if isinstance(data, list) and data:
        data = data[0]

    # Some shapes have "All", some "Intraday", "Product"
    for path in [
        ("All", "lastTrade"),
        ("all", "lastTrade"),
        ("All", "last"),
        ("Intraday", "lastTrade"),
        ("intraday", "lastTrade"),
        ("All", "adjustedFlag"),  # not a price, but keeps traversal safe
    ]:
        node = data.get(path[0]) if isinstance(data, dict) else None
        if isinstance(node, dict):
            val = node.get(path[1])
            if isinstance(val, (int, float)):
                return float(val)

    # Direct candidates on data
    for k in ("lastTrade", "last", "close", "previousClose", "lastPrice"):
        val = data.get(k) if isinstance(data, dict) else None
        if isinstance(val, (int, float)):
            return float(val)

    # Sometimes nested in 'quote' field or 'details'
    quote = data.get("quote") if isinstance(data, dict) else None
    if isinstance(quote, dict):
        for k in ("lastTrade", "last", "lastPrice"):
            val = quote.get(k)
            if isinstance(val, (int, float)):
                return float(val)

    return None

# --- External dependency (import only when used to keep script import-safe) --
def get_positions_dict() -> Dict[str, Any]:
    try:
        from services import etrade_service as et  # type: ignore
    except Exception as e:
        LOG.error("could not import etrade_service: %s", e)
        return {}
    try:
        # Prefer account key if env provided; else rely on etrade_service default
        acct_key = os.environ.get("ETRADE_ACCOUNT_KEY") or None
        if acct_key:
            return et.get_positions(acct_key)  # type: ignore
        return et.get_positions()  # type: ignore
    except TypeError:
        # Fallback for older signature
        try:
            return et.get_positions()  # type: ignore
        except Exception as e:
            LOG.error("get_positions failed: %s", e)
            return {}
    except Exception as e:
        LOG.error("get_positions failed: %s", e)
        return {}

def get_last_price(symbol: str) -> Optional[float]:
    try:
        from services import etrade_service as et  # type: ignore
    except Exception as e:
        LOG.error("could not import etrade_service: %s", e)
        return None
    try:
        qd = et.get_quote(symbol)  # type: ignore
        px = _extract_last_px_from_quote(qd)
        return px
    except Exception as e:
        LOG.warning("get_quote failed for %s: %s", symbol, e)
        return None

# --- Decision Logic ----------------------------------------------------------
def decide_for_position(sg: Dict[str, Any], symbol: str, qty: float,
                        entry_px: Optional[float],
                        opened_ts: Optional[int],
                        last_px: Optional[float]) -> Dict[str, Any]:
    """
    Returns a decision dict. No side-effects (no order placement).
    """
    # Normalize/fallbacks
    ep = float(entry_px) if isinstance(entry_px, (int, float)) else None
    lp = float(last_px) if isinstance(last_px, (int, float)) else None

    if lp is None:
        dec = {"symbol": symbol, "qty": qty, "entry": ep, "opened_ts": opened_ts, "last": None, "action": "SKIP_NO_LAST"}
        LOG.info("[DECISION] %s SKIP_NO_LAST %s", symbol, json.dumps(dec))
        return dec

    if ep is None or ep <= 0:
        dec = {"symbol": symbol, "qty": qty, "entry": ep, "opened_ts": opened_ts, "last": lp, "action": "SKIP_NO_ENTRY"}
        LOG.info("[DECISION] %s SKIP_NO_ENTRY %s", symbol, json.dumps(dec))
        return dec

    gain_pct = (lp - ep) / ep * 100.0
    LOG.info("[PROTECT] %s opened_ts=%s entry=%.4f last=%.4f", symbol, str(opened_ts), ep, lp)

    # Protection thresholds
    trail_arm = float(sg.get("protect_trail_arm_pct", 3.0))
    trail_pct = float(sg.get("protect_trail_pct", 3.0))
    stop_bps  = int(sg.get("stop_bps", 100))

    if gain_pct >= trail_arm:
        dec = {
            "symbol": symbol, "qty": qty, "entry": ep, "last": lp,
            "gain_pct": round(gain_pct, 3),
            "trail_arm": trail_arm, "trail_pct": trail_pct,
            "stop_bps": stop_bps,
            "action": "ARM_TRAIL",
        }
        LOG.info("[DECISION] %s ARM_TRAIL %s", symbol, json.dumps(dec))
        return dec

    # Below trail arm: do nothing for now (placeholder for stop/target logic)
    dec = {"symbol": symbol, "qty": qty, "entry": ep, "last": lp, "gain_pct": round(gain_pct, 3), "action": "HOLD"}
    LOG.info("[DECISION] %s HOLD %s", symbol, json.dumps(dec))
    return dec

# --- Main loop ---------------------------------------------------------------
def main() -> None:
    cfg = load_settings()
    sg = cfg["sell_guard"]
    LOG.info("sell_guard starting…")
    LOG.info("Settings: %s", json.dumps({"sell_guard": sg})[:300] + ("…" if len(json.dumps({"sell_guard": sg})) > 300 else ""))

    # Heartbeat & loop timing
    throttle_ms = int(sg.get("throttle_ms", 30000))
    heartbeat_next = time.time()

    # Account hint for logs
    account_hint = "UNKNOWN"

    while True:
        now = time.time()
        if now >= heartbeat_next:
            LOG.info("heartbeat: loop alive (account=%s)", account_hint)
            heartbeat_next = now + 30.0

        # --- Fetch positions ---
        LOG.info("positions scan…")
        pos = get_positions_dict()
        if not pos:
            LOG.warning("no positions payload; sleeping")
            time.sleep(throttle_ms / 1000.0)
            continue

        LOG.info("positions raw glimpse: %s", _glimpse(pos))

        rows = _iter_positions_tree(pos)
        # Capture account id if present
        for r in rows:
            if r.get("accountId"):
                account_hint = str(r["accountId"])
                break

        # Collapse to (symbol, qty)
        collapsed: List[Tuple[str, float]] = []
        for r in rows:
            sym = r.get("symbol") or ""
            qty = float(r.get("qty") or 0)
            if not sym or qty <= 0:
                continue
            collapsed.append((sym, qty))

        # Log normalized/eligible
        LOG.info("normalized positions -> %s", [(s, q) for s, q in collapsed])
        eligible = [(s, int(q)) for s, q in collapsed if q > 0]
        LOG.info("eligible final -> %s", eligible)

        if not eligible:
            time.sleep(throttle_ms / 1000.0)
            continue

        # --- Evaluate each candidate (no orders here) ---
        for sym, have_qty in eligible:
            LOG.info("candidates: %sx%s", sym, have_qty)

            # Inputs for decision: entry, opened_ts from rows; last via quote
            entry_px: Optional[float] = None
            opened_ts: Optional[int] = None
            for r in rows:
                if r.get("symbol") == sym:
                    entry_px = r.get("pricePaid")
                    opened_ts = r.get("dateAcquired")
                    break

            last_px = get_last_price(sym)

            decide_for_position(sg, sym, float(have_qty), entry_px, opened_ts, last_px)

        # Throttle between scans
        time.sleep(throttle_ms / 1000.0)

if __name__ == "__main__":
    LOG.info("Using SELL_GUARD_SETTINGS=%s", os.environ.get("SELL_GUARD_SETTINGS", DEFAULT_SETTINGS_PATH))
    try:
        main()
    except KeyboardInterrupt:
        LOG.info("sell_guard stopped by user")
