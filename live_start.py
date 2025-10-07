#!/usr/bin/env python3
import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("launcher")

ROOT = os.path.abspath(os.path.dirname(__file__))
SETTINGS_PATH = os.path.join(ROOT, "live_settings.json")
SYMS_PATH = os.path.join(ROOT, "sp500_symbols.txt")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_symbols(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip().split(",")[0].upper() for ln in f if ln.strip()]


def _norm_mode(v):
    v = str(v or "SIM").strip().upper()
    return "LIVE" if v in ("LIVE", "ETRADE", "REAL") else "SIM"


def main():
    log.info("▶️  Live launcher starting…")

    # Guardrails banner (optional env flags)
    log.info(
        "GUARDRAILS_ENABLED = %s", str(os.getenv("GUARDRAILS_ENABLED", "true")).lower()
    )
    log.info(
        "LIVE_SAFE_MODE     = %s", str(os.getenv("LIVE_SAFE_MODE", "true")).lower()
    )

    data = load_json(SETTINGS_PATH)
    raw_mode = data.get("broker_mode", "LIVE")
    mode = _norm_mode(os.getenv("BROKER_MODE") or raw_mode)

    from services.market_service import get_symbols

    symbols = get_symbols(SYMS_PATH)

    from services.live_loop import run_live_loop

    log.info("🔧 Using live settings from %s", SETTINGS_PATH)
    log.info("▶️  Live loop starting (mode=%s)", mode)

    # If you also pass settings as dict, run_live_loop will normalize it.
    run_live_loop(data, symbols, broker_mode=mode)


if __name__ == "__main__":
    sys.exit(main())
