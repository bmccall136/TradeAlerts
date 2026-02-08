# ai_budget.py
#
# UNLIMITED mode for AIAdvisor:
# - never blocks AI calls
# - still keeps the state file + summary for visibility

import json
import time
from datetime import date
from pathlib import Path
from typing import Literal

STATE_FILE = Path(__file__).resolve().parent / "ai_usage_state.json"

# Keep these for logging only (not enforced)
DAILY_BUDGET_USD = 10_000_000.00
EST_COST_PER_CALL_USD = 0.004
MIN_INTERVAL_SEC = 0

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
    UNLIMITED: Always allow.
    (We keep the function so ai_advisor.py doesn't change.)
    """
    return True


def note_ai_call(actual_cost_usd: float | None = None) -> None:
    state = _reset_if_new_day(_load_state())
    cost = float(actual_cost_usd) if actual_cost_usd is not None else EST_COST_PER_CALL_USD

    state["spent"] = float(state.get("spent") or 0.0) + cost
    state["calls"] = int(state.get("calls") or 0) + 1
    state["last_call_ts"] = time.time()

    _save_state(state)


def budget_summary() -> str:
    state = _reset_if_new_day(_load_state())
    return (
        f"AI budget {state['date']}: "
        f"${state['spent']:.2f} used (UNLIMITED mode), "
        f"{state['calls']} calls"
    )
