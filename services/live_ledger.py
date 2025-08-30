# services/live_ledger.py
from __future__ import annotations
import json, os, time
from collections import defaultdict
from typing import Dict, List

_LEDGER_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "live_ledger.json")
os.makedirs(os.path.dirname(_LEDGER_PATH), exist_ok=True)

def _now_iso():
    import datetime as dt
    return dt.datetime.utcnow().isoformat()

def _load():
    try:
        with open(_LEDGER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"lots": {}, "trades": []}

def _save(state):
    tmp = _LEDGER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, _LEDGER_PATH)

def reset_today():
    """Erase today's trades (keeps open lots). Call if you need to clear."""
    st = _load()
    st["trades"] = []
    _save(st)

def apply_fill(fill: dict, ignore: set | None = None):
    """
    fill = {
      time: <epoch ms or iso>, symbol: "AAPL",
      action: "BUY"|"SELL", qty: int, price: float
    }
    """
    ignore = ignore or set()
    sym = (fill.get("symbol") or "").upper()
    if not sym or sym in ignore:
        return

    qty  = max(0, int(fill.get("qty") or 0))
    px   = float(fill.get("price") or 0.0)
    side = (fill.get("action") or "").upper()
    when = fill.get("time")

    st = _load()
    lots: Dict[str, List[List[float]]] = st.setdefault("lots", {})
    lots.setdefault(sym, [])  # list of [qty_remaining, cost_per_share]

    tr_price_paid = 0.0
    pl = 0.0
    pl_pct = 0.0

    if side == "BUY":
        lots[sym].append([qty, px])
        st["trades"].append({
            "time": when, "symbol": sym, "action": side, "qty": qty,
            "price": px, "price_paid": px, "pl": 0.0, "pl_pct": 0.0
        })
    elif side == "SELL":
        sell_qty = qty
        cost_used = 0.0
        qty_used  = 0

        # FIFO consume open lots
        while sell_qty > 0 and lots[sym]:
            lot_qty, lot_cost = lots[sym][0]
            take = min(sell_qty, lot_qty)
            lot_qty -= take
            if lot_qty == 0:
                lots[sym].pop(0)
            else:
                lots[sym][0][0] = lot_qty

            cost_used += lot_cost * take
            qty_used  += take
            sell_qty  -= take

        # If we didn't have any lot cost (selling prior holdings we never saw),
        # cost_used stays 0 and we'll show 0% (can't compute a basis).
        tr_price_paid = (cost_used / qty_used) if qty_used else 0.0
        pl       = (px * qty) - cost_used
        pl_pct   = ( (px - tr_price_paid) / tr_price_paid * 100.0 ) if tr_price_paid else 0.0

        st["trades"].append({
            "time": when, "symbol": sym, "action": side, "qty": qty,
            "price": px, "price_paid": tr_price_paid, "pl": round(pl, 2),
            "pl_pct": round(pl_pct, 2)
        })

    _save(st)

def summarize_today():
    st = _load()
    trades = st.get("trades") or []
    realized = sum(float(t.get("pl") or 0.0) for t in trades if (t.get("action") or "").upper() == "SELL")
    basis    = sum((float(t.get("price_paid") or 0.0) * int(t.get("qty") or 0))
                   for t in trades if (t.get("action") or "").upper() == "SELL")
    realized_pct = (realized / basis * 100.0) if basis else 0.0
    return {
        "trades": trades,
        "realized_total": round(realized, 2),
        "realized_pct": round(realized_pct, 2)
    }
