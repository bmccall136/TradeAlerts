# services/strategy/scalp_gate.py
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ScalpCfg:
    # pure scalping: no trailing stop
    target_pct: float = 0.6        # take profit when >= +0.60%
    stop_pct: float = -0.7         # hard stop when <= -0.70%
    max_hold_min: int = 45         # optional time stop (enforced by caller)
    max_spread_pct: float = 0.35   # block if spread > this
    eod_exit_min: int = 5          # force exit this many min before close
    require_bid_ask: bool = True   # set False if you don’t parse NBBO yet

def decide(sym: str,
           qty: int,
           basis: float,
           last: float,
           bid: Optional[float] = None,
           ask: Optional[float] = None,
           et_min_to_close: Optional[int] = None,
           cfg: ScalpCfg = ScalpCfg()) -> Dict[str, Any]:
    """
    Returns: {'action': 'SELL'|'HOLD', 'reason': str, 'limit': float|None}
    """
    out = {"action": "HOLD", "reason": "no_gate", "limit": None}
    try:
        qty   = int(qty)
        basis = float(basis or 0)
        last  = float(last or 0)
        bid   = float(bid or 0) if bid is not None else None
        ask   = float(ask or 0) if ask is not None else None
    except Exception:
        out["reason"] = "bad_inputs"; return out

    if qty <= 0 or basis <= 0 or last <= 0:
        out["reason"] = "invalid_state"; return out

    if cfg.require_bid_ask and (not bid or not ask or ask <= 0 or bid <= 0):
        out["reason"] = "no_nbbo"; return out

    if bid and ask:
        spr = 100.0 * (ask - bid) / max(ask, last)
        if spr > cfg.max_spread_pct:
            out["reason"] = f"wide_spread {spr:.2f}%"; return out

    pnl_pct = 100.0 * (last / basis - 1.0)

    if pnl_pct >= cfg.target_pct:
        out.update(action="SELL", reason=f"target {pnl_pct:.2f}%", limit=bid or last); return out

    if pnl_pct <= cfg.stop_pct:
        out.update(action="SELL", reason=f"stop {pnl_pct:.2f}%", limit=bid or last); return out

    if et_min_to_close is not None and et_min_to_close <= cfg.eod_exit_min:
        out.update(action="SELL", reason=f"eod_exit {et_min_to_close}m", limit=bid or last); return out

    out["reason"] = "hold_rules_ok"
    return out
