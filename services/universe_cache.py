import json
from pathlib import Path

CACHE_FILE = Path("C:/TradeAlerts/data/relvol_universe.json")

def load_cached_universe(default):
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE) as f:
                data = json.load(f)
                return data.get("symbols", default)
    except Exception:
        pass
    return default


def save_universe(symbols):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"symbols": symbols}, f)