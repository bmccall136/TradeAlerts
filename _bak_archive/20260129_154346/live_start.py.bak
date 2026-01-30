#!/usr/bin/env python3
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys

# -----------------------------------------------------------------------------
# Emoji-safe console stream (Windows cp1252 console)
# -----------------------------------------------------------------------------
class SafeStdout:
    def write(self, s):
        try:
            sys.stdout.write(s)
        except UnicodeEncodeError:
            # Fallback: strip characters the console can't render
            safe = s.encode("ascii", "ignore").decode("ascii", errors="ignore")
            sys.stdout.write(safe)

    def flush(self):
        sys.stdout.flush()


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
_console = logging.StreamHandler(SafeStdout())
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

# Default / legacy settings file
DEFAULT_SETTINGS = os.path.join(ROOT, "live_settings.json")

# Mode-specific settings files
SETTINGS_BY_MODE = {
    "DAY": os.path.join(ROOT, "live_settings_day.json"),
    "SWING": os.path.join(ROOT, "live_settings_swing.json"),
}

LIVE_MODE_FILE = os.path.join(ROOT, "live_mode.txt")
VALID_LIVE_MODES = {"DAY", "SWING"}
LIVE_MODE_DEFAULT = "DAY"

SYMS_PATH = os.path.join(ROOT, "sp500_symbols.txt")


load_json

def load_symbols(path):
    with open(path, encoding="utf-8") as f:
        return [
            ln.strip().split(",")[0].upper()
            for ln in f
            if ln.strip()
        ]


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
        else:
            log.warning(
                "LIVE_SETTINGS_PATH=%s does not exist; falling back to mode mapping",
                env_path,
            )

    mode = _read_live_mode()
    path = SETTINGS_BY_MODE.get(mode, DEFAULT_SETTINGS)
    if not os.path.exists(path):
        log.warning(
            "Mode %s mapped to %s but it does not exist; falling back to %s",
            mode,
            path,
            DEFAULT_SETTINGS,
        )
        return DEFAULT_SETTINGS

    log.info("Mode %s → live settings from %s", mode, path)
    return path


def main():
    log.info("▶️  Live launcher starting…")

    # Guardrails banner (these env flags can still be used if you want)
    log.info(
        "GUARDRAILS_ENABLED = %s",
        str(os.getenv("GUARDRAILS_ENABLED", "true")).lower(),
    )
    log.info(
        "LIVE_SAFE_MODE     = %s",
        str(os.getenv("LIVE_SAFE_MODE", "true")).lower(),
    )

    # 1) Resolve settings path based on env + live_mode.txt
    settings_path = _resolve_settings_path()

    # 2) Load settings JSON
    data = load_json(settings_path)

    # 3) Normalize broker mode (LIVE vs SIM)
    raw_mode = data.get("broker_mode", "LIVE")
    mode = _norm_mode(os.getenv("BROKER_MODE") or raw_mode)

    from services.market_service import get_symbols

    symbols = get_symbols(SYMS_PATH)
    log.info("Scanning %d symbols from %s", len(symbols), SYMS_PATH)

    from services.live_loop import run_live_loop

    log.info("🔧 Using live settings from %s", settings_path)
    log.info("▶️  Live loop starting (mode=%s)", mode)

    run_live_loop(data, symbols, broker_mode=mode)


if __name__ == "__main__":
    sys.exit(main())
