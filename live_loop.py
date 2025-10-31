from __future__ import annotations
import time as time_mod

import logging
import math
import os
import re
import time
from datetime import UTC
from zoneinfo import ZoneInfo
import datetime as dt
import time as time_mod
ET = ZoneInfo("America/New_York")
import time as time_mod
from types import SimpleNamespace
from typing import Any

from services import live_guardrails as lg
from services.broker import get_broker
from services.scan_speedups import (
    log_candidate,
    preload_history_yahoo,
)
from services.simulation_service import (
    _is_market_open,
    analyze_symbol,
    seconds_until_open,
)
from services.trading_helpers import get_holdings, get_trades

log = logging.getLogger("live")

_DEFAULTS = {
    "broker_mode": "LIVE",
    "pause_when_market_closed": True,
    "scan_sleep_secs": 5,
    "atr_len": 14,
    "bb_length": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "rsi_len": 14,
    "poll_interval": 5.0,
    "strict_buy_signals": 4,
    "require_sma20": True,
    "required_filters": [],  # e.g. ['adx','macd']
    "scan_heartbeat_secs": 10.0,
    "candidate_log_limit": -1,  # how many pretty lines per iteration (-1 = unlimited)
}

SAFE_ON = os.getenv("LIVE_SAFE_MODE", "").lower() in ("1", "true", "yes", "on")
SAFE_MAX = int(os.getenv("LIVE_MAX_QTY", "0") or 0)
_BP_BUFFER = float(os.getenv("LIVE_BP_BUFFER", "5"))  # dollars cushion
_LIVE_TPLUS_DAYS = int(os.getenv("LIVE_TPLUS_DAYS", "0") or 0)  # 0 = off

# ── helpers ──────────────────────────────────────────────────────────────────

def _select_funds_amount(settled: float, buying_power: float) -> tuple[float, str]:
    """Decide which cash figure to use for sizing:
    - If settled > 0, use settled (cash account safety).
    - Else if buying_power > 0, use buying_power (your preference for cash acct with BP shown).
    - Else 0.
    Returns (amount, source_label).
    """
    try:
        s = float(settled or 0.0)
    except Exception:
        s = 0.0
    try:
        bp = float(buying_power or 0.0)
    except Exception:
        bp = 0.0
    if s > 0:
        return s, 'settled'
    if bp > 0:
        return bp, 'bp'
    return 0.0, 'settled'



def _env_int(name: str, default: int | None = None) -> int | None:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    # common cases: SimpleNamespace, pydantic-ish
    return getattr(obj, "dict", lambda: getattr(obj, "__dict__", {}))() or {}


def _get_comp(bal: dict[str, Any]) -> dict[str, Any]:
    bal = _to_dict(bal)
    comp = bal.get("computedBalance") or bal.get("Computed") or {}
    if not isinstance(comp, dict):
        comp = _to_dict(comp)
    return comp


def _from_any(bal: dict[str, Any], *keys: str) -> float | None:
    comp = _get_comp(bal)
    for k in keys:
        # prefer top-level key if present, else look in computedBalance
        for d in (bal, comp):
            if k in d:
                try:
                    return float(d[k])
                except Exception:
                    pass
    return None


# add this near the helpers section (above _extract_* functions)


def _extract_buying_power_from_snapshot(snapshot: dict) -> float | None:
    """
    Robustly extract cash/equity buying power (prefers cash BP).
    Works with common E*TRADE balance shapes and nested fields.
    """
    keys = (
        # common cash/equity buying power names
        "cashBuyingPower",
        "buyingPower",
        "availableFundsForTrading",
        "marginBuyingPower",
        "bp",
        # conservative fallbacks used by some responses
        "computedCashAvailableForInvestment",
        "cashAvailableForInvestment",
        "available_cash",
        "cash",
    )
    hits = _dig_numbers(snapshot, keys)
    if not hits:
        return None
    # pick a sensible positive value
    best = max([h for h in hits if h is not None and h >= 0.0] or [None])
    return best


def _normalize_settings(s):
    if isinstance(s, dict):
        merged = {**_DEFAULTS, **s}
    elif hasattr(s, "__dict__"):
        merged = {**_DEFAULTS, **s.__dict__}
    else:
        merged = dict(_DEFAULTS)
    return SimpleNamespace(**merged)


def _norm_mode(val: str | None) -> str:
    v = str(val or "SIM").strip().upper()
    aliases = {"ETRADE": "LIVE", "REAL": "LIVE", "PAPER": "SIM", "SIMULATION": "SIM"}
    v = aliases.get(v, v)
    return "LIVE" if v == "LIVE" else "SIM"


def sget(ns, key, default=None):
    return getattr(ns, key, default)


_BP_BUFFER = float(os.getenv("LIVE_BP_BUFFER", "5"))  # $ cushion to avoid GFVs


def _dig_numbers(blob: dict, key_names) -> dict:
    """Walk nested dict and collect numeric hits for any of key_names
    (case/underscore-insensitive). Returns {key_found: float_value, ...}"""

    def norm(k: str) -> str:
        return re.sub(r"[_\s]", "", str(k).lower())

    targets = {norm(k) for k in key_names}
    out = {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if norm(k) in targets:
                    try:
                        out[k] = float(v)
                    except Exception:
                        pass
                walk(v)
        elif isinstance(x, (list, tuple)):
            for it in x:
                walk(it)

    walk(blob or {})
    return out


def _fetch_account_snapshot(broker) -> dict:
    """
    Try broker.get_account_summary(); else flatten E*TRADE get_balances.
    Returns a dict containing at least {"Computed": {...}, "Cash": {...}}.
    """
    # 1) broker summary
    try:
        snap = broker.get_account_summary() or {}
        comp = snap.get("Computed") or snap.get("computed") or {}
        cash = snap.get("Cash") or snap.get("cash") or {}
        if isinstance(comp, dict) or isinstance(cash, dict):
            return {
                "Computed": comp,
                "Cash": cash,
                **{k: v for k, v in snap.items() if k not in ("Computed", "Cash")},
            }
    except Exception:
        pass

    # 2) raw balances
    try:
        et = getattr(broker, "_et", None)
        acct_id = getattr(broker, "_account_id_key", None) or getattr(
            broker, "account_id", None
        )
        if et and acct_id:
            raw = et.get_balances(acct_id) or {}
            br = raw.get("BalanceResponse", {}) or raw  # tolerate either shape
            comp = br.get("Computed") or {}
            cash = br.get("Cash") or {}
            return {"Computed": comp, "Cash": cash}
    except Exception:
        pass

    return {}


def _extract_settled_cash(acct: dict) -> float | None:
    """
    For your account, settled/usable cash maps best to Cash.moneyMktBalance,
    then Computed.netCash. Fall back only if positive.
    """
    hits = _dig_numbers(
        acct,
        [
            "moneyMktBalance",
            "netCash",
            "settledCash",
            "settledCashForInvestment",
            "cashBalance",
            "cashAvailableForInvestment",
            "computedCashAvailableForInvestment",
        ],
    )
    prefer = (
        "moneyMktBalance",
        "netCash",
        "settledCash",
        "settledCashForInvestment",
        "cashBalance",
        "cashAvailableForInvestment",
        "computedCashAvailableForInvestment",
    )
    for want in prefer:
        for k, v in hits.items():
            if (
                k.lower().replace("_", "") == want.lower().replace("_", "")
                and v is not None
                and v >= 0
            ):
                return float(v)
    return None


def _extract_buying_power(acct: dict) -> float | None:
    """
    Prefer Computed.cashBuyingPower, then marginBuyingPower, then netCash.
    """
    hits = _dig_numbers(
        acct, ["cashBuyingPower", "marginBuyingPower", "netCash", "buyingPower"]
    )
    for want in ("cashBuyingPower", "marginBuyingPower", "netCash"):
        for k, v in hits.items():
            if (
                k.lower().replace("_", "") == want.lower().replace("_", "")
                and v is not None
                and v > 0
            ):
                return float(v)
    return None


def _pool_for_sizing(settled_cash, live_bp) -> tuple[float | None, str]:
    """
    GFV-SAFE: only settled cash counts for LIVE sizing.
    No fallback to BP. If settled <= buffer, we don't buy.
    """
    if isinstance(settled_cash, (int, float)) and settled_cash > _BP_BUFFER:
        return float(settled_cash), "settled"
    return None, "settled"


def run_live_loop(settings, symbols, broker_mode=None):
    settings = _normalize_settings(settings)
    mode = _norm_mode(broker_mode or settings.broker_mode)

    # ⬇️ Force gate open in LIVE (you can still re-enable with env if you want)
    if mode == "LIVE":
        override_gate = True
    else:
        override_gate = os.getenv("LIVE_IGNORE_GUARDRAILS_TODAY", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # let env override candidate_log_limit if desired
    cand_limit = _env_int(
        "LIVE_CANDIDATE_LOG_LIMIT", sget(settings, "candidate_log_limit", -1)
    )

    # Quiet yfinance noise
    try:
        import logging as _pylog

        _pylog.getLogger("yfinance").setLevel(_pylog.ERROR)
    except Exception:
        pass

    lg.start_guardrails_auto_seller()

    broker = get_broker(mode)
    bname = (getattr(broker, "name", "") or "").upper()
    log.info(
        "🔌 Broker wired: %s (mode=%s, broker.name=%s)",
        type(broker).__name__,
        mode,
        getattr(broker, "name", None),
    )

    if mode == "LIVE" and bname in ("SIM", "PAPER", ""):
        raise RuntimeError(
            f"LIVE requested, but {type(broker).__name__} looks non-live (name={getattr(broker,'name',None)!r})."
        )

    strict_signals = getattr(settings, "strict_buy_signals", 4)
    require_sma20 = getattr(settings, "require_sma20", True)
    req = set(getattr(settings, "required_filters", []))
    total_syms = len(symbols)

    log.info(
        "[LIVE] config: strict=%d require_sma20=%s req=%s universe=%d",
        strict_signals,
        require_sma20,
        sorted(list(req)) or "[]",
        total_syms,
    )

    HEARTBEAT_SEC = float(getattr(settings, "scan_heartbeat_secs", 10.0))
    preload_history_yahoo(symbols, months=6)

    import datetime as dt
    import zoneinfo
    ET = zoneinfo.ZoneInfo("America/New_York")

    def _now_et():
        return dt.datetime.now(tz=ET)

    def _within_run_window(now: datetime) -> bool:
        # Run 08:00–23:55 ET to avoid the midnight deauth window
        start = dt.time(8, 0)
        stop  = dt.time(23, 55)
        t = now.timetz()
        return start <= t <= stop

    def _sleep_until_8am_et():
        now = _now_et()
        tomorrow = (now + dt.timedelta(days=1)).date() if now.timetz() > dt.time(23, 55) else now.date()
        wake = dt.datetime.combine(tomorrow, dt.time(8, 0), tzinfo=ET)
        return max(1, int((wake - now).total_seconds()))

    # --- replacement loop gate ---
    while True:
        now = _now_et()

        if not _within_run_window(now):
            secs = _sleep_until_8am_et()
            log.info("[LIVE] outside allowed window (08:00–23:55 ET); sleeping %ds", secs)
            time_mod.sleep(secs)
            continue

        # Only gate on REGULAR if the user asked to pause when closed
        if settings.pause_when_market_closed and settings.market_session != "EXTENDED":
            if not _is_market_open():
                wait = seconds_until_open()
                log.info("[LIVE] Market closed (REGULAR); sleeping %.1fs", wait)
                time_mod.sleep(wait)
                continue

        # ... your normal scan/buy loop ...
        time_mod.sleep(settings.scan_sleep_secs)

        iter_start = time_mod.time()
        last_ping = iter_start
        log.info("[LIVE] 🔁 Starting scan loop iteration")

        # Pre-fetch balances/account summary ONCE per iteration
        bal = {}
        try:
            bal = _fetch_account_snapshot(broker)
        except Exception as e:
            log.warning("[LIVE] account snapshot failed: %s", e)

        settled_cash = _extract_settled_cash(bal)
        live_bp = _extract_buying_power(bal)

        # --- funds log (matches the sizing pool) ---
        pool, src = _pool_for_sizing(settled_cash, live_bp)
        if mode == "LIVE":
            sc_str = (
                f"${settled_cash:.2f}"
                if isinstance(settled_cash, (int, float))
                else "None"
            )
            bp_str = f"${live_bp:.2f}" if isinstance(live_bp, (int, float)) else "None"
            log.info("[LIVE] funds: settled=%s, bp=%s (using=%s)", sc_str, bp_str, src)

        # --- candidate collection + logging budget ---
        cand_limit = sget(settings, "candidate_log_limit", None)  # env/JSON override ok

        candidates: list[tuple[str, float, list[str]]] = []
        scanned = 0
        skipped = 0
        cand_logs_emitted = 0

        # 🔁 scan the universe
        for sym in symbols:
            scanned += 1
            try:
                price, triggered, passed = analyze_symbol(sym, settings)
            except Exception as e:
                skipped += 1
                log.debug("%s: analyze_symbol failed: %s", sym, e)
                price = None
                passed = False
                triggered = None

            now = time_mod.time()
            if now - last_ping >= HEARTBEAT_SEC:
                rate = scanned / max(now - iter_start, 1e-6)
                remaining = max(total_syms - scanned, 0)
                eta = remaining / rate if rate > 0 else float("inf")
                log.info(
                    "[LIVE] progress: %d/%d scanned (%.1f/s) skipped=%d candidates=%d ETA≈%.0fs",
                    scanned,
                    total_syms,
                    rate,
                    skipped,
                    len(candidates),
                    (eta if eta != float("inf") else -1),
                )
                last_ping = now

            if not passed or price is None:
                continue

            tokens = [(t or "").strip() for t in (triggered or [])]
            tokens_lc = [t.replace(" ", "").lower() for t in tokens]
            sig_count = len(tokens)
            has_sma20 = any(
                "price>sma20" in t or "price>sma(20)" in t for t in tokens_lc
            )
            has_adx = any(t.startswith("adx") or "adx>=" in t for t in tokens_lc)
            has_macd = any("macd" in t for t in tokens_lc)
            meets_reqs = ("adx" not in req or has_adx) and (
                "macd" not in req or has_macd
            )

            if cand_limit is None or cand_limit < 0 or cand_logs_emitted < cand_limit:
                log_candidate(
                    sym, float(price), list(triggered or []), scanned, total_syms
                )
                cand_logs_emitted += 1

            if not meets_reqs:
                continue
            if require_sma20 and not has_sma20:
                continue

            candidates.append((sym, float(price), list(triggered or [])))

        elapsed = time_mod.time() - iter_start
        log.info(
            "[LIVE] summary: scanned=%d skipped=%d candidates=%d (%.1fs)",
            scanned,
            skipped,
            len(candidates),
            elapsed,
        )

        if not candidates:
            log.info("[LIVE] no candidates this round")
            time_mod.sleep(settings.poll_interval)
            continue

        def _score(sym: str, price: float, triggered: list[str]) -> float:
            return len(triggered) * 10 + price * 0.01

        ranked = sorted(candidates, key=lambda t: _score(*t), reverse=True)
        preview = ", ".join([f"{s}@{p:.2f}({len(tr)})" for s, p, tr in ranked[:5]])
        log.info(
            "[LIVE] top candidates: %s%s",
            preview or "none",
            " …" if len(ranked) > 5 else "",
        )

        trade_log = get_trades(10000)
        holdingsL = {
            s: {"qty": q, "avg_cost": ac, "last_price": lp}
            for s, q, ac, lp in get_holdings()
        }

        def _affordable_qty(px: float, max_per_trade: float) -> int:
            """
            GFV-safe: only settled cash counts. If no settled pool, return 0.
            Also respect max_per_trade as a cap, not a fallback.
            """
            if not isinstance(px, (int, float)) or px <= 0:
                return 0

            # start with zero and only size from settled pool
            cap = 0.0

            # cap by max_per_trade if provided
            try:
                if max_per_trade not in (None, "", "NONE", "None", "INF", "Inf"):
                    cap = float(max_per_trade)
                else:
                    cap = float("inf")
            except Exception:
                cap = float("inf")

            # settled-only pool
            pool, _ = _pool_for_sizing(settled_cash, live_bp)  # settled or None
            if not isinstance(pool, (int, float)):
                return 0  # no settled cash => no buy

            # take the smaller of pool buffer and max_per_trade
            cap = min(cap, pool - _BP_BUFFER)
            if cap <= 0:
                return 0

            return max(0, int(math.floor(cap / float(px))))

        # Pyramiding rules: SIM keeps t+2 by default; LIVE uses env override (default 0)
        tplus_days = _LIVE_TPLUS_DAYS if mode == "LIVE" else 2

        def _get_buy_events(sym: str):
            ev = []
            for t in trade_log or []:
                if (t.get("symbol") == sym) and (
                    str(t.get("action", "")).upper() == "BUY"
                ):
                    ts = t.get("trade_time")
                    try:
                        ts_dt = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        if ts_dt.tzinfo is None:
                            ts_dt = ts_dt.replace(tzinfo=UTC)
                    except Exception:
                        ts_dt = dt.datetime.now(UTC)

                    ev.append({
                        "time": ts_dt,
                        "price": float(t.get("price") or 0.0),
                        "qty": int(float(t.get("qty") or 0)),
                    })
            return sorted(ev, key=lambda e: e["time"])

        def _pyramid_ok(sym: str, price: float, qty: int, rules: dict[str, Any]):
            # Allow adds; no cooldown, no distance, no T+… gates, no “cash” gate.
            max_pos = int(rules.get("max_position_qty", 1_000_000))
            pos = holdingsL.get(sym, {"qty": 0})
            if (pos.get("qty", 0) + qty) > max_pos:
                return False, ["max_qty"]
            return True, []

            adds = max(len(buys) - 1, 0)
            last_fill_px = buys[-1]["price"]
            first_buy_dt = buys[0]["time"]
            last_add_dt = buys[-1]["time"]

            if adds >= rules["max_adds"]:
                reasons.append("max_adds")

            since = (datetime.now(UTC) - last_add_dt).total_seconds()
            if since < rules["min_add_interval_s"]:
                reasons.append("cooldown")

            min_px = last_fill_px * (1 + rules["min_add_distance_pct"] / 100.0)
            if price < min_px:
                reasons.append("distance")

            if rules.get("t_plus_settlement_days", 0) > 0 and pos.get("qty", 0) > 0:
                earliest_next = first_buy_dt + dt.timedelta(
                    days=rules["t_plus_settlement_days"]
                )
                if dt.datetime.now(UTC) < earliest_next:
                    reasons.append(f"t+{rules['t_plus_settlement_days']}")

            if (pos.get("qty", 0) + qty) > rules["max_position_qty"]:
                reasons.append("max_qty")

            return (len(reasons) == 0), reasons

        if not override_gate and (lg.has_bought_today() or lg.open_position_exists()):
            log.info(
                "[GR] Buy gate closed (already bought today or an open position exists)"
            )
            time_mod.sleep(settings.poll_interval)
            continue
        elif override_gate:
            log.warning(
                "[GR] TEMP OVERRIDE: ignoring guardrail ('bought today' / 'open position') for this run"
            )

        purchased = False
        for sym, price, triggered in ranked:
            if len(triggered) < strict_signals:
                continue

            max_per_trade = float("inf")
            try:
                _mpt = getattr(settings, "max_per_trade", None)
                if _mpt not in (None, "", "NONE", "None", "INF", "Inf"):
                    max_per_trade = float(_mpt)
            except Exception:
                pass

            afford_qty = _affordable_qty(price, max_per_trade)
            qty = afford_qty

            if sget(settings, "first_day_one_only", False):
                qty = min(qty, 1)

            safe_cap = sget(settings, "safe_cap_qty", None)
            if safe_cap is not None:
                try:
                    qty = min(qty, int(safe_cap))
                except (TypeError, ValueError):
                    pass

            if qty < 1 and afford_qty >= 1:
                qty = 1

            if SAFE_ON and SAFE_MAX > 0:
                qty = min(qty, SAFE_MAX)

            bp_str = f"{live_bp:.2f}" if isinstance(live_bp, (int, float)) else "None"
            sc_str = (
                f"{settled_cash:.2f}"
                if isinstance(settled_cash, (int, float))
                else "None"
            )
            mpt_str = (
                f"{max_per_trade:.1f}"
                if isinstance(max_per_trade, (int, float))
                and max_per_trade != float("inf")
                else "inf"
            )
            log.info(
                "[LIVE] considering %-6s px=%.2f afford_qty=%d settled=%s bp=%s max_per_trade=%s safe_cap=%s -> qty=%d",
                sym,
                float(price),
                afford_qty,
                sc_str,
                bp_str,
                mpt_str,
                (safe_cap if safe_cap is not None else "N/A"),
                qty,
            )

            if qty < 1:
                log.info("[LIVE] Skip %s: qty < 1", sym)
                continue

            ok, why = _pyramid_ok(
                sym,
                price,
                qty,
                {
                    "max_adds": 999999,
                    "min_add_interval_s": 0,
                    "min_add_distance_pct": 0.0,
                    "max_position_qty": 999999,
                    "t_plus_settlement_days": 0,
                },
            )
            if not ok:
                log.info("[LIVE] Blocked %s by pyramiding: %s", sym, ",".join(why))
                continue

            try:
                resp = broker.buy(sym, qty, price_type="MARKET")
                if not resp.get("ok"):
                    log.info("[LIVE] skip %s: %s", sym, resp.get("reason"))
                    continue

                log.info(
                    "[LIVE] ✅ BUY %s x%d @ %.2f via %s -> %s",
                    sym,
                    qty,
                    price,
                    getattr(broker, "name", "BROKER"),
                    resp,
                )
                if mode == "LIVE":
                    lg.record_entry(sym, qty)
                purchased = True
                break
            except Exception as e:
                log.exception("[LIVE] BUY failed for %s: %s", sym, e)

        if not purchased:
            log.info(
                "[LIVE] ranked selection found no purchasable candidates (all gated)"
            )
        time_mod.sleep(settings.poll_interval)
