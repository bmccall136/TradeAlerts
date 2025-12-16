# ai_budget.py
#
# Super simple daily budget + throttle for AIAdvisor.
# This does NOT call OpenAI – it just tracks how often
# we are allowed to call it.

import json
import time
from datetime import date
from pathlib import Path
from typing import Literal

STATE_FILE = Path("ai_usage_state.json")

# ==== TUNE THESE NUMBERS ====
DAILY_BUDGET_USD = 10.00        # Max you’re willing to spend per day
EST_COST_PER_CALL_USD = 0.02   # Rough worst-case cost for ONE AI call
MIN_INTERVAL_SEC = 20          # Min seconds between any two AI calls
# ============================

AI_REASON = Literal["buy_entry", "sell_exit", "analysis", "generic"]


def _today_str() -> str:
    return date.today().isoformat()


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # default / reset
    return {
        "date": _today_str(),
        "spent": 0.0,
        "calls": 0,
        "last_call_ts": 0.0,
    }


def _save_state(state: dict) -> None:
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        # Never crash trading because logging failed
        pass


def _reset_if_new_day(state: dict) -> dict:
    today = _today_str()
    if state.get("date") != today:
        state = {
            "date": today,
            "spent": 0.0,
            "calls": 0,
            "last_call_ts": 0.0,
        }
    return state


def allow_ai_call(reason: AI_REASON = "generic") -> bool:
    """
    Check both:
      - daily budget (approximate)
      - min interval between calls
    """
    state = _reset_if_new_day(_load_state())
    now = time.time()

    last_ts = float(state.get("last_call_ts") or 0.0)
    if now - last_ts < MIN_INTERVAL_SEC:
        return False

    spent = float(state.get("spent") or 0.0)
    if spent + EST_COST_PER_CALL_USD > DAILY_BUDGET_USD:
        return False

    return True


def note_ai_call(actual_cost_usd: float | None = None) -> None:
    """
    Record a call. If you don’t know actual cost, leave None and we’ll
    use EST_COST_PER_CALL_USD.
    """
    state = _reset_if_new_day(_load_state())
    cost = float(actual_cost_usd) if actual_cost_usd is not None else EST_COST_PER_CALL_USD

    state["spent"] = float(state.get("spent") or 0.0) + cost
    state["calls"] = int(state.get("calls") or 0) + 1
    state["last_call_ts"] = time.time()

    _save_state(state)


def budget_summary() -> str:
    """Nice text for logs / debug."""
    state = _reset_if_new_day(_load_state())
    return (
        f"AI budget {state['date']}: "
        f"${state['spent']:.2f} used / ${DAILY_BUDGET_USD:.2f} limit, "
        f"{state['calls']} calls"
    )
