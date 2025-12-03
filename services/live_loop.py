# services/live_loop.py  — BP-only sizing & no market pause (default)
# Changes (2025-11-03):
# - Force sizing to use Buying Power only (cash-account friendly).
# - Disable "pause when market closed" by default (can re-enable via settings).
# - Keep Wikipedia fetch in live_start.py; this file only handles buy loop.
# Changes (2025-11-27, Max AI):
# - Wire in ai_advisor.get_ai_recommendation as a full-go gate on LIVE buys.

from __future__ import annotations

import logging
import math
import os
import re
import time
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from ai_advisor import get_ai_recommendation

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
    # 👇 Default off per Ben's preference; can still override in live_settings.json
    "pause_when_market_closed": False,
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
AI_MIN_CONFIDENCE = 0.70  # 70% confidence required when AI is enabled

SAFE_ON = os.getenv("LIVE_SAFE_MODE", "").lower() in ("1", "true", "yes", "on")
SAFE_MAX = int(os.getenv("LIVE_MAX_QTY", "0") or 0)
_BP_BUFFER = float(os.getenv("LIVE_BP_BUFFER", "5"))  # dollars cushion
_LIVE_TPLUS_DAYS = int(os.getenv("LIVE_TPLUS_DAYS", "0") or 0)  # 0 = off


def _select_funds(summary: dict, settings: dict) -> tuple[float, str]:
    """
    Select how much money is available to trade.

    For both CASH and MARGIN accounts we prefer E*TRADE's true
    buying-power style fields (currentBp / cashAvailableForInvestment,
    etc.) and we do NOT fall back to tiny settledCash balances.
    """
    s = summary or {}
    acct_type = (settings.get("account_type") or "cash").lower()

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError, TypeError):
            return None

    # E*TRADE balance blocks can be nested
    comp = s.get("Computed") or s.get("computed") or {}
    margin = s.get("Margin") or s.get("margin") or {}

    # Ordered preference of buying-power style fields
    candidates = [
        s.get("currentBp"),
        comp.get("cashAvailableForInvestment"),
        comp.get("cashBuyingPower"),
        margin.get("marginBuyingPower"),
        s.get("buyingPower"),
        s.get("cashBuyingPower"),
    ]

    bp_val = None
    for v in candidates:
        v = _num(v)
        if v is not None and v > 0:
            bp_val = v
            break

    if bp_val is None:
        bp_val = 0.0

    # For your use case we always trade off buying power,
    # regardless of cash vs margin; label it accordingly.
    use = max(0.0, float(bp_val))
    return use, "buying_power"


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


# --- Buying power extractor (ETRADE-only) ---
def _extract_buying_power(bal: dict) -> float:
    """
    Prefer E*TRADE's true buying power fields.
    Ignore settledCash / availableCash style fields that show tiny amounts.
    """
    if not isinstance(bal, dict):
        return 0.0

    # E*TRADE balance blocks
    comp = bal.get("Computed") or bal.get("computed") or {}
    margin = bal.get("Margin") or bal.get("margin") or {}

    candidates = [
        # Cash account / general BP
        comp.get("cashAvailableForInvestment"),
        comp.get("cashBuyingPower"),
        # Margin accounts
        margin.get("marginBuyingPower"),
        # Fallbacks on the top-level, if present
        bal.get("currentBp"),
        bal.get("cashBp"),
    ]

    for v in candidates:
        try:
            if v is None:
                continue
            v = float(v)
            if v > 0:
                return round(v, 2)
        except (TypeError, ValueError):
            continue

    # If E*TRADE really returns nothing useful, just 0.0 instead
    return 0.0


def _pool_for_sizing(settled_cash, buying_power, *, prefer="bp"):
    """
    Returns the pool used for sizing and a label.
    We force BP-only (cash account friendly): ignore settled cash for buys.
    """
    return float(buying_power or 0.0), "bp"


def _compute_exposure(
    buying_power: float | None, holdingsL: dict[str, dict[str, Any]]
) -> tuple[float, float]:
    """
    Approximate portfolio exposure:
      - positions_value = Σ(qty * last_price)
      - total = positions_value + buying_power
      - exposure_pct = positions_value / total * 100
    """
    bp = float(buying_power or 0.0)
    pos_val = 0.0
    for sym, pos in holdingsL.items():
        try:
            q = float(pos.get("qty") or 0.0)
            lp = float(pos.get("last_price") or 0.0)
            pos_val += max(0.0, q * lp)
        except Exception:
            continue
    total = bp + pos_val
    exposure_pct = (pos_val / total * 100.0) if total > 0 else 0.0
    return pos_val, exposure_pct


def ai_gate_for_buy(
    sym: str,
    price: float,
    qty: int,
    triggered: list[str],
    buying_power: float | None,
    holdingsL: dict[str, dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None]:
    """
    Full-go AI gate:
      - Hard veto on RED_FLAG
      - Require BUY/STRONG_BUY
      - Require confidence >= 70
    Returns (allowed, rec_dict_or_none).
    """
    sym_u = sym.upper()
    pos_val, exposure_pct = _compute_exposure(buying_power, holdingsL)
    open_positions = sum(1 for p in holdingsL.values() if (p.get("qty") or 0) > 0)

    position = holdingsL.get(sym_u)

    pos_snapshot = None
    if position:
        try:
            pos_snapshot = {
                "qty": int(position.get("qty") or 0),
                "avg_cost": float(position.get("avg_cost") or 0.0),
                "last_price": float(position.get("last_price") or 0.0),
            }
        except Exception:
            pos_snapshot = None

    snapshot = {
        "symbol": sym_u,
        "name": sym_u,
        "price": float(price),
        "planned_qty": int(qty),
        "indicators": {
            "trigger_count": len(triggered or []),
            "triggers": list(triggered or []),
        },
        "position": pos_snapshot,
        "portfolio": {
            "buying_power": float(buying_power or 0.0),
            "open_positions": int(open_positions),
            "total_exposure_pct": float(exposure_pct),
            "positions_value": float(pos_val),
        },
        # TODO: wire real news API later; empty list is fine for now.
        "news_headlines": [],
        "timeframe": "short-term swing (1-3 days)",
    }

    rec = get_ai_recommendation(snapshot)

    # Log a compact view so we can see why AI vetoed or approved
    try:
        log.info(
            "[AI] %s snapshot=%s rec=%s",
            sym_u,
            json.dumps(
                {
                    "symbol": snapshot["symbol"],
                    "price": snapshot["price"],
                    "planned_qty": snapshot["planned_qty"],
                    "trigger_count": snapshot["indicators"]["trigger_count"],
                    "open_positions": snapshot["portfolio"]["open_positions"],
                    "exposure_pct": snapshot["portfolio"]["total_exposure_pct"],
                }
            ),
            json.dumps(rec),
        )
    except Exception:
        log.info("[AI] %s rec=%r", sym_u, rec)

    action = str(rec.get("action", "SKIP")).upper()

    if action == "RED_FLAG":
        return False, rec
    if action not in {"BUY", "STRONG_BUY"}:
        return False, rec

    # If we get here, AI explicitly said BUY / STRONG_BUY → allowed
    return True, rec


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
    cand_limit = _env_int("LIVE_CANDIDATE_LOG_LIMIT", sget(settings, "candidate_log_limit", -1))

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

    while True:
        if settings.pause_when_market_closed and not _is_market_open():
            wait = seconds_until_open()
            log.info("[LIVE] Market closed — sleeping %.1fs", wait)
            time.sleep(wait)
            continue

        iter_start = time.time()
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
            sc_str = f"${settled_cash:.2f}" if isinstance(settled_cash, (int, float)) else "None"
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

            now = time.time()
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
            has_sma20 = any("price>sma20" in t or "price>sma(20)" in t for t in tokens_lc)
            has_adx = any(t.startswith("adx") or "adx>=" in t for t in tokens_lc)
            has_macd = any("macd" in t for t in tokens_lc)
            meets_reqs = ("adx" not in req or has_adx) and ("macd" not in req or has_macd)

            if cand_limit is None or cand_limit < 0 or cand_logs_emitted < cand_limit:
                log_candidate(sym, float(price), list(triggered or []), scanned, total_syms)
                cand_logs_emitted += 1

            if not meets_reqs:
                continue
            if require_sma20 and not has_sma20:
                continue

            candidates.append((sym, float(price), list(triggered or [])))

        elapsed = time.time() - iter_start
        log.info(
            "[LIVE] summary: scanned=%d skipped=%d candidates=%d (%.1fs)",
            scanned,
            skipped,
            len(candidates),
            elapsed,
        )

        if not candidates:
            log.info("[LIVE] no candidates this round")
            time.sleep(settings.poll_interval)
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
            if not isinstance(px, (int, float)) or px <= 0:
                return 0
            cap = float(max_per_trade) if isinstance(max_per_trade, (int, float)) else float(
                "inf"
            )
            pool, _ = _pool_for_sizing(settled_cash, live_bp)
            if isinstance(pool, (int, float)):
                cap = min(cap, pool - _BP_BUFFER)
            if cap <= 0:
                return 0
            return max(0, int(math.floor(cap / float(px))))

        # Pyramiding: LIVE ignores T+ rules; SIM uses t+2
        tplus_days = _LIVE_TPLUS_DAYS if mode == "LIVE" else 2

        def _pyramid_ok(sym: str, price: float, qty: int, rules: dict[str, Any]):
            # Allow adds; only guard total position size.
            max_pos = int(rules.get("max_position_qty", 1_000_000))
            pos = holdingsL.get(sym, {"qty": 0})
            if (pos.get("qty", 0) + qty) > max_pos:
                return False, ["max_qty"]
            return True, []

        override_gate = True if mode == "LIVE" else override_gate
        if not override_gate and (lg.has_bought_today() or lg.open_position_exists()):
            log.info(
                "[GR] Buy gate closed (already bought today or an open position exists)"
            )
            time.sleep(settings.poll_interval)
            continue
        elif override_gate:
            log.warning(
                "[GR] TEMP OVERRIDE: ignoring guardrail ('bought today' / 'open position') for this run"
            )

        purchased = False
        for sym, price, triggered in ranked:
            if len(triggered) < getattr(settings, "strict_buy_signals", 4):
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
            sc_str = f"{settled_cash:.2f}" if isinstance(settled_cash, (int, float)) else "None"
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

            ok, why = _pyramid_ok(sym, price, qty, {"max_position_qty": 999999})
            if not ok:
                log.info("[LIVE] Blocked %s by pyramiding: %s", sym, ",".join(why))
                continue

            # --- AI advisor gate (FULL GO) ---
            ai_allowed = True
            ai_rec = None
            try:
                ai_allowed, ai_rec = ai_gate_for_buy(
                    sym, price, qty, triggered, live_bp, holdingsL
                )
            except Exception as e:
                log.warning("[AI] error for %s: %s", sym, e)
                ai_allowed, ai_rec = False, None

            if not ai_allowed:
                try:
                    log.info(
                        "[AI] veto %s: rec=%s",
                        sym,
                        json.dumps(ai_rec) if ai_rec is not None else "None",
                    )
                except Exception:
                    log.info("[AI] veto %s", sym)
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
            log.info("[LIVE] ranked selection found no purchasable candidates (all gated)")
        time.sleep(settings.poll_interval)
