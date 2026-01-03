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
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from services.market_service import analyze_symbol

from ai_advisor import get_ai_recommendation

from services import live_guardrails as lg
from services.broker import get_broker
from services.scan_speedups import (
    log_candidate,
    preload_history_yahoo,
)
from services.trading_helpers import get_holdings, get_trades
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# --- HARD BLOCK: yfinance is forbidden in LIVE ---
if os.getenv("BROKER_MODE", "").upper() == "LIVE":
    import sys
    if "yfinance" in sys.modules:
        raise RuntimeError("❌ yfinance loaded in LIVE mode — this is forbidden")

log = logging.getLogger("live")
def _dbg_gate(sym: str, msg: str, *, force: bool = False):
    """
    Gate debug logger.
    Enable with:
      $env:MM_DEBUG_ALL="1"   (all symbols)
      $env:MM_DEBUG_SYMBOL="AAPL" (single symbol)
    """
    ds = (os.getenv("MM_DEBUG_SYMBOL") or "").strip().upper()
    da = (os.getenv("MM_DEBUG_ALL") or "").strip().lower() in ("1", "true", "yes", "on")
    sym_u = (sym or "").strip().upper()

    if force or da or (ds and ds == sym_u):
        log.warning("[GATE] %s %s", sym_u, msg)


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

from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# --- Wash-sale avoidance (loss re-buy block) -----------------------------------
import sqlite3
from datetime import date, timedelta

WASH_SALE_BLOCK_DAYS = int(os.getenv("WASH_SALE_BLOCK_DAYS", "31"))
WASH_SALE_ENABLED = os.getenv("WASH_SALE_ENABLED", "1").lower() in ("1", "true", "yes", "on")

def wash_sale_blocked(symbol: str, db_path: str, today: date | None = None) -> tuple[bool, str]:
    """
    Returns (blocked, reason). Block if the most recent SELL with gain < 0
    is within the last WASH_SALE_BLOCK_DAYS.
    Uses realized_trades.close_date (YYYY-MM-DD) and gain (REAL).
    """
    sym = (symbol or "").strip().upper()
    if not sym or not WASH_SALE_ENABLED:
        return (False, "")

    if today is None:
        today = date.today()
    cutoff = (today - timedelta(days=WASH_SALE_BLOCK_DAYS)).isoformat()

    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        row = cur.execute(
            """
            SELECT MAX(substr(close_date,1,10))
            FROM realized_trades
            WHERE upper(symbol)=?
              AND action='SELL'
              AND CAST(gain AS REAL) < 0
              AND substr(close_date,1,10) >= ?
            """,
            (sym, cutoff),
        ).fetchone()
        con.close()

        last_loss_date = (row[0] if row else None)
        if last_loss_date:
            return (True, f"wash-sale guard: last loss sell {last_loss_date} (block {WASH_SALE_BLOCK_DAYS}d)")
        return (False, "")
    except Exception:
        # If DB missing/locked/etc, do NOT block buys — fail open (safer operationally).
        return (False, "")

def _is_market_open(now: datetime | None = None) -> bool:
    """
    Basic market-hours gate (no holiday calendar).
    Mon–Fri, 09:30–16:00 ET.
    """
    now = now or datetime.now(tz=_ET)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 30) <= t <= dtime(16, 0)

def seconds_until_open(now: datetime | None = None) -> int:
    """
    Seconds until next 09:30 ET on a weekday (no holiday calendar).
    Returns 0 if already open.
    """
    now = now or datetime.now(tz=_ET)
    if _is_market_open(now):
        return 0

    # Move to next weekday if weekend
    while now.weekday() >= 5:
        now = now.replace(hour=12, minute=0, second=0, microsecond=0)  # midday
        now = now.fromtimestamp(now.timestamp() + 86400, tz=_ET)

    open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now > open_dt:
        # next day
        open_dt = open_dt.fromtimestamp(open_dt.timestamp() + 86400, tz=_ET)
        while open_dt.weekday() >= 5:
            open_dt = open_dt.fromtimestamp(open_dt.timestamp() + 86400, tz=_ET)

    return max(0, int((open_dt - now).total_seconds()))


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

    # Only check confidence AFTER action is approved
    conf = rec.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except Exception:
        conf = None

    if conf is None or conf < AI_MIN_CONFIDENCE:
        return False, rec

    return True, rec
    # If we get here, AI explicitly said BUY / STRONG_BUY and confidence passed
    return True, rec
def run_live_loop(settings, symbols, broker_mode=None):
    settings = _normalize_settings(settings)
    mode = _norm_mode(broker_mode or settings.broker_mode)

    # Guardrails: default ON in LIVE. Only bypass if env says so.
    override_gate = os.getenv("LIVE_IGNORE_GUARDRAILS_TODAY", "").lower() in (
        "1","true","yes","on",
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

    if mode != "LIVE":
        preload_history_yahoo(symbols, months=6)
    else:
        log.info("[LIVE] Yahoo history preload disabled (LIVE mode)")

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

        # 🔁 scan the universe
        for sym in symbols:
            scanned += 1
            try:
                res = analyze_symbol(sym, settings)

                # HARD GUARD: analyzer MUST return (price, triggered, passed)
                if not (isinstance(res, tuple) and len(res) == 3):
                    try:
                        fn = getattr(analyze_symbol, "__module__", "?") + "." + getattr(analyze_symbol, "__name__", "?")
                    except Exception:
                        fn = str(analyze_symbol)
                    log.warning("[LIVE] SKIP %s: analyze_symbol returned %r (type=%s) fn=%s",
                                sym, res, type(res).__name__, fn)
                    continue

                price, triggered, passed = res

            except Exception as e:
                log.warning("[LIVE] SKIP %s: analyze_symbol exception: %s", sym, e, exc_info=True)
                skipped += 1
                continue

            # --- heartbeat/progress (log even if not passed) ---
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

            # --- hard skips ---
            if price is None:
                log.warning("[LIVE] SKIP %s: analyze_symbol returned price=None", sym)
                skipped += 1
                continue

            if not passed:
                continue

            # --- Wash-sale avoidance ---
            try:
                live_db_path = os.path.join(ROOT, "live.db")
                blocked, why = wash_sale_blocked(sym, live_db_path)
                if blocked:
                    _dbg_gate(sym, f"BLOCK {why}", force=False)
                    continue
            except Exception:
                pass

            tokens = [(t or "").strip() for t in (triggered or [])]
            tokens_lc = [t.replace(" ", "").lower() for t in tokens]

            sma_len = int(getattr(settings, "price_sma_len", getattr(settings, "sma_length", 20)) or 20)
            has_sma = any(
                (f"price>sma{sma_len}" in t) or (f"price>sma({sma_len})" in t)
                for t in tokens_lc
            )

            has_adx  = any(t.startswith("adx") or "adx>=" in t for t in tokens_lc)
            has_macd = any("macd" in t for t in tokens_lc)
            has_vwap = any("vwap" in t for t in tokens_lc)
            has_vol  = any("vol" in t for t in tokens_lc) or any("volume" in t for t in tokens_lc)

            meets_reqs = (
                ("adx"  not in req or has_adx)  and
                ("macd" not in req or has_macd) and
                ("vwap" not in req or has_vwap) and
                ("vol"  not in req or has_vol)
            )

            if not meets_reqs:
                missing = []
                if "adx" in req and not has_adx:   missing.append("adx")
                if "macd" in req and not has_macd: missing.append("macd")
                if "vwap" in req and not has_vwap: missing.append("vwap")
                if "vol" in req and not has_vol:   missing.append("vol")
                _dbg_gate(sym, f"REQ miss={missing} tokens={tokens}", force=False)
                continue

            if require_sma20 and not has_sma:
                _dbg_gate(sym, f"SMA miss (need price>sma{sma_len}) tokens={tokens}", force=False)
                continue

            _dbg_gate(sym, f"PROMOTE candidate triggers={len(triggered or [])}", force=False)
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
            pos = holdingsL.get(sym, {"qty": 0})
            cur_qty = int(pos.get("qty", 0) or 0)

            # Conservative default: if we already hold it, do NOT add unless explicitly allowed
            if cur_qty > 0 and bool(rules.get("single_entry_only", True)):
                return False, ["single_entry_only"]

            max_pos = int(rules.get("max_position_qty", 1_000_000))
            if (cur_qty + qty) > max_pos:
                return False, ["max_position_qty"]

            return True, []

        # Guardrails bypass (ONLY if you explicitly set env var)
        bypass = os.getenv("LIVE_IGNORE_GUARDRAILS_TODAY", "").lower() in ("1", "true", "yes", "on")
        override_gate = True if bypass else False

        if not override_gate and (lg.has_bought_today() or lg.open_position_exists()):
            log.info("[GR] Buy gate closed (already bought today or an open position exists)")
            time.sleep(settings.poll_interval)
            continue
        elif override_gate:
            log.warning("[GR] BYPASS: LIVE_IGNORE_GUARDRAILS_TODAY=1 -> ignoring guardrail this run")


        purchased = False
        for sym, price, triggered in ranked:
            strict_n = getattr(settings, "strict_buy_signals", 4)
            if len(triggered) < strict_n:
                _dbg_gate(sym, f"STRICT miss triggers={len(triggered)} need>={strict_n} triggered={triggered}")
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

            # Use REAL settings (fallbacks are conservative, not infinite)
            pyr_cfg = {
                "max_position_qty": int(settings.get("max_position_qty", settings.get("max_per_trade", 25))),
                "max_pyramids": int(settings.get("max_pyramids", 1)),
                "single_entry_only": bool(settings.get("single_entry_only", True)),
            }

            ok, why = _pyramid_ok(sym, price, qty, pyr_cfg)
            if not ok:
                LOG.info("[PYRAMID BLOCK] %s qty=%s price=%s reason=%s cfg=%s", sym, qty, price, why, pyr_cfg)
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
