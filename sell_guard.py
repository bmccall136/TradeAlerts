from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Tuple

try:
    from zoneinfo import ZoneInfo

    ETZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ETZ = None


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

try:
    import services.etrade_service as et
except Exception as exc:  # pragma: no cover
    LOG.error("FATAL: cannot import services.etrade_service: %s", exc)
    raise SystemExit(1)

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


def fetch_positions() -> List[Dict[str, Any]]:
    """
    Fetch positions via services.etrade_service and return a flat list of rows.
    """
    res = et.positions_with_quotes()
    acct = (res or {}).get("AccountPortfolio") or []
    if not acct:
        return []
    rows: List[Dict[str, Any]] = []
    for acct_row in acct:
        for pos in acct_row.get("Position", []) or []:
            rows.append(pos)
    return rows


def fetch_open_orders() -> List[Dict[str, Any]]:
    try:
        res = et.open_orders()
        if not res:
            return []
        return (res.get("OrdersResponse") or {}).get("Order", []) or []
    except Exception as exc:
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
            response_format={"type": "json_object"},
        )
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


def parse_positions(rows: Iterable[Dict[str, Any]]) -> List[PositionRow]:
    out: List[PositionRow] = []
    for r in rows:
        sym = str(r.get("symbolDescription") or r.get("symbol") or "").strip()
        if not sym:
            continue
        qty = float(r.get("quantity", 0) or 0)
        if qty <= 0:
            continue

        mv = float(r.get("marketValue", 0) or 0)
        avg = float(r.get("pricePaid", 0) or 0)
        last_trade = float(r.get("lastTrade", 0) or 0)

        # Best-effort opened_at: use dateAcquired if present
        opened_at = None
        da = r.get("dateAcquired")
        if da:
            try:
                opened_at = datetime.fromtimestamp(da / 1000.0, tz=UTC)
            except Exception:
                opened_at = None

        out.append(
            PositionRow(
                symbol=sym,
                qty=qty,
                mv=mv,
                entry_price=avg,
                last_trade=last_trade,
                opened_at=opened_at,
            )
        )
    return out


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
    Try to place the order via services.etrade_service with a few variants,
    similar to our other adaptive placement logic.
    """
    attempts = 0
    last_err: Exception | None = None
    while attempts < max_attempts:
        attempts += 1
        try:
            LOG.info(
                "place_with_adaptive_variants attempt %d: %s qty=%s type=%s limit=%s",
                attempts,
                symbol,
                qty,
                order_type,
                limit_price,
            )
            et.place_equity_order_direct(
                acct_key,
                symbol,
                qty,
                action="SELL",
                order_type=order_type,
                limit_price=limit_price,
            )
            LOG.info("place_with_adaptive_variants success for %s", symbol)
            return
        except Exception as exc:
            last_err = exc
            LOG.warning(
                "place_with_adaptive_variants attempt %d failed for %s: %s",
                attempts,
                symbol,
                exc,
            )
            time.sleep(1.0)

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
                    sym = (
                        (o.get("Instrument") or [{}])[0]
                        .get("Product", {})
                        .get("symbol", "")
                        .strip()
                    )
                    if not sym:
                        continue
                    ot = o.get("orderTime")
                    if not ot:
                        continue
                    opened_at = datetime.fromtimestamp(ot / 1000.0, tz=UTC)
                    if sym not in open_map or opened_at < open_map[sym]:
                        open_map[sym] = opened_at
                except Exception:
                    continue

            LOG.info(
                "positions raw glimpse: %s",
                json.dumps(positions_raw[:1], default=str)[:400] + "...",
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

                opened = p.opened_at or open_map.get(s)
                if opened:
                    hold_sec = (loop_start - opened).total_seconds()
                    hold_min = max(0.0, hold_sec / 60.0)
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
        except Exception as exc:
            LOG.exception("Unexpected error in main loop: %s", exc)
            time.sleep(cfg.interval_sec)


if __name__ == "__main__":
    main()
