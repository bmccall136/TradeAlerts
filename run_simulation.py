import sys, io, logging
import os
import sys
import io
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

# ─── Enable UTF-8 & ANSI on Windows ─────────────────────────────────────────
os.system("")                      # enable ANSI colors on Win10+
sys.stdout.reconfigure(encoding="utf-8")

# ─── Load environment variables ──────────────────────────────────────────────
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# DEBUG: confirm E*TRADE credentials are loaded
print("E*TRADE Consumer Key:", os.getenv("CONSUMER_KEY"))

# ─── Logger setup ───────────────────────────────────────────────────────────
logger = logging.getLogger("sim")
logger.setLevel(logging.DEBUG)

# File handler: rotates daily, keeps 7 days
dir_logs = Path(__file__).parent / 'logs'
dir_logs.mkdir(exist_ok=True)
file_handler = TimedRotatingFileHandler(
    dir_logs / 'triggers.log', when='midnight', interval=1, backupCount=7
)
file_handler.setLevel(logging.INFO)
file_handler.suffix = "%Y-%m-%d"
file_formatter = logging.Formatter(
    "[%(asctime)s] %(name)s %(levelname)s: %(message)s"
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# ── Always‑UTF‑8 console handler ────────────────────────────────────────
utf8_console = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding="utf-8",
    errors="replace",
    line_buffering=True
)
console = logging.StreamHandler(utf8_console)
console.setLevel(logging.DEBUG)
console.setFormatter(
    logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s")
)
logger.addHandler(console)

# ─── Environment for simulation DB ───────────────────────────────────────────
from settings import SIMULATION_DB
os.environ["ALERT_DB_PATH"] = SIMULATION_DB

# ─── Core imports (after env & logging) ─────────────────────────────────────
from services.trading_helpers import (
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
from services.market_service import (
    get_symbols,
    analyze_symbol,
)
from services.simulation_service import (
    run_simulation_loop,
    stop_simulation,
)

# ─── Main routine ────────────────────────────────────────────────────────────
def main():
    # load simulation config
    cfg_path = Path(__file__).parent / 'simulation_config.json'
    with open(cfg_path) as f:
        cfg = json.load(f)

    # extract settings & initialize DB
    settings = extract_simulation_settings(cfg)

    setup_simulation_db()

    # start the simulation loop
    try:
        run_simulation_loop(settings)
    except KeyboardInterrupt:
        logger.info("Simulation interrupted, stopping...")
        stop_simulation()

if __name__ == '__main__':
    main()
