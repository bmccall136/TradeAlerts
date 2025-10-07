# trail_guard.py — simple software trailing stop that sells at market
import logging
import os
import time
from typing import Any

from services import etrade_service as es

# Your app services (already in your project)
from services.etrade_service import get_positions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s trail-guard: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("trail-guard")

TRAIL_PCT = float(os.getenv("TRAIL_PCT", "12"))  # % drop from high to trigger sell
STOP_FLOOR_PCT = float(
    os.getenv("STOP_FLOOR_PCT", "5")
)  # optional fixed stop from entry (0=off)
POLL_SECS = float(os.getenv("POLL_SECS", "3"))
SESSION = os.getenv("MARKET_SESSION", "REGULAR")  # or EXTENDED
TIF = os.getenv("ORDER_TIF", "GOOD_UNTIL_CANCEL")
BLOCK = {
    s.strip().upper()
    for s in (os.getenv("SELL_BLOCKLIST") or "").split(",")
    if s.strip()
}


def _per_share_entry(p: dict[str, Any], last_fallback: float) -> float:
    # prefer explicit avg price; else derive from costBasis/qty; else fallback to last
    qty = int(p.get("qty") or p.get("quantity") or 0)
    for k in ("price_paid", "avgPrice", "averagePrice"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except:
                pass
    cb = p.get("costBasis") or p.get("totalCost")
    try:
        if cb is not None and qty > 0:
            return float(cb) / qty
    except:
        pass
    return float(last_fallback or 0.0)


def _last_from_pos(p: dict[str, Any]) -> float:
    for k in ("last_price", "lastPrice", "mark", "last", "close"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except:
                pass
    return 0.0


def _sell_market(symbol: str, qty: int):
    if hasattr(es, "sell_market"):
        return es.sell_market(symbol, qty, session=SESSION, tif=TIF)
    if hasattr(es, "place_market_order"):
        return es.place_market_order(
            symbol=symbol, qty=qty, side="SELL", session=SESSION, term=TIF
        )
    raise RuntimeError("No sell function available in etrade_service")


def main():
    log.info(
        "started (TRAIL=%.2f%%, STOP_FLOOR=%s, poll=%.1fs, session=%s, tif=%s, blocklist=%s)",
        TRAIL_PCT,
        f"{STOP_FLOOR_PCT:.2f}%" if STOP_FLOOR_PCT > 0 else "off",
        POLL_SECS,
        SESSION,
        TIF,
        ",".join(sorted(BLOCK)) if BLOCK else "(none)",
    )

    trail_k = 1.0 - (TRAIL_PCT / 100.0)
    floor_k = 1.0 - (STOP_FLOOR_PCT / 100.0) if STOP_FLOOR_PCT > 0 else None

    state: dict[str, dict[str, float]] = {}  # symbol -> {entry, hi}
    last_sell_at: dict[str, float] = {}  # throttle per symbol

    while True:
        try:
            positions = get_positions() or []
            if not positions:
                time.sleep(POLL_SECS)
                continue

            for p in positions:
                sym = (p.get("symbol") or "").upper()
                if not sym:
                    continue
                if sym in BLOCK:
                    # throttle logging to once/min
                    now = time.time()
                    nxt = state.get(f"blk_{sym}", {}).get("t", 0)
                    if now >= nxt:
                        log.info("%s: blocked; skipping", sym)
                        state[f"blk_{sym}"] = {"t": now + 60}
                    continue

                qty = int(p.get("qty") or p.get("quantity") or 0)
                if qty <= 0:
                    continue

                last = _last_from_pos(p)
                entry = _per_share_entry(p, last)

                st = state.get(sym) or {"entry": entry, "hi": max(entry, last)}
                # update hi with new highs
                if last > (st.get("hi") or 0.0):
                    st["hi"] = last
                # if entry was unknown earlier, backfill
                if st.get("entry", 0.0) <= 0 and entry > 0:
                    st["entry"] = entry

                trigger_trail = last > 0 and last <= round(st["hi"] * trail_k, 2)
                trigger_floor = (
                    (floor_k is not None)
                    and last > 0
                    and last <= round(st["entry"] * floor_k, 2)
                )

                if trigger_trail or trigger_floor:
                    now = time.time()
                    if now - last_sell_at.get(sym, 0) >= 2.0:
                        reason = (
                            f"trail({TRAIL_PCT:.2f}%<= {round(st['hi']*trail_k,2)})"
                            if trigger_trail
                            else f"floor({STOP_FLOOR_PCT:.2f}%<= {round(st['entry']*floor_k,2)})"
                        )
                        try:
                            _sell_market(sym, qty)
                            log.warning(
                                "SOLD %s x%d @ MARKET (reason=%s last=%.2f hi=%.2f entry=%.2f)",
                                sym,
                                qty,
                                reason,
                                last,
                                st["hi"],
                                st["entry"],
                            )
                            last_sell_at[sym] = now
                        except Exception as e:
                            log.error(
                                "Sell error for %s x%d (%s): %s", sym, qty, reason, e
                            )

                state[sym] = st

            time.sleep(POLL_SECS)

        except KeyboardInterrupt:
            log.info("exiting (keyboard)")
            break
        except Exception as e:
            log.error("loop error: %s", e)
            time.sleep(max(2.0, POLL_SECS))


if __name__ == "__main__":
    main()
