# services/live_guardrails.py
from dataclasses import dataclass
from typing import Optional, Dict
import time, math

@dataclass
class GuardCfg:
    enabled: bool = True
    base_stop_pct: float = -1.0
    target_pct: float = 0.20

    scalp_guard_enabled: bool = True
    scalp_window_sec: int = 60
    scalp_min_gain_pct: float = 0.20
    scalp_hard_stop_pct: float = -0.30

    arm_trail_after_gain_pct: float = 3.0
    trail_pct: float = 3.0

    min60_check_enabled: bool = True
    min60_check_min_gain_pct: float = 1.50
    min60_hard_stop_pct: float = -1.00

    extended_session_sells: bool = True

# runtime state per symbol
_STATE: Dict[str, Dict] = {}

def _pct(a, b):  # (current - entry) / entry * 100
    try: return (a - b) / b * 100.0
    except Exception: return 0.0

def record_entry(sym: str, qty: float, px: float, ts: Optional[float] = None):
    now = ts or time.time()
    _STATE[sym] = {
        "entry_px": float(px),
        "qty": float(qty),
        "t0": now,
        "hi": float(px),
        "trail_armed": False,
        "tp_done": False,
        "min60_checked": False
    }

def record_exit(sym: str):
    _STATE.pop(sym, None)

def check_exit_reason(sym: str, last_px: float, now: Optional[float], cfg: GuardCfg) -> Optional[Dict]:
    if not cfg.enabled: return None
    st = _STATE.get(sym)
    if not st: return None
    px = float(last_px)
    entry = st["entry_px"]
    g = _pct(px, entry)
    elapsed = (now or time.time()) - st["t0"]
    st["hi"] = max(st["hi"], px)

    # 0) Always-on base stop
    if g <= cfg.base_stop_pct:
        return {"reason": "BASE_STOP", "trigger": g, "stop_at": cfg.base_stop_pct}

    # 1) Scalp guard (first minute)
    if cfg.scalp_guard_enabled and elapsed <= cfg.scalp_window_sec:
        if g < cfg.scalp_min_gain_pct and g <= cfg.scalp_hard_stop_pct:
            return {"reason": "SCALP_STOP", "trigger": g}

    # 2) Take-profit (one-shot)
    if not st["tp_done"] and g >= cfg.target_pct:
        st["tp_done"] = True
        return {"reason": "TAKE_PROFIT", "trigger": g, "target": cfg.target_pct}

    # 3) Trailing (arm then trail off highest)
    if not st["trail_armed"] and g >= cfg.arm_trail_after_gain_pct:
        st["trail_armed"] = True
    if st["trail_armed"]:
        trail_stop = st["hi"] * (1.0 - cfg.trail_pct / 100.0)
        if px <= trail_stop:
            return {"reason": "TRAIL_STOP", "trigger": g, "trail_pct": cfg.trail_pct}

    # 4) Minute-60 sanity check
    if cfg.min60_check_enabled and not st["min60_checked"] and elapsed >= 60 * 60:
        st["min60_checked"] = True
        if g < cfg.min60_check_min_gain_pct:
            # arm a tight stop relative to entry
            if g <= cfg.min60_hard_stop_pct:
                return {"reason": "MIN60_FAIL", "trigger": g}

    return None
