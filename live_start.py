#!/usr/bin/env python3
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Small JSON helper for live_start
# -----------------------------------------------------------------------------
def load_json(path, default=None):
    """
    Load JSON from `path`. If file is missing or invalid, return `default`.
    """
    try:
        p = Path(path)
        if not p.exists():
            print(f"[live_start] {p} not found, using default")
            return default
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[live_start] ERROR reading {path}: {e}")
        return default


# -----------------------------------------------------------------------------
# Emoji-safe console stream (Windows cp1252 console)
# -----------------------------------------------------------------------------
class SafeStdout:
    """
    Wrap an underlying stream and strip non-ascii only if the console can't render.
    This avoids recursion if sys.stdout ever gets reassigned.
    """
    def __init__(self, stream):
        self._stream = stream

    def write(self, s):
        try:
            self._stream.write(s)
        except UnicodeEncodeError:
            safe = s.encode("ascii", "ignore").decode("ascii", errors="ignore")
            self._stream.write(safe)

    def flush(self):
        self._stream.flush()


# -----------------------------------------------------------------------------
# Logging: console + rotating file (logs/live.log)
# -----------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "live.log")

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()

_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

# Console handler (emoji-safe)
_console = logging.StreamHandler(SafeStdout(sys.stdout))
_console.setFormatter(_fmt)
root_logger.addHandler(_console)

# File handler (UTF-8, rotating)
_file = RotatingFileHandler(
    LOG_PATH,
    maxBytes=5_000_000,
    backupCount=5,
    encoding="utf-8",
)
_file.setFormatter(_fmt)
root_logger.addHandler(_file)

log = logging.getLogger("launcher")

# -----------------------------------------------------------------------------
# Paths / helpers
# -----------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.dirname(__file__))

DEFAULT_SETTINGS = os.path.join(ROOT, "live_settings.json")

SETTINGS_BY_MODE = {
    "DAY": os.path.join(ROOT, "live_settings_day.json"),
    "SWING": os.path.join(ROOT, "live_settings_swing.json"),
}

LIVE_MODE_FILE = os.path.join(ROOT, "live_mode.txt")
VALID_LIVE_MODES = {"DAY", "SWING"}
LIVE_MODE_DEFAULT = "DAY"

SYMS_PATH = os.path.join(ROOT, "sp500_symbols.txt")


def load_symbols(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip().split(",")[0].upper() for ln in f if ln.strip()]


def _norm_mode(v):
    v = str(v or "SIM").strip().upper()
    return "LIVE" if v in ("LIVE", "ETRADE", "REAL") else "SIM"


def _read_live_mode() -> str:
    """Read DAY/SWING from live_mode.txt, with a safe default."""
    try:
        with open(LIVE_MODE_FILE, encoding="utf-8") as f:
            text = f.read().strip().upper()
        if text in VALID_LIVE_MODES:
            return text
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("live_mode: failed to read %s: %s", LIVE_MODE_FILE, exc)
    return LIVE_MODE_DEFAULT


def _resolve_settings_path() -> str:
    """
    Decide which live_settings*.json to use:

    1) If LIVE_SETTINGS_PATH env is set and exists -> use it.
    2) Else look at live_mode.txt (DAY/SWING) and choose
       live_settings_day.json or live_settings_swing.json.
    3) If that file is missing, fall back to live_settings.json.
    """
    env_path = os.getenv("LIVE_SETTINGS_PATH")
    if env_path:
        if os.path.exists(env_path):
            log.info("Using LIVE_SETTINGS_PATH from env: %s", env_path)
            return env_path
        log.warning("LIVE_SETTINGS_PATH=%s does not exist; falling back to mode mapping", env_path)

    mode = _read_live_mode()
    path = SETTINGS_BY_MODE.get(mode, DEFAULT_SETTINGS)
    if not os.path.exists(path):
        log.warning("Mode %s mapped to %s but it does not exist; falling back to %s", mode, path, DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

    log.info("Mode %s → live settings from %s", mode, path)
    return path


def main():
    log.info("▶️  Live launcher starting…")

    # Banner (env flags can still be used)
    log.info("GUARDRAILS_ENABLED = %s", str(os.getenv("GUARDRAILS_ENABLED", "true")).lower())
    log.info("LIVE_SAFE_MODE     = %s", str(os.getenv("LIVE_SAFE_MODE", "true")).lower())

    settings_path = _resolve_settings_path()
    data = load_json(settings_path, default={}) or {}

    raw_mode = data.get("broker_mode", "LIVE")
    mode = _norm_mode(os.getenv("BROKER_MODE") or raw_mode)

    base_symbols = load_symbols(SYMS_PATH)

    from services.universe_cache import load_cached_universe
    symbols = load_cached_universe(base_symbols)

    log.info("Universe loaded: %d symbols (base=%d)", len(symbols), len(base_symbols))
    log.info("Scanning %d symbols from %s", len(symbols), SYMS_PATH)

    from services.universe_builder import start_universe_builder
    start_universe_builder(base_symbols, log)

    from services.live_loop import run_live_loop

    log.info("🔧 Using live settings from %s", settings_path)
    log.info("▶️  Live loop starting (mode=%s)", mode)

    run_live_loop(data, symbols, broker_mode=mode)


if __name__ == "__main__":
    sys.exit(main())
