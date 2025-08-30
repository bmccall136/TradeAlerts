# sell_guard.py — STOP + optional trailing, JSON-driven, with blocklist + backoff
import os, json, time, sys, logging
from typing import Dict, Any, Optional, Set

# Your app services
from services.broker import get_broker
from services.etrade_service import get_positions  # use existing implementation

# ---- logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s sell-guard: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(stream=sys.stdout)]  # stdout (not stderr)
)
log = logging.getLogger("sell-guard")

# ---- tunables / constants ----
BLOCKLIST_LOG_SECS = 60.0
BACKOFF_MIN = 5.0
BACKOFF_MAX = 60.0

DEFAULTS = {
    "use_trailing_stop": False,
    "trailing_stop_pct": 3.0,
    "stop_loss_pct": 5.0,
    "take_profit_pct": 0.0,
    "poll_interval": 3.0,
    "market_session": "REGULAR",
    "order_term": "GOOD_UNTIL_CANCEL",
    "prefer_quotes": False,
    "sell_blocklist": [],

    # NEW trailing controls
    "trail_arm_gain_pct": 2.0,       # arm after +2%
    "trail_floor_to_entry": True,    # keep floor at entry once armed
    "trail_tiers": []                # e.g. [[5,6],[10,4]]
}

def load_settings(path="live_settings.json") -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
            if isinstance(data, dict):
                for k in data:
                    if k in cfg:
                        cfg[k] = data[k]
    except Exception as e:
        log.warning("failed reading %s: %s (using defaults)", path, e)

    # Optional ENV overrides
    def _f(name, d):
        v = os.getenv(name)
        if v is None: return d
        try: return float(v)
        except: return d

    def _b(name, d):
        v = (os.getenv(name) or "").strip().lower()
        if v == "": return d
        return v in ("1", "true", "yes", "on")

    cfg["use_trailing_stop"] = _b("USE_TRAILING_STOP", cfg["use_trailing_stop"])
    cfg["trailing_stop_pct"] = _f("TRAIL_PCT", cfg["trailing_stop_pct"])
    cfg["stop_loss_pct"]     = _f("STOP_LOSS_PCT", cfg["stop_loss_pct"])
    cfg["take_profit_pct"]   = _f("TAKE_PROFIT_PCT", cfg["take_profit_pct"])
    cfg["poll_interval"]     = max(0.5, min(_f("POLL_INTERVAL", cfg["poll_interval"]), 30.0))
    cfg["prefer_quotes"]     = _b("PREFER_QUOTES", cfg["prefer_quotes"])

    bl_env = os.getenv("SELL_BLOCKLIST")
    if bl_env:
        cfg["sell_blocklist"] = [x.strip().upper() for x in bl_env.split(",") if x.strip()]

    # normalize
    cfg["sell_blocklist"] = [str(x).upper() for x in cfg.get("sell_blocklist", [])]
    return cfg

def _do_sell(broker, sym: str, qty: int, reason: str, cfg: Dict[str, Any]) -> None:
    """Place a market sell via whatever API is available."""
    try:
        if hasattr(broker, "sell_market"):
            try:
                broker.sell_market(sym, qty, session=cfg["market_session"], tif=cfg["order_term"])
            except TypeError:
                broker.sell_market(sym, qty)
        elif hasattr(broker, "sell"):
            broker.sell(sym, qty)
        else:
            # try E*TRADE helper directly
            from services import etrade_service as es
            if hasattr(es, "sell_market"):
                es.sell_market(sym, qty, session=cfg["market_session"], tif=cfg["order_term"])
            elif hasattr(es, "place_market_order"):
                es.place_market_order(symbol=sym, qty=qty, side="SELL",
                                      session=cfg["market_session"], term=cfg["order_term"])
            else:
                raise AttributeError("No sell function available")
        log.warning("SOLD %s x%d @ MARKET (reason=%s)", sym, qty, reason)
    except Exception as e:
        log.error("Sell error for %s x%d (%s): %s", sym, qty, reason, e)

def main():
    cfg = load_settings()
    blockset: Set[str] = set(cfg["sell_blocklist"])

    log.info(
        "started (STOP=%.2f%%, trailing=%s %.2f%%, TP=%s, poll=%.1fs, session=%s, tif=%s, prefer_quotes=%s, blocklist=%s)",
        cfg["stop_loss_pct"],
        "on" if cfg["use_trailing_stop"] else "off",
        cfg["trailing_stop_pct"],
        f'{cfg["take_profit_pct"]:.2f}%' if cfg["take_profit_pct"] > 0 else "off",
        cfg["poll_interval"],
        cfg["market_session"],
        cfg["order_term"],
        cfg["prefer_quotes"],
        ",".join(sorted(blockset)) if blockset else "(none)",
    )

    broker = get_broker(os.getenv("MODE", "LIVE"))
    last_sell_at: Dict[str, float] = {}
    state: Dict[str, Dict[str, Any]] = {}
    blocked_log_next: Dict[str, float] = {}

    # precompute fixed stop / TP multipliers (trail handled dynamically)
    stop_k  = 1.0 - (cfg["stop_loss_pct"] / 100.0) if cfg["stop_loss_pct"] > 0 else None
    tp_k    = 1.0 + (cfg["take_profit_pct"] / 100.0) if cfg["take_profit_pct"] > 0 else None

    backoff = BACKOFF_MIN

    while True:
        try:
            positions = get_positions() or []
            if not positions:
                time.sleep(cfg["poll_interval"])
                backoff = BACKOFF_MIN
                continue

            for p in positions:
                sym = (p.get("symbol") or "").upper()
                if not sym:
                    continue

                # Blocklist throttle (log at most once/min per symbol)
                if sym in blockset:
                    now = time.time()
                    if now >= blocked_log_next.get(sym, 0):
                        log.info("%s: blocked; skipping position", sym)
                        blocked_log_next[sym] = now + BLOCKLIST_LOG_SECS
                    continue

                qty = int(p.get("qty") or p.get("quantity") or 0)
                if qty <= 0:
                    continue

                # Prices
                last = p.get("last_price") or p.get("lastPrice") or p.get("mark") or p.get("last") or 0.0
                try:
                    last = float(last or 0.0)
                except:
                    last = 0.0

                entry = p.get("price_paid") or p.get("avgPrice") or p.get("averagePrice")
                try:
                    entry = float(entry) if entry is not None else None
                except:
                    entry = None
                if entry is None:
                    cb = p.get("costBasis") or p.get("totalCost")
                    try:
                        cb = float(cb) if cb is not None else None
                    except:
                        cb = None
                    if cb is not None and qty > 0:
                        entry = cb / qty

                st = state.get(sym) or {}
                st_entry = float(entry if entry is not None else (last or 0.0))
                if "entry" not in st:
                    st["entry"] = st_entry
                    st["hi"] = st_entry
                    st["armed"] = False
                else:
                    # keep highest print seen (used once armed)
                    st["hi"] = max(float(st["hi"]), float(last))

                # -------- Trailing arming + tiers --------
                gain_pct = 0.0
                if st["entry"] > 0:
                    gain_pct = (last / st["entry"] - 1.0) * 100.0

                if cfg["use_trailing_stop"]:
                    if not st.get("armed", False) and last >= st["entry"] * (1.0 + cfg["trail_arm_gain_pct"]/100.0):
                        st["armed"] = True
                        st["hi"] = last  # start tracking from arming point
                        log.info("%s: trail armed at %.2f (+%.2f%%)", sym, last, cfg["trail_arm_gain_pct"])
                    if st["armed"]:
                        st["hi"] = max(st["hi"], last)

                # choose effective trail pct based on tiers
                eff_trail_pct = float(cfg["trailing_stop_pct"])
                for tier in cfg.get("trail_tiers", []):
                    try:
                        g, pct = float(tier[0]), float(tier[1])
                        if gain_pct >= g:
                            eff_trail_pct = min(eff_trail_pct, pct)
                    except Exception:
                        pass
                # -----------------------------------------

                fixed_stop = round(st["entry"] * stop_k, 2) if stop_k is not None else None

                trail_stop = None
                if cfg["use_trailing_stop"] and st.get("armed", False):
                    trail_k = 1.0 - (eff_trail_pct / 100.0)
                    raw_trail = st["hi"] * trail_k
                    if cfg.get("trail_floor_to_entry", True):
                        raw_trail = max(raw_trail, st["entry"])
                    trail_stop = round(raw_trail, 2)

                tp_px = round(st["entry"] * tp_k, 2) if tp_k is not None else None

                # Triggers (rate limited)
                if last > 0:
                    now = time.time()
                    if now - last_sell_at.get(sym, 0) >= 2.0:
                        if fixed_stop is not None and last <= fixed_stop:
                            _do_sell(broker, sym, qty, reason=f"stop({cfg['stop_loss_pct']:.2f}%<= {fixed_stop})", cfg=cfg)
                            last_sell_at[sym] = now
                        elif trail_stop is not None and last <= trail_stop:
                            _do_sell(broker, sym, qty, reason=f"trail({eff_trail_pct:.2f}%<= {trail_stop})", cfg=cfg)
                            last_sell_at[sym] = now
                        elif tp_px is not None and last >= tp_px:
                            _do_sell(broker, sym, qty, reason=f"take_profit(>= {tp_px})", cfg=cfg)
                            last_sell_at[sym] = now

                state[sym] = st

            time.sleep(cfg["poll_interval"])
            backoff = BACKOFF_MIN  # successful iteration

        except KeyboardInterrupt:
            log.info("exiting (keyboard)")
            break
        except Exception as e:
            log.error("loop error: %s", e)
            time.sleep(backoff)
            backoff = min(backoff * 1.5, BACKOFF_MAX)
            continue

if __name__ == "__main__":
    main()
