from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple

from ai_advisor import get_ai_recommendation

try:
    from zoneinfo import ZoneInfo

    ETZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ETZ = None

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

LOG = logging.getLogger("sell-guard")
LOG.setLevel(logging.INFO)
for h in list(LOG.handlers):
    LOG.removeHandler(h)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(
    logging.Formatter(
        "%(asctime)s,%(msecs)03d %(levelname)s sell-guard: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
LOG.addHandler(_sh)

# --------------------------------------------------------------------------- #
# Paths / imports
# --------------------------------------------------------------------------- #

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

sys.path.insert(0, ROOT)

try:
    from services import etrade_service as et
except Exception as exc:  # pragma: no cover
    LOG.error("failed to import etrade_service: %s", exc)
    et = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #


def now_et() -> datetime:
    dt = datetime.now(UTC)
    if ETZ:
        dt = dt.astimezone(ETZ)
    return dt


def parse_hhmm(s: str) -> Tuple[int, int]:
    s = (s or "").strip()
    if not s:
        return (0, 0)
    parts = s.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return (0, 0)
    return max(0, min(23, h)), max(0, min(59, m))


def now_in_window(start_hhmm: str, end_hhmm: str) -> bool:
    h1, m1 = parse_hhmm(start_hhmm)
    h2, m2 = parse_hhmm(end_hhmm)
    now = now_et()
    cur = (now.hour, now.minute)

    if (h1, m1) == (0, 0) and (h2, m2) == (0, 0):
        return True

    start = (h1, m1)
    end = (h2, m2)

    if start <= end:
        return start <= cur <= end
    else:
        return cur >= start or cur <= end


# --------------------------------------------------------------------------- #
# Defaults + settings loader
# --------------------------------------------------------------------------- #

DEFAULTS = {
    "normalize_tick": 0.01,
    "sell_window_start_et": "09:35",
    "sell_window_end_et": "15:55",
    "throttle_ms": 30_000,
    "use_extended_hours": False,
    "market_fallback_for": ["SELL_STOP", "TIMEOUT"],
    "max_place_attempts": 4,
    "sell_guard": {
        "allow_intraday_stoploss": True,
        "avoid_daytrades": False,
        "stop_bps": 100,
        "target_bps": 200,
        "min_hold_minutes": 0,
        "max_hold_mins": 1_000_000,
        "protect_trail_arm_pct": 3.0,
        "protect_trail_pct": 3.0,
        "protect_min_gain_pct": 1.5,
        "blocklist": [],
        "force_without_entry": False,
    },
}

# 🔧 respect SELL_GUARD_SETTINGS from launcher; fall back to default file
SETTINGS_FILE = os.environ.get(
    "SELL_GUARD_SETTINGS", os.path.join(HERE, "sell_guard_settings.json")
)


def _load_user_settings() -> Dict[str, Any]:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            LOG.info("Loading sell guard settings from %s", SETTINGS_FILE)
            return json.load(f)
    except FileNotFoundError:
        LOG.warning("settings file not found: %s", SETTINGS_FILE)
    except Exception as exc:  # pragma: no cover
        LOG.error("failed to load %s: %s", SETTINGS_FILE, exc)
    return {}


def load_settings() -> Dict[str, Any]:
    user = _load_user_settings()
    merged = dict(DEFAULTS)
    merged["sell_guard"] = dict(DEFAULTS["sell_guard"])

    # top-level overrides
    for k, v in user.items():
        if k != "sell_guard":
            merged[k] = v

    # nested sell_guard overrides
    if isinstance(user.get("sell_guard"), dict):
        merged["sell_guard"].update(user["sell_guard"])

    return merged


# --------------------------------------------------------------------------- #
# E*TRADE helpers / wrappers
# --------------------------------------------------------------------------- #


def get_account_key() -> str:
    """
    Use your existing et.get_account_summary() helper to find the primary
    account_key, instead of a non-existent get_primary_account().
    """
    if not et:
        raise RuntimeError("etrade_service not available")

    try:
        summary = et.get_account_summary() or {}
    except Exception as exc:
        raise RuntimeError(f"get_account_summary failed: {exc}") from exc

    key = (
        summary.get("account_key")
        or summary.get("accountIdKey")
        or summary.get("account_id_key")
    )

    # in case it's nested for any reason
    if not key:
        for v in summary.values():
            if isinstance(v, dict):
                key = (
                    v.get("account_key")
                    or v.get("accountIdKey")
                    or v.get("account_id_key")
                )
                if key:
                    break

    if not key:
        raise RuntimeError(f"could not determine account_key from {summary!r}")

    return str(key)


def get_positions_any(acct_key: str | None = None) -> Dict[str, Any]:
    """Return raw positions payload from E*TRADE.

    NOTE: We ignore acct_key for now. et.get_positions() already knows
    the default account via account_summary, so we just call it with
    no arguments and return the raw payload for iter_positions().
    """
    payload: Dict[str, Any] = {}
    try:
        payload = et.get_positions() or {}
    except Exception as exc:  # pragma: no cover - defensive
        LOG.warning("get_positions_any failed: %s", exc)
    # Useful for debugging; leave structure intact for iter_positions()
    return payload

def get_open_orders(acct_key: str) -> Dict[str, Any]:
    """Return open orders; your et.list_orders() does not take status= kwarg."""
    if not et:
        raise RuntimeError("etrade_service not available")
    try:
        # Assuming your wrapper already returns only OPEN orders or all orders.
        return et.list_orders(acct_key)
    except Exception as exc:  # pragma: no cover
        LOG.error("get_open_orders failed: %s", exc)
        return {}

def preview(acct_key: str, sym: str, qty: int, price_type: str, limit_px: float | None):
    if not et:
        raise RuntimeError("etrade_service not available")
    return et.preview_equity_order(
        acct_key, symbol=sym, qty=qty, side="SELL", price_type=price_type, limit_price=limit_px
    )


def place(acct_key: str, sym: str, qty: int, price_type: str, limit_px: float | None):
    if not et:
        raise RuntimeError("etrade_service not available")
    return et.place_equity_order(
        acct_key, symbol=sym, qty=qty, side="SELL", price_type=price_type, limit_price=limit_px
    )


def best_bid(sym: str) -> float:
    if not et:
        return 0.0
    try:
        q = et.get_quote(sym) or {}
        bd = q.get("quoteData", [{}])[0].get("all", {}).get("bid", 0.0)
        return float(bd or 0.0)
    except Exception as exc:  # pragma: no cover
        LOG.error("best_bid(%s) failed: %s", sym, exc)
        return 0.0


def last_trade(sym: str) -> float:
    if not et:
        return 0.0
    try:
        q = et.get_quote(sym) or {}
        lt = q.get("quoteData", [{}])[0].get("all", {}).get("lastTrade", 0.0)
        return float(lt or 0.0)
    except Exception as exc:  # pragma: no cover
        LOG.error("last_trade(%s) failed: %s", sym, exc)
        return 0.0


# --------------------------------------------------------------------------- #
# Position parsing
# --------------------------------------------------------------------------- #


def _glimpse(x: Any, limit: int = 200) -> str:
    try:
        s = json.dumps(x, default=str, separators=(",", ":"))
    except Exception:
        s = repr(x)
    if len(s) > limit:
        s = s[: limit - 3] + "..."
    return s


from typing import Iterable, Tuple

def iter_positions(payload) -> Iterable[Tuple[str, float, float, float]]:
    """
    Yield (symbol, qty, market_value, avg_price) tuples from the raw
    E*TRADE /portfolio.json payload.

    This implementation is dictionary-only and does NOT depend on any
    Position dataclass, so we avoid the 'name Position is not defined'
    mess entirely.
    """
    if not payload:
        return []

    # Accept both the raw json() and already-unwrapped dicts
    pr = (
        payload.get("PortfolioResponse")
        or payload.get("portfolioResponse")
        or payload
    )

    # AccountPortfolio can be a dict or list
    acct_ports = (
        pr.get("AccountPortfolio")
        or pr.get("accountPortfolio")
        or []
    )
    if isinstance(acct_ports, dict):
        acct_ports = [acct_ports]

    def _f(x, default=0.0):
        try:
            if x is None or x == "":
                return float(default)
            return float(str(x).replace(",", ""))
        except Exception:
            return float(default)

    for acct in acct_ports:
        positions = acct.get("Position") or acct.get("position") or []
        if isinstance(positions, dict):
            positions = [positions]

        for pos in positions:
            try:
                prod = pos.get("Product") or pos.get("product") or {}
                sym = (prod.get("symbol") or pos.get("symbol") or "").upper().strip()
                if not sym:
                    continue

                qty = _f(
                    pos.get("quantity")
                    or pos.get("longQuantity")
                    or pos.get("longQty")
                    or pos.get("positionQty")
                    or pos.get("positionQuantity")
                    or 0.0
                )

                mkt_val = _f(
                    pos.get("marketValue")
                    or (qty * _f(pos.get("lastTrade") or pos.get("lastPrice") or 0.0))
                )

                avg = _f(
                    pos.get("averagePrice")
                    or pos.get("averageCost")
                    or pos.get("costBasisPerShare")
                    or pos.get("costBasis")
                    or 0.0
                )

                # yield (symbol, qty, market_value, avg_price)
                yield (sym, qty, mkt_val, avg)

            except Exception as e:
                LOG.warning("iter_positions: bad position row %r: %s", pos, e)

def opened_today(sym: str) -> bool:
    """
    Rough PDT helper. We'll refine if needed.
    """
    if not et:
        return False

    try:
        tx = et.get_transactions(sym) or {}
    except Exception as exc:  # pragma: no cover
        LOG.error("get_transactions(%s) failed: %s", sym, exc)
        return False

    arr = (
        tx.get("TransactionDetails") or tx.get("Transactions") or tx.get("transactions") or []
    )
    if isinstance(arr, dict):
        arr = [arr]

    today = now_et().date()
    for row in arr:
        if not isinstance(row, dict):
            continue
        ttype = str(row.get("transactionType") or "").upper()
        if "BUY" not in ttype and "BOUGHT" not in ttype:
            continue
        dt_str = str(row.get("transactionDate") or "").strip()
        if not dt_str:
            continue
        try:
            dt = datetime.fromisoformat(dt_str).date()
        except Exception:
            continue
        if dt == today:
            return True

    return False


# --------------------------------------------------------------------------- #
# Settings wrapper
# --------------------------------------------------------------------------- #


@dataclass
class GuardSettings:
    normalize_tick: float
    sell_window_start_et: str
    sell_window_end_et: str
    throttle_ms: int
    max_place_attempts: int
    market_fallback_for: List[str]
    use_extended_hours: bool
    sg: Dict[str, Any]


TRAIL: Dict[str, Dict[str, float]] = {}  # sym -> {"hi": float, "trail_pct": float, "armed": 0/1}


# --------------------------------------------------------------------------- #
# Core helpers
# --------------------------------------------------------------------------- #


def compute_order_params(symbol: str, cfg: GuardSettings) -> Tuple[str, float | None]:
    """Decide MARKET vs LIMIT and compute limit price when enabled."""
    pt, limit_px = "MARKET", None
    limit_from = (cfg.sg.get("limit_from") or "").lower()
    tick = float(cfg.sg.get("normalize_tick") or cfg.normalize_tick or 0.01) or 0.01
    offset_bps = int(cfg.sg.get("limit_offset_bps") or 0)

    if limit_from in ("bid", "last"):
        ref = best_bid(symbol) if limit_from == "bid" else last_trade(symbol)
        if ref > 0:
            if offset_bps:
                limit_px = max(0.01, round(ref * (1 - offset_bps / 10_000.0), 2))
            else:
                limit_px = round(ref / tick) * tick

    if limit_px is not None:
        return "LIMIT", limit_px

    return pt, None


def ai_exit_check(
    symbol: str,
    qty: int,
    pl_pct: float,
    hold_min: float,
    entry_px: float,
    last_px: float,
) -> dict:
    """Ask the AI advisor whether we should consider an early EXIT."""
    sym = symbol.upper()
    try:
        snapshot = {
            "decision_type": "EXIT",
            "symbol": sym,
            "qty": int(qty),
            "entry_price": float(entry_px),
            "last_price": float(last_px),
            "unrealized_pct": float(pl_pct),
            "hold_minutes": float(hold_min),
            "timeframe": "short-term swing (1-3 days)",
            "portfolio": {},
            "news_headlines": [],
        }
    except Exception:
        snapshot = {
            "decision_type": "EXIT",
            "symbol": sym,
            "qty": int(qty),
            "unrealized_pct": float(pl_pct),
            "hold_minutes": float(hold_min),
            "timeframe": "short-term swing (1-3 days)",
        }

    return get_ai_recommendation(snapshot)


def place_with_adaptive_variants(
    acct_key: str,
    sym: str,
    qty: int,
    price_type: str,
    limit_or_none: float | None,
    max_outer: int,
) -> bool:
    """Preview + place loop with basic venue error retries."""
    for outer in range(1, max_outer + 1):
        try:
            prev = preview(acct_key, sym, qty, price_type, limit_or_none)
        except Exception as e:
            LOG.error("preview failed for %s: %s", sym, e)
            return False

        if not isinstance(prev, dict) or "PreviewOrderResponse" not in prev:
            LOG.error("preview response malformed for %s: %s", sym, _glimpse(prev))
            return False

        por = prev["PreviewOrderResponse"]
        if por.get("orderType") != "EQ":
            LOG.error("unexpected orderType in preview: %s", por.get("orderType"))
            return False

        msgs = por.get("PreviewMessage") or []
        if isinstance(msgs, dict):
            msgs = [msgs]

        venue_err = False
        for m in msgs:
            code = str(m.get("code") or "")
            text = str(m.get("text") or "")
            LOG.info("[PREVIEW_MSG] code=%s text=%s", code, text)
            if code == "100" or "venue" in text.lower():
                venue_err = True

        if venue_err:
            LOG.warning(
                "venue error on preview (attempt %d/%d); retrying with fresh quote",
                outer,
                max_outer,
            )
            time.sleep(1.0)
            continue

        try:
            placed = place(acct_key, sym, qty, price_type, limit_or_none)
        except Exception as e:
            LOG.error("place failed for %s: %s", sym, e)
            return False

        if not isinstance(placed, dict) or "PlaceOrderResponse" not in placed:
            LOG.error("place response malformed for %s: %s", sym, _glimpse(placed))
            return False

        por2 = placed["PlaceOrderResponse"]
        if por2.get("orderType") != "EQ":
            LOG.error("unexpected orderType in place: %s", por2.get("orderType"))
            return False

        LOG.info("[PLACE_OK] %s qty=%d price_type=%s limit=%s", sym, qty, price_type, limit_or_none)
        return True

    LOG.error("max venue retries reached for %s; giving up", sym)
    return False


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #


def main() -> None:
    LOG.info("=== sell_guard starting ===")

    settings = load_settings()
    sg = settings.get("sell_guard", {}) or {}
    cfg = GuardSettings(
        normalize_tick=float(settings.get("normalize_tick", 0.01)),
        sell_window_start_et=str(settings.get("sell_window_start_et", "09:35")),
        sell_window_end_et=str(settings.get("sell_window_end_et", "15:55")),
        throttle_ms=int(settings.get("throttle_ms", 30_000)),
        max_place_attempts=int(settings.get("max_place_attempts", 4)),
        market_fallback_for=list(settings.get("market_fallback_for", ["SELL_STOP", "TIMEOUT"])),
        use_extended_hours=bool(settings.get("use_extended_hours", False)),
        sg=sg,
    )

    acct_key = get_account_key()
    LOG.info("Using account_key=%s", acct_key)

    throttle = max(1, int(cfg.throttle_ms / 1000))

    while True:
        # --- 1) Skip non-trading days (weekends) completely -------------------
        now = datetime.now(ETZ or UTC)
        if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            LOG.info("weekend (Sat/Sun); sell_guard idle, sleeping %ds", throttle)
            time.sleep(throttle)
            continue

        # --- 2) Enforce intraday sell window (e.g. 09:30–16:00 ET) -----------
        if not now_in_window(cfg.sell_window_start_et, cfg.sell_window_end_et):
            LOG.info(
                "outside sell window %s–%s ET; sleeping %ds",
                cfg.sell_window_start_et,
                cfg.sell_window_end_et,
                throttle,
            )
            time.sleep(throttle)
            continue

        open_orders = get_open_orders(acct_key)
        LOG.info("open orders glimpse: %s", _glimpse(open_orders))

        open_map: Dict[str, datetime] = {}
        try:
            ords = (
                open_orders.get("OrderResponse") or open_orders.get("Orders") or open_orders or {}
            )
            if isinstance(ords, dict):
                ords = ords.get("Order") or ords.get("orders") or []
            if isinstance(ords, dict):
                ords = [ords]
        except Exception:
            ords = []

        for row in ords:
            if not isinstance(row, dict):
                continue
            sym = str(
                row.get("symbolDescription") or row.get("symbol") or row.get("prodSym") or ""
            ).upper()
            ts = row.get("orderTime") or row.get("placedTime") or row.get("timePlaced")
            if not sym or not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    if ETZ:
                        dt = dt.replace(tzinfo=ETZ)
                else:
                    if ETZ:
                        dt = dt.astimezone(ETZ)
                open_map[sym] = dt
            except Exception:
                continue

        try:
            pos = get_positions_any(acct_key)
        except Exception as e:
            LOG.warning("get_positions failed: %s", e)
            time.sleep(throttle)
            continue

        LOG.info("positions raw glimpse: %s", _glimpse(pos))

        rows: List[Tuple[str, float, float, float]] = list(iter_positions(pos))

        block = set(map(str.upper, cfg.sg.get("blocklist") or []))
        force_without_entry = bool(cfg.sg.get("force_without_entry", False))

        candidates: List[Tuple[str, int, float, float, float]] = []

        for (sym, qty, mv, entry_price) in rows:
            opened = open_map.get(sym)

            # If we don't have an opened_at record, treat it as 0-minute hold
            # but still let other guards decide whether it’s eligible.
            hold_min = 0.0
            if opened:
                try:
                    hold_sec = (tnow - opened).total_seconds()
                    hold_min = max(0.0, hold_sec / 60.0)
                except Exception:
                    hold_min = 0.0

            pl_pct = 0.0
            if qty and entry_price and entry_price > 0:
                try:
                    pl_pct = ((mv / qty) - entry_price) / entry_price * 100.0
                except Exception:
                    pl_pct = 0.0

            candidates.append((sym, qty, pl_pct, hold_min, entry_price))

        LOG.info("eligible final -> %s", [(s, q) for s, q, _, _, _ in candidates])
        if not candidates:
            LOG.info("candidates: (none)")
            LOG.info("sleeping %ds", throttle)
            time.sleep(throttle)
            continue

        LOG.info(
            "candidates: %s",
            ",".join(f"{s}x{q}" for s, q, _, _, _ in candidates),
        )

        stop_pct = abs(float(cfg.sg.get("stop_bps", 100))) / 100.0
        target_pct = abs(float(cfg.sg.get("target_bps", 200))) / 100.0
        min_hold = float(cfg.sg.get("min_hold_minutes", 0))
        max_hold = float(cfg.sg.get("max_hold_mins", 1_000_000))

        arm_at = float(cfg.sg.get("protect_trail_arm_pct", 3.0))
        trail_pct_cfg = float(cfg.sg.get("protect_trail_pct", 3.0))
        min_gain_lock = float(cfg.sg.get("protect_min_gain_pct", 1.5))

        allow_intraday_stop = bool(cfg.sg.get("allow_intraday_stoploss", True))
        avoid_daytrades = bool(cfg.sg.get("avoid_daytrades", False))

        for s, qty, pl_pct, hold_min, entry_px in candidates:
            # PDT guard (you've said it's irrelevant in cash-mode, but we keep it optional)
            if avoid_daytrades and opened_today(s):
                LOG.info(
                    "[PDT] Skipping %s (opened today; avoid_daytrades on)", s
                )
                continue

            # --- AI emergency exit (FULL SEND) ---
            try:
                last_px = entry_px * (1.0 + (pl_pct / 100.0)) if entry_px else 0.0
                ai = ai_exit_check(s, qty, pl_pct, hold_min, entry_px, last_px)
                ai_action = str(ai.get("action", "HOLD")).upper()
                ai_conf = int(ai.get("confidence", 0) or 0)
                ai_tags = ai.get("reason_tags") or []

                if ai_action in {"SELL", "RED_FLAG"} and ai_conf >= 80:
                    pt, lim = compute_order_params(s, cfg)
                    LOG.info(
                        "[AI_EXIT] %s qty=%d pl=%.2f%% hold=%.1f mins → %s (%d%%) tags=%s → place %s%s",
                        s,
                        qty,
                        pl_pct,
                        hold_min,
                        ai_action,
                        ai_conf,
                        ",".join(ai_tags),
                        pt,
                        f" {lim:.2f}" if lim else "",
                    )
                    place_with_adaptive_variants(
                        acct_key,
                        s,
                        qty,
                        pt,
                        lim if pt == "LIMIT" else None,
                        cfg.max_place_attempts,
                    )
                    continue
            except Exception as exc:
                LOG.warning("[AI_EXIT] error for %s: %s", s, exc)

            # Intraday stop-loss
            if allow_intraday_stop and pl_pct <= -stop_pct:
                pt, lim = compute_order_params(s, cfg)
                LOG.info(
                    "[STOP] %s %.2f%% ≤ -%.2f%% → place %s%s",
                    s,
                    pl_pct,
                    stop_pct,
                    pt,
                    f" {lim:.2f}" if lim else "",
                )
                place_with_adaptive_variants(
                    acct_key,
                    s,
                    qty,
                    pt,
                    lim if pt == "LIMIT" else None,
                    cfg.max_place_attempts,
                )
                continue

            # Max-hold timeout
            if hold_min >= max_hold >= 0:
                pt, lim = compute_order_params(s, cfg)
                LOG.info(
                    "[TIMEOUT] %s hold %.1f mins ≥ %.1f mins → place %s%s",
                    s,
                    hold_min,
                    max_hold,
                    pt,
                    f" {lim:.2f}" if lim else "",
                )
                place_with_adaptive_variants(
                    acct_key,
                    s,
                    qty,
                    pt,
                    lim if pt == "LIMIT" else None,
                    cfg.max_place_attempts,
                )
                continue

            # --- Trailing logic ---
            cur = pl_pct
            hi = TRAIL.get(s, {}).get("hi", cur)
            hi = max(hi, cur)
            TRAIL.setdefault(s, {})["hi"] = hi

            if cur >= arm_at and not TRAIL[s].get("armed"):
                TRAIL[s]["armed"] = 1
                TRAIL[s]["trail_pct"] = max(0.5, trail_pct_cfg)
                LOG.info(
                    "[TRAIL_ARM] %s gain=%.2f%% ≥ %.2f%% → armed trail=%.2f%% (hi=%.2f%%)",
                    s,
                    cur,
                    arm_at,
                    TRAIL[s]["trail_pct"],
                    hi,
                )

            if TRAIL[s].get("armed"):
                trail = TRAIL[s]["trail_pct"]
                if cur <= (hi - trail):
                    pt, lim = compute_order_params(s, cfg)
                    LOG.info(
                        "[TRAIL_SELL] %s gain %.2f%% fell from hi %.2f%% by ≥ %.2f%% → place %s%s",
                        s,
                        cur,
                        hi,
                        trail,
                        pt,
                        f" {lim:.2f}" if lim else "",
                    )
                    place_with_adaptive_variants(
                        acct_key,
                        s,
                        qty,
                        pt,
                        lim if pt == "LIMIT" else None,
                        cfg.max_place_attempts,
                    )
                    continue
                else:
                    LOG.info(
                        "[ARMED] %s hi=%.2f%% gain=%.2f%% trail=%.2f%% (holding)",
                        s,
                        hi,
                        cur,
                        trail,
                    )

            if hold_min < min_hold:
                LOG.info(
                    "[HOLD] %s hold %.1f mins < %.1f mins (min_hold); gain=%.2f%%",
                    s,
                    hold_min,
                    min_hold,
                    cur,
                )
                continue

            if cur >= target_pct:
                pt, lim = compute_order_params(s, cfg)
                LOG.info(
                    "[TARGET] %s gain %.2f%% ≥ %.2f%% → place %s%s",
                    s,
                    cur,
                    target_pct,
                    pt,
                    f" {lim:.2f}" if lim else "",
                )
                place_with_adaptive_variants(
                    acct_key,
                    s,
                    qty,
                    pt,
                    lim if pt == "LIMIT" else None,
                    cfg.max_place_attempts,
                )
                continue

            if cur >= min_gain_lock:
                pt, lim = compute_order_params(s, cfg)
                LOG.info(
                    "[LOCK] %s gain %.2f%% ≥ %.2f%% (min_gain_lock) → place %s%s",
                    s,
                    cur,
                    min_gain_lock,
                    pt,
                    f" {lim:.2f}" if lim else "",
                )
                place_with_adaptive_variants(
                    acct_key,
                    s,
                    qty,
                    pt,
                    lim if pt == "LIMIT" else None,
                    cfg.max_place_attempts,
                )
                continue

            LOG.info(
                "[HOLD] %s gain=%.2f%% hold=%.1f mins (waiting for trail/target/timeout)",
                s,
                cur,
                hold_min,
            )

        LOG.info("sleeping %ds", throttle)
        time.sleep(throttle)


if __name__ == "__main__":
    main()
