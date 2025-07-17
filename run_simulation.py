#!/usr/bin/env python3
# ─── UTF-8 console logger ────────────────────────────────────────────────────
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console.setFormatter(
    logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s")
)
# Force UTF-8 on Windows consoles
try:
    console.stream.reconfigure(encoding="utf-8")
except AttributeError:
    # older Python / non-reconfigurable streams: wrap in a TextIOWrapper
    import io
    console.stream = io.TextIOWrapper(
        console.stream.buffer,
        encoding="utf-8",
        errors="replace",
        line_buffering=True
    )

logger.addHandler(console)


# (Optional) also log to console
console = logging.StreamHandler()
console.setFormatter(handler.formatter)
logger.addHandler(console)

# ─── Environment & DB setup ─────────────────────────────────────────────────
from settings import SIMULATION_DB
os.environ["ALERT_DB_PATH"] = SIMULATION_DB

# ─── Core imports ───────────────────────────────────────────────────────────
from services.trading_helpers  import (
    setup_simulation_db,
    check_if_position_open,
    enter_trade,
    check_exit_orders,
    compute_qty,
)
from services.settings_schema import (
    SimulationSettings,
    extract_simulation_settings,
)
from services.market_service   import (
    get_symbols,
    analyze_symbol,
)

# now the rest of your run_simulation logic…
def main():
    # a) Load settings from config
    cfg = json.load(open('simulation_config.json'))
    cfg.pop('timeframe', None)
    settings = extract_simulation_settings(cfg)

    # b) Load symbol list
    symbols = get_symbols(simulation=True)
    print(f"[SIM] Scanning {len(symbols)} symbols every minute…")


    # c) Hand off to the official loop
    from services.simulation_service import run_simulation_loop
    run_simulation_loop(settings)


if __name__ == "__main__":
    main()
