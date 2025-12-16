
# services/live_loop.py — BP-only sizing + no market-close pausing
from __future__ import annotations

import time, logging, math
from typing import List, Dict, Any
# --- add this block near the other imports, and remove any prior analyze_symbol import ---
try:
    from services.market_service import analyze_symbol
except ImportError:
    # fallback for older path/naming
    from services.market import analyze_symbol
from io import StringIO
LOG = logging.getLogger("live")
if not LOG.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_DEFAULTS = {
    "strict": 6,
    "require_sma20": True,
    # removed pause_when_market_closed logic
    "bp_buffer": 0.00,  # dollars to keep as safety buffer from Buying Power
    "min_qty": 1,
}
tables = pd.read_html(StringIO(resp.text))  # instead of pd.read_html(resp.text)
def _get_account_funds(broker) -> Dict[str, float]:
    """Query broker for buying power (cash account) and settled cash if available.
       Returns dict with 'bp' and 'settled' (settled may be 0 or missing)."""
    settled = 0.0
    bp = 0.0
    try:
        acct = broker.get_account_overview()
        # normalize fetch; tolerate various shapes
        settled = float(acct.get("settledCash", 0.0) or 0.0)
        # For cash accounts, buyingPower usually equals available cash for trading
        bp = float(acct.get("buyingPower", 0.0) or 0.0)
    except Exception as e:
        LOG.warning("failed to read account overview: %s", e)
    return {"bp": max(bp, 0.0), "settled": max(settled, 0.0)}

def _pool_for_sizing(funds: Dict[str, float], settings: Dict[str, Any]) -> float:
    """Use Buying Power only, minus optional buffer."""
    bp = float(funds.get("bp", 0.0))
    buf = float(settings.get("bp_buffer", _DEFAULTS["bp_buffer"]))
    pool = max(0.0, bp - max(0.0, buf))
    return pool

def _log_funds(funds: Dict[str, float], pool: float):
    LOG.info("[LIVE] funds: settled=$%.2f, bp=$%.2f (using=bp, pool=$%.2f)",
             funds.get("settled", 0.0), funds.get("bp", 0.0), pool)

def run_live_loop(settings: Dict[str, Any], symbols: List[str], broker_mode: str = "LIVE"):
    # Imports here to avoid circulars in some environments
    from services.broker import get_broker
    from services.market import analyze_symbol

    cfg = dict(_DEFAULTS)
    cfg.update(settings or {})

    broker = get_broker(mode=broker_mode)
    LOG.info("🔌 Broker wired: LiveBroker (mode=%s, broker.name=%s)", broker_mode, getattr(broker, "name", "UNKNOWN"))
    LOG.info("[LIVE] config: strict=%s require_sma20=%s req=%s universe=%d",
             cfg.get("strict"), cfg.get("require_sma20"), cfg.get("req", ['adx','macd','vol','vwap']), len(symbols))

    if not symbols:
        LOG.warning("No symbols to scan.")
        return

    # main loop (simple perpetual)
    while True:
        # funds each iteration
        funds = _get_account_funds(broker)
        pool = _pool_for_sizing(funds, cfg)
        _log_funds(funds, pool)

        # simple scan skeleton — preserve your existing logic for real system
        candidates = []
        start = time.time()
        for idx, sym in enumerate(symbols, start=1):
            try:
                sig = analyze_symbol(sym, cfg)  # your existing function: returns dict or None
                if sig and sig.get("selected"):
                    candidates.append((sym, sig))
            except Exception as e:
                # keep scanning even on symbol issues
                pass

            if idx % 30 == 0:
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed > 0 else 0.0
                eta = (len(symbols) - idx) / rate if rate > 0 else 0
                LOG.info("[LIVE] progress: %d/%d scanned (%.1f/s) candidates=%d ETA≈%ss",
                         idx, len(symbols), rate, len(candidates), int(eta))

        # rank/size example — use pool only
        if candidates:
            LOG.info("[LIVE] %d candidates found; sizing with bp-only pool=$%.2f", len(candidates), pool)
        else:
            LOG.info("[LIVE] no candidates this pass")

        # sleep a bit before next pass
        time.sleep(30)
