from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Tuple
# sell_guard.py (top-ish)
from services.realized_service import insert_realized_trade

try:
    from zoneinfo import ZoneInfo

    ETZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ETZ = None

LIVE_DB = "live.db"  # adjust if your path is different


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

# Backwards-compat alias used deeper in the file
_lg = LOG

try:
    import services.etrade_service as et
except Exception as exc:  # pragma: no cover
    LOG.error("FATAL: cannot import services.etrade_service: %s", exc)
    raise SystemExit(1)
# --------------------------------------------------------------------------- #
# E*TRADE positions helper
# --------------------------------------------------------------------------- #

def get_positions_any() -> Dict[str, Any]:
    """
    Thin wrapper around et.get_positions() so the rest of the code can call
    a single helper. Returns the raw E*TRADE payload.
    """
    if et is None:
        raise RuntimeError("etrade_service import failed; et is None")

    try:
        raw = et.get_positions()
        LOG.debug(
            "get_positions_any: type=%s",
            type(raw).__name__,
        )
        return raw
    except Exception:
        LOG.exception("get_positions_any: error calling et.get_positions()")
        raise

try:
    from openai import OpenAI

    _openai_client = OpenAI()
except Exception:  # pragma: no cover
    _openai_client = None


# --------------------------------------------------------------------------- #
# Defaults / settings
# --------------------------------------------------------------------------- #


SETTINGS_FILE = os.environ.get(
    "SELL_GUARD_SETTINGS", "C:/TradeAlerts/sell_guard_settings.json"
)


@dataclass
class SellGuardConfig:
    mode: str
    interval_sec: int
    market_open: str
    market_close: str
    timezone: str
    blocklist: List[str]
    only_allow_symbol: str | None
    min_hold_minutes: float
    max_hold_minutes: float
    min_gain_pct: float
    target_gain_pct: float
    trail_arm_gain_pct: float
    trail_backoff_pct: float
    timeout_exit_pct: float
    avoid_daytrades: bool
    max_place_attempts: int
    normalize_tick: float
    allow_intraday_stoploss: bool
    market_fallback_for: List[str]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SellGuardConfig":
        return cls(
            mode=str(d.get("mode", "DAY")).upper(),
            interval_sec=int(d.get("interval_sec", 30)),
            market_open=str(d.get("market_open", "09:30")),
            market_close=str(d.get("market_close", "16:00")),
            timezone=str(d.get("timezone", "America/New_York")),
            blocklist=list(d.get("blocklist", [])),
            only_allow_symbol=d.get("only_allow_symbol"),
            min_hold_minutes=float(d.get("min_hold_minutes", 0)),
            max_hold_minutes=float(d.get("max_hold_minutes", 480)),
            min_gain_pct=float(d.get("min_gain_pct", -5.0)),
            target_gain_pct=float(d.get("target_gain_pct", 1.0)),
            trail_arm_gain_pct=float(d.get("trail_arm_gain_pct", 1.5)),
            trail_backoff_pct=float(d.get("trail_backoff_pct", 1.0)),
            timeout_exit_pct=float(d.get("timeout_exit_pct", -1.0)),
            avoid_daytrades=bool(d.get("avoid_daytrades", False)),
            max_place_attempts=int(d.get("max_place_attempts", 4)),
            normalize_tick=float(d.get("normalize_tick", 0.01)),
            allow_intraday_stoploss=bool(d.get("allow_intraday_stoploss", True)),
            market_fallback_for=list(d.get("market_fallback_for", [])),
        )


DEFAULTS: Dict[str, Any] = {
    "sell_guard": {
        "mode": "DAY",
        "interval_sec": 30,
        "market_open": "09:30",
        "market_close": "16:00",
        "timezone": "America/New_York",
        "blocklist": [],
        "only_allow_symbol": None,
        "min_hold_minutes": 0,
        "max_hold_minutes": 480,
        "min_gain_pct": -5.0,
        "target_gain_pct": 1.0,
        "trail_arm_gain_pct": 1.5,
        "trail_backoff_pct": 1.0,
        "timeout_exit_pct": -1.0,
        "avoid_daytrades": False,
        "max_place_attempts": 4,
        "normalize_tick": 0.01,
        "allow_intraday_stoploss": True,
        "market_fallback_for": [
            "SELL_STOP",
            "TIMEOUT",
        ],
    }
}


def _load_user_settings(path: str | os.PathLike[str]) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        LOG.warning("Settings file %s not found; using defaults only", path)
        return {}
    except json.JSONDecodeError as exc:
        LOG.error("Settings file %s is invalid JSON: %s", path, exc)
        raise SystemExit(1)


def merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merged[k] = merge_dict(base[k], v)
        else:
            merged[k] = v
    return merged


def load_settings() -> Dict[str, Any]:
    """
    Load settings from SELL_GUARD_SETTINGS, merged over DEFAULTS.
    """
    user = _load_user_settings(SETTINGS_FILE)
    if not isinstance(user, dict):
        raise SystemExit(f"Settings root must be an object, got {type(user)!r}")

    merged = dict(DEFAULTS)
    merged.update(user)

    # Fill defaults for nested sell_guard block
    merged.setdefault("sell_guard", {})
    merged["sell_guard"] = merge_dict(DEFAULTS["sell_guard"], merged["sell_guard"])
    return merged


def get_ai_flags(settings: Dict[str, Any]) -> tuple[bool, bool]:
    """Extract AI enablement flags from settings.

    Returns (ai_enabled, ai_use_exits).
    """
    ai = settings.get("ai") or {}
    enabled = bool(ai.get("enabled", False))
    use_exits = bool(ai.get("use_exits", True))
    return enabled, use_exits


# --------------------------------------------------------------------------- #
# E*TRADE helpers / wrappers
# --------------------------------------------------------------------------- #


def account_id_key() -> str:
    aid = et.account_id_key()
    if not aid:
        raise RuntimeError("account_id_key() returned empty")
    return aid


def fetch_positions() -> dict:
    """
    Fetch raw positions from E*TRADE and log a small snippet for debugging.
    """
    # 1) get the data
    positions_raw = get_positions_any()

    # 3) hand it back to the caller
    return positions_raw


def fetch_open_orders() -> List[Dict[str, Any]]:
    """Return a flat list of open orders from E*TRADE, or [] on error."""
    try:
        # list_open_orders() already flattens the E*TRADE response for us
        return et.list_open_orders()
    except Exception as exc:  # pragma: no cover
        LOG.warning("open_orders() failed: %s", exc)
        return []


# --------------------------------------------------------------------------- #
# AI Advisor – exits
# --------------------------------------------------------------------------- #


def ai_exit_check(
    symbol: str,
    qty: float,
    pl_pct: float,
    hold_min: float,
    entry_price: float,
    last_price: float,
) -> Dict[str, Any]:
    """
    Call AI Advisor for exit recommendation.

    Returns a dict like:
      {
        "action": "SELL" | "HOLD" | "RED_FLAG",
        "confidence": 0-100,
        "reason": "...",
        "reason_tags": ["tag1", "tag2"]
      }
    """
    if not _openai_client:
        return {"action": "HOLD", "confidence": 0, "reason": "no_client"}

    prompt = f"""
You are an intraday trading risk assistant. Evaluate whether we should EXIT a position.

Data:
- Symbol: {symbol}
- Quantity: {qty}
- Unrealized P/L: {pl_pct:.2f}%
- Hold time (minutes): {hold_min:.1f}
- Entry price: {entry_price:.2f}
- Last price: {last_price:.2f}

Respond with a concise JSON only, no extra text, like:
{{
  "action": "SELL" | "HOLD" | "RED_FLAG",
  "confidence": 0-100,
  "reason": "short explanation",
  "reason_tags": ["risk", "trend", "volatility"]
}}
"""

    try:
        resp = _openai_client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=200,
            temperature=0.1,
        )
        # Expect a JSON string back from the model
        raw = resp.output[0].content[0].text
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("AI response is not a JSON object")
        return data
    except Exception as exc:
        LOG.warning("ai_exit_check error for %s: %s", symbol, exc)
        return {"action": "HOLD", "confidence": 0, "reason": "error"}


# --------------------------------------------------------------------------- #
# Core logic
# --------------------------------------------------------------------------- #


@dataclass
class PositionRow:
    symbol: str
    qty: float
    mv: float
    entry_price: float
    last_trade: float
    opened_at: datetime | None


def parse_positions(rows) -> List[PositionRow]:
    """
    Normalize the E*TRADE PortfolioResponse into a flat list of
    PositionRow objects. Accepts either:
      - raw dict from et.positions()
      - list/iterable of position dicts (legacy behaviour)
    """
    # --- Normalize input into a list of dicts called `items` ---

    # Case 1: full E*TRADE response dict
    if isinstance(rows, dict):
        pr = rows.get("PortfolioResponse") or rows.get("portfolioResponse") or rows

        # Some responses use AccountPortfolio, some AccountPositions
        accounts = (
            pr.get("AccountPortfolio")
            or pr.get("AccountPositions")
            or []
        )

        if isinstance(accounts, dict):
            accounts = [accounts]

        items: List[Dict[str, Any]] = []
        for acct in accounts:
            pos_list = acct.get("Position") or acct.get("positions") or []
            if isinstance(pos_list, dict):
                pos_list = [pos_list]
            items.extend(pos_list)

    # Case 2: JSON string (just in case)
    elif isinstance(rows, str):
        try:
            parsed = json.loads(rows)
            return parse_positions(parsed)
        except Exception:
            LOG.error("parse_positions: got string rows; JSON decode failed")
            return []

    # Case 3: already an iterable of dicts
    else:
        try:
            items = list(rows or [])
        except TypeError:
            LOG.error("parse_positions: unsupported rows type %r", type(rows))
            return []

    holdings: List[PositionRow] = []

    for r in items:
        if not isinstance(r, dict):
            LOG.warning("parse_positions: skipping non-dict row: %r", r)
            continue

        sym = str(r.get("symbolDescription") or r.get("symbol") or "").strip()
        if not sym:
            continue

        qty = float(r.get("quantity") or 0)
        price_paid = float(r.get("pricePaid") or r.get("costPerShare") or 0)
        market_value = float(r.get("marketValue") or 0)
        total_cost = float(r.get("totalCost") or (qty * price_paid))
        total_gain = float(r.get("totalGain") or (market_value - total_cost))

        # Best effort for last trade / current price (not strictly needed since we use mv/qty first)
        try:
            last_trade = float(
                r.get("lastTrade") or r.get("price") or 0.0
            )
        except Exception:
            last_trade = 0.0

        # opened_at from dateAcquired (E*TRADE uses ms since epoch)
        opened_at = None
        ts = r.get("dateAcquired")
        if ts:
            try:
                opened_at = datetime.fromtimestamp(float(ts) / 1000.0, tz=UTC)
            except Exception:
                opened_at = None

        # Day P&L is currently unused in the PositionRow, but we keep the computation
        # in case we want to log or extend PositionRow later.
        # day_pnl = float(r.get("daysGain") or 0.0)

        holdings.append(
            PositionRow(
                symbol=sym,
                qty=qty,
                mv=market_value,
                entry_price=price_paid,
                last_trade=last_trade,
                opened_at=opened_at,
            )
        )

    return holdings


def within_session(now: datetime, cfg: SellGuardConfig) -> bool:
    """
    Return True if now is within the configured market session.
    """
    if ETZ is not None:
        now_local = now.astimezone(ETZ)
    else:  # pragma: no cover
        now_local = now

    h, m = map(int, cfg.market_open.split(":", 1))
    open_dt = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    h, m = map(int, cfg.market_close.split(":", 1))
    close_dt = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    return open_dt <= now_local <= close_dt


def normalize_price(px: float, tick: float) -> float:
    if tick <= 0:
        return px
    return round(px / tick) * tick


def compute_order_params(
    symbol: str,
    cfg: SellGuardConfig,
    *,
    kind: str = "SELL",
) -> Tuple[str, float | None]:
    """
    For now we mostly place market or stop orders; price logic is handled
    elsewhere if needed.
    """
    if kind == "SELL":
        return "MARKET", None
    return "MARKET", None


def place_with_adaptive_variants(
    acct_key: str,
    symbol: str,
    qty: float,
    order_type: str,
    limit_price: float | None,
    max_attempts: int,
) -> None:
    """
    Try to place a SELL order, retrying on transient E*TRADE errors.

    This version only uses the high-level preview_equity_order /
    place_equity_order helpers from services.etrade_service.
    It does NOT depend on any older place_equity_order_direct
    or ensure_session() helpers.
    """
    # Normalize the order type
    order_type = (order_type or "MARKET").upper()
    price_type = "MARKET" if order_type == "MARKET" else "LIMIT"

    from importlib import import_module

    et = import_module("services.etrade_service")

    attempts = 0
    last_err: Exception | None = None

    while attempts < max_attempts:
        attempts += 1
        try:
            LOG.info(
                "place_with_adaptive_variants attempt %s: %s qty=%s type=%s limit=%s",
                attempts,
                symbol,
                qty,
                order_type,
                limit_price,
            )

            # For MARKET we must not send a limit price; for LIMIT we pass it through.
            limit = None
            if price_type == "LIMIT" and limit_price is not None:
                limit = float(limit_price)

            # Use the canonical preview + place helpers from etrade_service.
            preview = et.preview_equity_order(
                acct_key,
                symbol,
                int(qty),
                limit,
                action="SELL",
                price_type=price_type,
            )
            et.place_equity_order(preview, qty=int(qty))

            LOG.info("place_with_adaptive_variants success for %s", symbol)
            return

        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc)

            # Special-case E*TRADE 1514:
            # "We did not find this security in your account for the closing order..."
            if "code': 1514" in msg or '"code": 1514' in msg:
                LOG.error(
                    "place_with_adaptive_variants: E*TRADE code 1514 for %s; "
                    "symbol/account mismatch for closing order, skipping auto-sell. Error: %s",
                    symbol,
                    msg,
                )
                # Do NOT keep retrying; just give up on this symbol for now.
                return

            LOG.warning(
                "place_with_adaptive_variants attempt %s failed for %s: %s",
                attempts,
                symbol,
                msg,
            )
            time.sleep(1.0)

    # If we get here, all attempts failed with non-1514 errors.
    raise RuntimeError(f"Failed to place order for {symbol}: {last_err}")



# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #


def main() -> None:
    LOG.info("sell_guard starting…")
    LOG.info("Using SELL_GUARD_SETTINGS=%s", SETTINGS_FILE)

    settings = load_settings()
    sg = settings.get("sell_guard", {}) or {}
    ai_enabled, ai_use_exits = get_ai_flags(settings)
    LOG.info("AI exits config: enabled=%s use_exits=%s", ai_enabled, ai_use_exits)

    cfg = SellGuardConfig.from_dict(sg)
    LOG.info("SellGuardConfig: %s", cfg)

    acct_key = account_id_key()
    LOG.info("account_id_key=%s", acct_key)

    armed_trail: Dict[str, float] = {}

    while True:
        loop_start = datetime.now(tz=UTC)

        try:
            if not within_session(loop_start, cfg):
                LOG.info(
                    "Outside market session %s–%s; sleeping %ss",
                    cfg.market_open,
                    cfg.market_close,
                    cfg.interval_sec,
                )
                time.sleep(cfg.interval_sec)
                continue

            positions_raw = fetch_positions()
            positions = parse_positions(positions_raw)
            if not positions:
                LOG.info("No positions; sleeping %ss", cfg.interval_sec)
                time.sleep(cfg.interval_sec)
                continue

            open_orders = fetch_open_orders()
            open_map: Dict[str, datetime] = {}
            for o in open_orders:
                try:
                    sym = (o.get("symbol") or "").strip()
                    if not sym:
                        continue
                    ot = o.get("orderTime")
                    if not ot:
                        continue
                    # E*TRADE generally returns ISO strings here, but be defensive
                    dt: Optional[datetime] = None
                    if isinstance(ot, (int, float)):
                        dt = datetime.fromtimestamp(ot / 1000.0, tz=UTC)
                    elif isinstance(ot, str):
                        s = ot.strip()
                        if not s:
                            continue

                        # Normalize common E*TRADE formats
                        # e.g. "2025-12-03T14:26:01.000Z" or with +0000
                        s = s.replace("Z", "+00:00")
                        if len(s) > 5 and (s[-5:].endswith("0000") and s[-5] in "+-"):
                            # "...+0000" -> "...+00:00"
                            s = s[:-5] + s[-5:-2] + ":" + s[-2:]
                        try:
                            dt = datetime.fromisoformat(s)
                        except Exception:
                            # maybe it's actually epoch ms in a string
                            if s.isdigit():
                                val = int(s)
                                # assume ms if it looks too large
                                if val > 10**11:
                                    dt = datetime.fromtimestamp(val / 1000.0, tz=UTC)
                                else:
                                    dt = datetime.fromtimestamp(val, tz=UTC)
                    if dt is None:
                        continue

                    opened_at = dt.astimezone(UTC)
                    if sym not in open_map or opened_at < open_map[sym]:
                        open_map[sym] = opened_at
                except Exception:
                    continue


            LOG.info(
                "positions raw glimpse: %s",
                json.dumps(positions_raw, default=str)[:400] + "..."
)
            LOG.info(
                "eligible final -> %s",
                [
                    (p.symbol, p.qty)
                    for p in positions
                    if p.symbol not in cfg.blocklist
                ],
            )

            for p in positions:
                s = p.symbol
                qty = p.qty
                mv = p.mv
                entry_px = p.entry_price
                last_trade = p.last_trade

                if s in cfg.blocklist:
                    LOG.info("[SKIP] %s is in blocklist", s)
                    continue

                if cfg.only_allow_symbol and s != cfg.only_allow_symbol:
                    LOG.info("[SKIP] %s not equal to only_allow_symbol=%s", s, cfg.only_allow_symbol)
                    continue

                if qty <= 0:
                    continue

                if mv and qty:
                    cur_px = mv / qty
                elif last_trade:
                    cur_px = last_trade
                else:
                    cur_px = entry_px or 0.0

                if not entry_px:
                    LOG.info("[SKIP] %s has no entry price", s)
                    continue

                pl_pct = ((cur_px - entry_px) / entry_px) * 100.0

                # Determine hold time:
                # - Prefer any explicit opened_at from the position.
                # - Fall back to earliest open order time for that symbol.
                # - BUT: if the only timestamp we have is a same-day dateAcquired
                #   (E*TRADE often uses midnight local), treat it as "new today"
                #   so we do NOT instantly timeout a fresh intraday entry.
                opened = p.opened_at or open_map.get(s)
                if opened:
                    if ETZ is not None:
                        opened_local = opened.astimezone(ETZ)
                        now_local = loop_start.astimezone(ETZ)
                    else:  # pragma: no cover
                        opened_local = opened
                        now_local = loop_start

                    if opened_local.date() < now_local.date():
                        # Prior-day (or older) position → use real age in minutes
                        hold_sec = (loop_start - opened).total_seconds()
                        hold_min = max(0.0, hold_sec / 60.0)
                    else:
                        # Same-day position → treat as "fresh" for timeout purposes.
                        # Timeouts are meant for multi-day bags; intraday exits
                        # will rely on targets, trails, stoploss, and AI exits.
                        hold_min = 0.0
                else:
                    hold_min = 0.0

                LOG.info(
                    "[HOLD] %s gain=%.2f%% hold=%.1f mins (waiting for trail/target/timeout)",
                    s,
                    pl_pct,
                    hold_min,
                )

                if hold_min < cfg.min_hold_minutes:
                    LOG.info(
                        "[HOLD] %s hold_min=%.1f < min_hold=%.1f → skipping",
                        s,
                        hold_min,
                        cfg.min_hold_minutes,
                    )
                    continue

                if hold_min > cfg.max_hold_minutes:
                    LOG.info(
                        "[TIMEOUT] %s hold_min=%.1f > max_hold=%.1f, pl=%.2f%% → exit",
                        s,
                        hold_min,
                        cfg.max_hold_minutes,
                        pl_pct,
                    )
                    pt, lim = compute_order_params(s, cfg, kind="TIMEOUT")
                    place_with_adaptive_variants(
                        acct_key,
                        s,
                        qty,
                        pt,
                        lim if pt == "LIMIT" else None,
                        cfg.max_place_attempts,
                    )
                    continue

                # --- AI emergency exit (FULL SEND) ---
                if ai_enabled and ai_use_exits:
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
                else:
                    LOG.debug(
                        "[AI_EXIT] disabled for %s (ai_enabled=%s use_exits=%s)",
                        s,
                        ai_enabled,
                        ai_use_exits,
                    )

                # Intraday stop-loss
                if cfg.allow_intraday_stoploss and pl_pct <= cfg.timeout_exit_pct:
                    LOG.info(
                        "[STOPLOSS] %s pl=%.2f%% <= timeout_exit_pct=%.2f%% → exit",
                        s,
                        pl_pct,
                        cfg.timeout_exit_pct,
                    )
                    pt, lim = compute_order_params(s, cfg, kind="SELL_STOP")
                    place_with_adaptive_variants(
                        acct_key,
                        s,
                        qty,
                        pt,
                        lim if pt == "LIMIT" else None,
                        cfg.max_place_attempts,
                    )
                    continue

                if pl_pct >= cfg.trail_arm_gain_pct:
                    prev = armed_trail.get(s)
                    new_floor = pl_pct - cfg.trail_backoff_pct
                    if prev is None or new_floor > prev:
                        armed_trail[s] = new_floor
                        LOG.info(
                            "[TRAIL_ARM] %s pl=%.2f%% arm_floor=%.2f%% (prev=%s)",
                            s,
                            pl_pct,
                            new_floor,
                            f"{prev:.2f}%" if prev is not None else "None",
                        )
                else:
                    if s in armed_trail:
                        LOG.info("[TRAIL_RESET] %s pl=%.2f%% < arm gain → disarm", s, pl_pct)
                        armed_trail.pop(s, None)

                if s in armed_trail:
                    floor = armed_trail[s]
                    if pl_pct <= floor:
                        LOG.info(
                            "[TRAIL_EXIT] %s pl=%.2f%% <= trail_floor=%.2f%% → exit",
                            s,
                            pl_pct,
                            floor,
                        )
                        pt, lim = compute_order_params(s, cfg)
                        place_with_adaptive_variants(
                            acct_key,
                            s,
                            qty,
                            pt,
                            lim if pt == "LIMIT" else None,
                            cfg.max_place_attempts,
                        )
                        armed_trail.pop(s, None)
                        continue

                if pl_pct >= cfg.target_gain_pct:
                    LOG.info(
                        "[TARGET_EXIT] %s pl=%.2f%% >= target_gain_pct=%.2f%% → exit",
                        s,
                        pl_pct,
                        cfg.target_gain_pct,
                    )
                    pt, lim = compute_order_params(s, cfg)
                    place_with_adaptive_variants(
                        acct_key,
                        s,
                        qty,
                        pt,
                        lim if pt == "LIMIT" else None,
                        cfg.max_place_attempts,
                    )
                    armed_trail.pop(s, None)
                    continue

            loop_end = datetime.now(tz=UTC)
            elapsed = (loop_end - loop_start).total_seconds()
            sleep_for = max(1.0, cfg.interval_sec - elapsed)
            LOG.info("sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)

        except KeyboardInterrupt:
            LOG.info("KeyboardInterrupt → exiting")
            break
        except Exception as e:
            # Robust logging that cannot crash
            try:
                glimpse = None
                if "positions_raw" in locals():
                    glimpse = positions_raw

                if glimpse is not None:
                    dump = json.dumps(glimpse, default=str)
                    LOG.error(
                        "Unexpected error in main loop: %s | positions_raw glimpse: %s",
                        e,
                        dump[:400] + "...",
                    )
                else:
                    LOG.error("Unexpected error in main loop (no positions_raw yet): %s", e)

            except Exception as log_err:
                # Last-ditch logging so logging itself never crashes
                LOG.error(
                    "Unexpected error in main loop AND while logging (%s): %s",
                    log_err,
                    e,
                )

            time.sleep(cfg.interval_sec)


if __name__ == "__main__":
    main()
