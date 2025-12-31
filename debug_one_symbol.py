import json
import os
import sys

def load_settings():
    path = os.environ.get("LIVE_SETTINGS", r"C:\TradeAlerts\live_settings_day.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_one_symbol.py <SYMBOL>")
        raise SystemExit(2)

    sym = sys.argv[1].strip().upper()
    settings = load_settings()

    from services import market_service as ms  # <-- THIS is what you’re missing

    print(f"[OK] Imported services.market_service")
    print(f"[RUN] analyze_symbol({sym}) using LIVE_SETTINGS={os.environ.get('LIVE_SETTINGS')}")

    result = ms.analyze_symbol(sym, settings)
    print("\n[RESULT]")
    print(result)

if __name__ == "__main__":
    main()
