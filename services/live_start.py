#!/usr/bin/env python3
# live_start.py — drop-in launcher for LIVE mode
import json
import logging
import os
import sys
from dataclasses import fields

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("live_start")

# --- Paths ---
ROOT = os.path.abspath(os.path.dirname(__file__))
DEFAULT_SETTINGS = os.path.join(ROOT, "live_settings.json")
DEFAULT_SP500 = os.path.join(ROOT, "sp500_symbols.txt")  # one symbol per line


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_symbols(path: str) -> list[str]:
    # Fall back to C:\TradeAlerts\sp500_symbols.txt if relative one not found
    candidates = [
        path,
        DEFAULT_SP500,
        os.path.join("C:\\TradeAlerts", "sp500_symbols.txt"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                syms = [ln.strip().split(",")[0].upper() for ln in f if ln.strip()]
            # de-dup while preserving order
            seen, out = set(), []
            for s in syms:
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)
            return out
    raise FileNotFoundError("Could not find sp500_symbols.txt in expected locations.")


def _filter_for_dataclass(dc_type, data: dict) -> dict:
    # Keep only keys defined in the dataclass
    keys = {f.name for f in fields(dc_type)}
    return {k: v for k, v in data.items() if k in keys}


def main():
    # 1) Load LIVE settings
    settings_path = os.getenv("LIVE_SETTINGS_PATH", DEFAULT_SETTINGS)
    if not os.path.exists(settings_path):
        raise FileNotFoundError(f"live_settings.json not found at {settings_path}")

    log.info("🔧 Using live settings from %s", os.path.basename(settings_path))
    raw = _read_json(settings_path)

    # 2) Pull out broker mode (separate from SimulationSettings)
    broker_mode = str(raw.pop("broker_mode", "LIVE")).upper() or "LIVE"

    # 3) Build SimulationSettings safely
    from services.settings_schema import SimulationSettings

    data = _filter_for_dataclass(SimulationSettings, raw)
    settings = SimulationSettings(**data)

    # 4) Load symbols
    symbols_path = raw.get("symbols_path") or os.getenv("SP500_PATH") or DEFAULT_SP500
    symbols = _load_symbols(symbols_path)
    log.info("🧾 Loaded %d symbols. Preview: %s", len(symbols), symbols[:10])

    # 5) Run loop
    from services.live_loop import run_live_loop

    log.info("▶️  Starting LIVE loop")
    run_live_loop(settings, symbols, broker_mode=broker_mode)


if __name__ == "__main__":
    sys.exit(main())
