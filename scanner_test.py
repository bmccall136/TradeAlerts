import logging
from services.market_service import get_symbols, analyze_symbol

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def main(simulation=False):
    syms = get_symbols(simulation=simulation)
    logger.info(f"Starting test scan of {len(syms)} symbols (no market‑hours pause)")
    logger.info(f"Running scan at {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for sym in syms:
        try:
            alert = analyze_symbol(sym)
            # No insert_alert call here; analyze_symbol does the DB insert!
        except Exception as e:
            logger.error(f"Error scanning {sym}: {e}")

if __name__ == "__main__":
    main(simulation=False)
