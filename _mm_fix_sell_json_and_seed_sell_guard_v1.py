import json, datetime, shutil
from pathlib import Path

ROOT = Path(r"C:\TradeAlerts")

DAY  = ROOT / "sell_guard_settings_day.json"
SWING= ROOT / "sell_guard_settings_swing.json"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def backup(p: Path):
    bak = p.with_suffix(p.suffix + f".bak_seed_sell_guard_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

def load_json_lenient(p: Path):
    txt = p.read_text(encoding="utf-8", errors="replace").strip()
    # Try strict JSON first
    try:
        return json.loads(txt), txt
    except Exception:
        pass
    # Minimal lenient repair for the known SWING break:
    # - missing comma between top-level objects
    # - extra trailing junk
    # This is intentionally conservative.
    repaired = txt

    # Common issue: ... }  "stale_relief_exit": { ... }  (missing comma after sell_guard)
    repaired = repaired.replace('}\n  "stale_relief_exit"', '},\n  "stale_relief_exit"')

    # If file accidentally has multiple JSON blobs concatenated, keep first blob only
    # (rare, but we've seen it). We'll try parsing progressively.
    for cut in range(len(repaired), 0, -1):
        try:
            obj = json.loads(repaired[:cut])
            return obj, repaired[:cut]
        except Exception:
            continue
    raise SystemExit(f"ERROR: Could not parse {p} even after repair attempt")

def ensure_overlay(obj: dict):
    # Default overlay = no change multipliers (1.0)
    obj.setdefault("regime_exit_overlay", {})
    reo = obj["regime_exit_overlay"]
    for r in ["TREND","CHOP","DEAD","UNKNOWN"]:
        reo.setdefault(r, {})
        reo[r].setdefault("target_mult", 1.0)
        reo[r].setdefault("stop_mult",   1.0)
        reo[r].setdefault("time_mult",   1.0)

def seed_sell_guard(obj: dict):
    """
    Seed with Ben's remembered default sell-guard strategy:

    - Base target +0.20%, base stop -1.00%
    - After 60 min:
        if gain < +1.5% -> arm hard stop -1.0% from entry
        if gain >= +3.0% -> arm 3% trailing stop
    - Prefer EXTENDED outside RTH
    """
    sg = obj.setdefault("sell_guard", {})

    # Core execution window / loop defaults
    sg.setdefault("interval_secs", 15)
    sg.setdefault("sell_window_start_et", "09:31")
    sg.setdefault("sell_window_end_et",   "15:58")
    sg.setdefault("use_extended_hours", True)
    sg.setdefault("throttle_ms", 300)

    # Base exits
    sg.setdefault("target_gain_pct", 0.20)  # +0.20%
    sg.setdefault("base_stop_pct",   1.00)  # -1.00% (absolute pct)
    sg.setdefault("allow_intraday_stop", True)
    sg.setdefault("intraday_stop_pct", 1.00)

    # Timeout/hold
    sg.setdefault("enable_timeout_exits", True)
    sg.setdefault("min_hold_minutes", 0)
    sg.setdefault("max_hold_minutes", 240)

    # “Big winners” logic (arming rules)
    # These are neutral keys; your sell_guard.py can interpret them how you want.
    arm = sg.setdefault("arm_rules", {})
    arm.setdefault("after_minutes", 60)
    arm.setdefault("if_gain_lt_pct", 1.5)
    arm.setdefault("arm_hard_stop_pct", 1.0)     # -1.0% from entry
    arm.setdefault("if_gain_gte_pct", 3.0)
    arm.setdefault("arm_trailing_pct", 3.0)      # 3% trail

    # Trailing/protect toggles
    sg.setdefault("enable_trailing", True)
    sg.setdefault("trailing_pct", 3.0)

def write_json(p: Path, obj: dict):
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE -> {p}")

def main():
    # DAY
    if DAY.exists():
        backup(DAY)
        day_obj, _ = load_json_lenient(DAY)
    else:
        day_obj = {}

    seed_sell_guard(day_obj)
    ensure_overlay(day_obj)
    write_json(DAY, day_obj)

    # SWING
    if SWING.exists():
        backup(SWING)
        swing_obj, _ = load_json_lenient(SWING)
    else:
        swing_obj = {}

    seed_sell_guard(swing_obj)
    ensure_overlay(swing_obj)
    write_json(SWING, swing_obj)

    print("DONE. Restart dashboard, then Ctrl+F5 the SELL settings page.")

if __name__ == "__main__":
    main()