import time
import json
import logging
from datetime import datetime
from services.market_service import get_symbols, analyze_symbol
from services.alert_service import insert_alert

# ─── Logging setup ───────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ─── Test scanner (no market‐hours gating) ───────────────────────────────────────

def main(simulation=False):
    syms = get_symbols(simulation=simulation)
    logger.info(f"Starting test scan of {len(syms)} symbols (no market‑hours pause)")
    while True:
        logger.info(f"Running scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        for sym in syms:
            try:
                alert = analyze_symbol(sym)
                if alert:
                    insert_alert(**alert)
            except Exception as e:
                logger.error(f"Error scanning {sym}: {e}")
        time.sleep(60)  # pause 1 minute between sweeps

if __name__ == "__main__":
    # pass simulation=True if you want to hit your simulation pipeline instead of live data
    main(simulation=False)
