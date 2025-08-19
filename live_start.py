# live_start.py
import os, json, time
from pathlib import Path
from datetime import datetime, time as dtime

# --- imports from your project ---
from services.live_loop import run_live_loop
from services.market_service import get_symbols

# try to use your existing market-hours helper; fall back if missing
try:
    from services.simulation_service import _is_market_open as market_open_now
except Exception:
    import pytz
    def market_open_now():
        et = pytz.timezone("America/New_York")
        now = datetime.now(et)
        if now.weekday() >= 5:  # Sat/Sun
            return False
        return dtime(9, 30) <= now.time() <= dtime(16, 0)

# ---- settings path (env overrideable) ----
# Use LIVE_SETTINGS_FILE if set; otherwise fall back to simulation_config.json
SETTINGS_FILE = os.environ.get("LIVE_SETTINGS_FILE", "simulation_config.json")
settings_path = Path(SETTINGS_FILE)
print("🔧 Using live settings from", settings_path)

# ---- load settings (optional for run_live_loop) ----
settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  Failed to read {settings_path}: {e}")

# ---- load symbols ----
symbols = get_symbols(simulation=False) or []
print(f"🧾 Loaded {len(symbols)} symbols. Preview: {symbols[:10]}")

# ---- wait for market hours ----
if not market_open_now():
    print("⏸️  Market is closed. Waiting until open (checks every 60s)…")
    while not market_open_now():
        time.sleep(60)

print("▶️  Market open — starting live loop")

# ---- start live loop ----
# Support both possible function signatures.
try:
    # common signature: (settings, symbols)
    run_live_loop(settings, symbols)
except TypeError:
    try:
        # alt: keyword args
        run_live_loop(settings=settings, symbols=symbols)
    except TypeError:
        # alt: symbols only
        run_live_loop(symbols)
