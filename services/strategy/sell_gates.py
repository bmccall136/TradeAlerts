# services/strategy/sell_gates.py
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class GateConfig:
    profit_target_pct: float = 1.5     # e.g., +1.5%
    hard_stop_pct: float = -2.5        # e.g., -2.5%
    trailing_pct: float = 1.0          # trail from high by 1%
    max_spread_pct: float = 0.4        # block if spread too wide
    staleness_sec: int = 10            # quotes older than this → block
    eod_close_min: int = 5             # force exit N min before close (optional)

@dataclass
class Inputs:
    sym: str
    qty: int
    basis: float        # average cost per share
    last: float         # last trade price
    bid: Optional[float]
    ask: Optional[float]
    prev_close: Optional[float]
    ts_ms: int          # quote timestamp (UTC ms)
    et_min_to_close: Optional[int]     # minutes to close in ET
    trailing_high: Optional[float]     # persisted per-symbol during session

def decide(inputs: Inputs, cfg: GateConfig) -> Dict[str, Any]:
    """Return {'action': 'SELL'|'HOLD', 'reason': str, 'limit': float|None, 'trail_high': float}"""
    out = {"action": "HOLD", "reason": "no_gate", "limit": None, "trail_high": inputs.trailing_high or inputs.last}
    if inputs.qty <= 0 or inputs.basis <= 0 or inputs.last <= 0:
        out["reason"] = "invalid_state"; return out

    # Staleness / spread guards
    spread_ok = (inputs.bid and inputs.ask and inputs.ask > 0 and
                 100 * (inputs.ask - inputs.bid) / inputs.ask <= cfg.max_spread_pct)
    if not spread_ok:
        out["reason"] = "spread_block"; return out

    # Update trailing high
    trail_high = max(inputs.trailing_high or inputs.last, inputs.last)
    out["trail_high"] = trail_high

    pnl_pct = 100.0 * (inputs.last / inputs.basis - 1.0)

    # Hard stop
    if pnl_pct <= cfg.hard_stop_pct:
        out.update(action="SELL", reason=f"hard_stop {pnl_pct:.2f}%", limit=inputs.bid or inputs.last); return out

    # Profit target
    if pnl_pct >= cfg.profit_target_pct:
        out.update(action="SELL", reason=f"target {pnl_pct:.2f}%", limit=inputs.bid or inputs.last); return out

    # Trailing stop
    drop_from_high = 100.0 * (inputs.last / trail_high - 1.0)
    if drop_from_high <= -cfg.trailing_pct and trail_high > inputs.basis:
        out.update(action="SELL", reason=f"trailing {drop_from_high:.2f}%", limit=inputs.bid or inputs.last); return out

    # EOD exit
    if inputs.et_min_to_close is not None and inputs.et_min_to_close <= cfg.eod_close_min:
        out.update(action="SELL", reason=f"eod_exit {inputs.et_min_to_close}m", limit=inputs.bid or inputs.last); return out

    return out
