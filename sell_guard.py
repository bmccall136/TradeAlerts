from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple

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

HERE = os.path.abspath(os.path.dirname(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from services import etrade_service as et  # E*TRADE wrapper
from services import live_guardrails as gr  # opened_at + journal


def j(x: Any) -> str:
    try:
        return json.dumps(x, indent=2, sort_keys=True, default=str)
    except Exception:
        return str(x)


def f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def now_et() -> datetime:
    if ETZ:
        return datetime.now(ETZ)
    return datetime.now(UTC)


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
        "mode": "live",
        "allow_intraday_stoploss": True,
        "avoid_daytrades": False,
        "blocklist": [],
        "force_symbols": [],
        "force_without_entry": False,
        "limit_from": "bid",
        "limit_offset_bps": 0,
        "max_hold_mins": 1_000_000,
        "min_hold_days": 0,
        "min_hold_minutes": 0,
        "normalize_tick": 0.01,
        "sell_protect_after_mins": 0,
        "sell_window_start_et": "09:35",
        "sell_window_end_et": "15:55",
        "stop_bps": 100,
        "target_bps": 200,
        "protect_min_gain_pct": 1.5,
        "protect_trail_arm_pct": 3.0,
        "protect_trail_pct": 3.0,
        "use_extended_hours": True,
        "circuit_fail_threshold": 2,
        "circuit_open_seconds": 480,
        "max_place_attempts": 4,
        "market_fallback_for": ["SELL_STOP", "TIMEOUT"],
    },
}

LIVE_MODE_FILE = os.path.join(HERE, "live_mode.txt")
VALID_LIVE_MODES = {"DAY", "SWING"}
LIVE_MODE_DEFAULT = "DAY"

SELL_GUARD_FILES = {
    "DAY": os.path.join(HERE, "sell_guard_settings_day.json"),
    "SWING": os.path.join(HERE, "sell_guard_settings_swing.json"),
}


def _read_live_mode() -> str:
    """Read DAY/SWING from live_mode.txt with a safe default."""
    try:
        with open(LIVE_MODE_FILE, encoding="utf-8") as f:
            text = f.read().strip().upper()
        if text in VALID_LIVE_MODES:
            return text
    except FileNotFoundError:
        pass
    except Exception as exc:
        LOG.warning("live_mode: failed to read %s: %s", LIVE_MODE_FILE, exc)
    return LIVE_MODE_DEFAULT


def _resolve_settings_path() -> str:
    """
    Decide which sell_guard_settings*.json to use:

    1) If SELL_GUARD_SETTINGS env is set and exists -> use it.
    2) Else look at live_mode.txt (DAY/SWING) and choose
       sell_guard_settings_day.json or sell_guard_settings_swing.json.
    3) If missing, fall back to sell_guard_settings.json.
    """
    env_path = os.environ.get("SELL_GUARD_SETTINGS")
    if env_path:
        if os.path.exists(env_path):
            LOG.info("Using SELL_GUARD_SETTINGS from env: %s", env_path)
            return env_path
        else:
            LOG.warning(
                "SELL_GUARD_SETTINGS=%s does not exist; falling back to mode mapping",
                env_path,
            )

    mode = _read_live_mode()
    path = SELL_GUARD_FILES.get(mode) or os.path.join(HERE, "sell_guard_settings.json")
    if not os.path.exists(path):
        fallback = os.path.join(HERE, "sell_guard_settings.json")
        LOG.warning(
            "Mode %s mapped to %s but it does not exist; falling back to %s",
            mode,
            path,
            fallback,
        )
        return fallback

    LOG.info("Mode %s → sell_guard settings from %s", mode, path)
    return path


def load_settings() -> Dict[str, Any]:
    path = _resolve_settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except FileNotFoundError:
        LOG.warning("sell_guard settings file not found at %s; using defaults", path)
        user = {}
    except Exception as exc:
        LOG.warning(
            "failed to load sell_guard settings from %s: %s; using defaults",
            path,
            exc,
        )
        user = {}

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
# E*TRADE helpers
# --------------------------------------------------------------------------- #

def get_acct_key() -> str:
    # Prefer the helper in etrade_service if present
    if hasattr(et, "get_account_id_key"):
        try:
            k = et.get_account_id_key()
            if k:
                return str(k)
        except Exception:
            pass
    # Fallback to attribute
    if hasattr(et, "account_id_key") and et.account_id_key:
        return str(et.account_id_key)
    # Last resort
    try:
        return str(et.account_id_key())
    except Exception:
        return "UNKNOWN"


def preview(acct_key: str, sym: str, qty: int, price_type: str, limit_or_none: float | None):
    """Thin wrapper around et.preview_equity_order using our sell-guard params."""
    return et.preview_equity_order(
        acct_key,
        sym,
        qty,
        limit_or_none if price_type == "LIMIT" else None,
        action="SELL",
        price_type=price_type,
        order_term="GOOD_FOR_DAY",
        market_session="REGULAR",
    )


def best_bid(symbol: str) -> float:
    try:
        q = et.fetch_etrade_quote(symbol) or {}
    except Exception:
        q = et.get_quote(symbol) or {}

    if isinstance(q, dict):
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
    try:
        q = et.fetch_etrade_quote(symbol) or {}
    except Exception:
        q = et.get_quote(symbol) or {}

    if isinstance(q, dict):
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


def _glimpse(obj: Any) -> Any:
    try:
        if isinstance(obj, dict):
            return {"type": "dict", "keys": list(obj.keys())[:10]}
        if isinstance(obj, list):
            return {"type": "list", "len": len(obj)}
        return str(obj)[:120]
    except Exception:
        return "<glimpse-failed>"


def get_positions_any(acct_key: str | None = None) -> Any:
    try:
        return et.get_positions(acct_key)
    except TypeError:
        return et.get_positions()


def iter_positions(pobj: Any):
    """Yield (sym, qty, last, entry) from E*TRADE shapes."""

    def L(x):
        if isinstance(x, list):
            return x
        if x is None:
            return []
        return [x]

    if not isinstance(pobj, dict):
        return

    pr = pobj.get("PortfolioResponse") or {}
    for ap in L(pr.get("AccountPortfolio")):
        positions = (
            ap.get("Position")
            or ap.get("position")
            or ap.get("Positions")
            or ap.get("positions")
        )
        for p in L(positions):
            prod = p.get("Product") or p.get("product") or {}
            sym = (prod.get("symbol") or "").strip().upper()

            if not sym:
                desc = (p.get("symbolDescription") or "").strip()
                if "(" in desc and desc.endswith(")"):
                    sym = desc.split("(")[-1][:-1].strip().upper()

            qty = f(
                p.get("quantity")
                or p.get("qty")
                or p.get("longQuantity")
                or p.get("positionQty")
                or 0,
                0.0,
            )

            q = p.get("Quick") or {}
            ins = p.get("Instrument") or {}
            allf = p.get("All") or {}

            last = f(
                q.get("lastTrade")
                or ins.get("lastTrade")
                or allf.get("extendedHourLastTrade")
                or 0,
                0.0,
            )

            entry = f(
                p.get("pricePaid")
                or p.get("purchasePrice")
                or p.get("averagePrice")
                or 0,
                0.0,
            )

            if sym and qty > 0:
                yield sym, qty, last, entry


def opened_today(sym: str) -> bool:
    """BUY today? (PDT helper)."""
    try:
        for t in et.get_transactions(start="today", end="today") or []:
            tsym = (t.get("symbol") or t.get("securitySymbol") or "").strip().upper()
            side = (t.get("transactionType") or t.get("side") or "").upper()
            if tsym == sym.upper() and "BUY" in side:
                return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------- #
# Config dataclass
# --------------------------------------------------------------------------- #


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


# trailing state (in-process)
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
                limit_px = max(0.01, round(ref - tick, 2))
            pt = "LIMIT"
    return pt, limit_px


def place_with_adaptive_variants(
    acct_key: str,
    sym: str,
    qty: int,
    price_type: str,
    limit_or_none: float | None,
    max_outer: int,
) -> bool:
    """
    Preview + place loop.

    Uses et.place_equity_order() for the actual place call. On transient
    venue errors (500/code 100), we re-preview and retry up to max_outer.
    """
    for outer in range(1, max_outer + 1):
        try:
            prev = preview(acct_key, sym, qty, price_type, limit_or_none)
        except Exception as e:
            LOG.error("preview failed for %s: %s", sym, e)
            return False

        if not isinstance(prev, dict) or "PreviewOrderResponse" not in prev:
            LOG.error("preview response malformed for %s: %s", sym, _glimpse(prev))
            return False

        try:
            et.place_equity_order(prev, qty=qty)
            LOG.info("%s SELL placed (%s)", sym, price_type)
            return True
        except Exception as e:
            msg = str(e)
            LOG.warning("place_equity_order failed for %s (outer=%d): %s", sym, outer, msg)
            # Transient venue issues → retry with fresh preview
            if (
                " 500:" in msg
                or '"code": 100' in msg
                or "'code': 100" in msg
            ):
                LOG.warning(
                    "Transient venue error for %s; refreshing preview (outer=%d)",
                    sym,
                    outer,
                )
                time.sleep(0.8 * outer)
                continue

            # Non-transient error → give up for this symbol
            return False

    return False


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def main() -> None:
    cfg_raw = load_settings()
    LOG.info("sell_guard starting…")
    LOG.info("Settings: %s", j(cfg_raw))

    sg = cfg_raw["sell_guard"]

    cfg = GuardSettings(
        sell_window_start_et=sg.get("sell_window_start_et")
        or cfg_raw.get("sell_window_start_et")
        or "09:35",
        sell_window_end_et=sg.get("sell_window_end_et")
        or cfg_raw.get("sell_window_end_et")
        or "15:55",
        throttle_ms=int(sg.get("throttle_ms", cfg_raw.get("throttle_ms", 30_000))),
        max_place_attempts=int(
            sg.get("max_place_attempts", cfg_raw.get("max_place_attempts", 4))
        ),
        market_fallback_for=list(
            sg.get("market_fallback_for")
            or cfg_raw.get("market_fallback_for")
            or []
        ),
        use_extended_hours=bool(
            sg.get("use_extended_hours", cfg_raw.get("use_extended_hours", False))
        ),
        normalize_tick=float(
            sg.get("normalize_tick", cfg_raw.get("normalize_tick", 0.01))
        ),
        sg=sg,
    )

    acct_key = get_acct_key()
    LOG.info("heartbeat: loop alive (account=%s)", acct_key)

    gr.init_table()
    heartbeat_next = time.time()
    throttle = max(1, int(cfg.throttle_ms / 1000))

    def inside_window() -> bool:
        try:
            etnow = now_et()
            sh, sm = map(int, cfg.sell_window_start_et.split(":"))
            eh, em = map(int, cfg.sell_window_end_et.split(":"))
            on = ((etnow.hour, etnow.minute) >= (sh, sm)) and (
                (etnow.hour, etnow.minute) <= (eh, em)
            )
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
            time.sleep(throttle)
            continue

        # opened_at map from guardrails
        open_map: Dict[str, datetime] = {}
        for e in gr.list_open_entries():
            sym = (e.get("symbol") or "").upper()
            ts = e.get("opened_at")
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

        # positions
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

        for sym, qty, last, entry in rows:
            sym = sym.upper()
            if sym in block:
                continue
            if qty < 1:
                continue

            opened = open_map.get(sym)
            if not opened and not force_without_entry:
                # no opened_at → let it sit; guardrails didn't track entry
                continue

            # P&L %
            pl_pct = (
                (last - entry) / max(entry, 0.0001) * 100.0
                if (last > 0 and entry > 0)
                else 0.0
            )

            # Hold minutes
            hold_min = 0.0
            if opened:
                try:
                    if ETZ:
                        now_naive = now_et().astimezone(ETZ).replace(tzinfo=None)
                        opened_naive = opened.astimezone(ETZ).replace(tzinfo=None)
                    else:
                        now_naive = now_et().replace(tzinfo=None)
                        opened_naive = opened.replace(tzinfo=None)
                    hold_min = max(
                        0.0, (now_naive - opened_naive).total_seconds() / 60.0
                    )
                except Exception:
                    LOG.warning("[OPENED_AT] bad opened_at for %s: %r", sym, opened)
                    hold_min = 0.0

            candidates.append((sym, int(qty), pl_pct, hold_min, entry))

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

        # thresholds
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
            # PDT guard
            if avoid_daytrades and opened_today(s):
                LOG.info(
                    "[PDT] Skipping %s (opened today; avoid_daytrades on)", s
                )
                continue

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

            # Arm immediately at threshold
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

            # If armed, check drawdown vs hi
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
                    continue

            # Respect min_hold for non-trailing exits
            if hold_min < min_hold:
                LOG.info(
                    "[HOLD] %s hold %.1f mins < %.1f mins (min_hold); gain=%.2f%%",
                    s,
                    hold_min,
                    min_hold,
                    cur,
                )
                continue

            # Fixed target
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
