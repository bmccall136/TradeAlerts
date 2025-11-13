# services/cash_ledger.py
from __future__ import annotations
import json, os, datetime as dt
from typing import List, Dict, Any, Optional

LEDGER_PATH = os.path.abspath(r"C:\TradeAlerts\cash_ledger.json")

def _ensure_file() -> None:
    d = os.path.dirname(LEDGER_PATH)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    if not os.path.isfile(LEDGER_PATH):
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump({"events": []}, f)

def _load() -> Dict[str, Any]:
    _ensure_file()
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {"events": []}
    except Exception:
        return {"events": []}

def _save(obj: Dict[str, Any]) -> None:
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)

def add_event(amount: float, date_iso: Optional[str] = None, note: str = "") -> None:
    """
    amount > 0  => deposit (adds cash to the account)
    amount < 0  => withdrawal
    date_iso    => 'YYYY-MM-DD' in ET (optional; default = today ET)
    """
    if date_iso:
        try:
            dt.date.fromisoformat(date_iso)
        except Exception:
            raise ValueError("date_iso must be YYYY-MM-DD")
    else:
        date_iso = dt.date.today().isoformat()
    obj = _load()
    ev = {"date": date_iso, "amount": float(amount), "note": str(note or "")}
    obj.setdefault("events", []).append(ev)
    _save(obj)

def sum_net_contributions(start_date_iso: str) -> float:
    """
    Sum all amounts with date >= start_date_iso.
    Positive = deposits; negative = withdrawals.
    """
    try:
        start = dt.date.fromisoformat(start_date_iso)
    except Exception:
        return 0.0
    total = 0.0
    obj = _load()
    for ev in obj.get("events", []):
        try:
            d = dt.date.fromisoformat(str(ev.get("date") or ""))
            amt = float(ev.get("amount") or 0.0)
        except Exception:
            continue
        if d >= start:
            total += amt
    return round(total, 2)
