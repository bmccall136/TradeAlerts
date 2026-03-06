import threading
from services.universe_relvol import build_relvol_universe
from services.universe_cache import save_universe

def start_universe_builder(symbols, log):

    def worker():
        try:
            log.info("[UNIVERSE] building relative-volume universe...")
            relvol = build_relvol_universe(symbols)
            save_universe(relvol)
            log.info("[UNIVERSE] relvol universe saved (%d symbols)", len(relvol))
        except Exception as e:
            log.exception("[UNIVERSE] build failed: %s", e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()