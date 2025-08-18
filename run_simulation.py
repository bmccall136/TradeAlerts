import os
import sys
import io
import logging
import json                      # ← add this (or move it up if it’s below your main)
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv
import os, ctypes
from services.trading_helpers import setup_simulation_db
from services.trading_helpers import fetch_intraday_vwap

# before any get_cash()/buy()/sell() calls:
setup_simulation_db()

# switch Windows console into UTF‑8 mode
os.system('chcp 65001 > nul')                 # simpler, fires off "chcp 65001"
ctypes.windll.kernel32.SetConsoleOutputCP(65001)
ctypes.windll.kernel32.SetConsoleCP(65001)

# ─── Enable UTF‑8 on stdout & stderr ───────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
utf8_out = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

# ─── Logger setup (only here!) ─────────────────────────────────────────────
logger = logging.getLogger("sim")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    console_fmt = logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    console = logging.StreamHandler(utf8_out)
    console.setLevel(logging.DEBUG)
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    dir_logs = Path(__file__).parent / "logs"
    dir_logs.mkdir(exist_ok=True)
    fh = TimedRotatingFileHandler(
        dir_logs / "triggers.log", when="midnight", interval=1, backupCount=7
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(console_fmt)
    logger.addHandler(fh)

# ─── Load .env & print consumer key ────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")
logger.debug(f"E*TRADE Consumer Key: {os.getenv('CONSUMER_KEY')}")

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
from services.settings_schema import SimulationSettings, extract_simulation_settings
from services.market_service import get_symbols, analyze_symbol
from services.simulation_service import run_simulation_loop, stop_simulation

# ─── Main routine ────────────────────────────────────────────────────────────
def main():
    # load simulation config
    cfg_path = Path(__file__).parent / 'simulation_config.json'
    with open(cfg_path) as f:
        cfg = json.load(f)
    print("Loaded config:", cfg)

    # extract settings & initialize DB
    settings = extract_simulation_settings(cfg)

    setup_simulation_db()

    # start the simulation loop
    try:
        run_simulation_loop(settings)
        logger.info(f"[SIM] using min_signals = {settings.min_signals}")

    except KeyboardInterrupt:
        print("Simulation interrupted by user.")

if __name__ == "__main__":
    main()
