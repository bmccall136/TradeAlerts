# services/live_service.py  (or scanner.py)
from services.log_utils import log_trigger
from pathlib import Path
from datetime import date
import csv, os, time
from typing import Dict, Any

CSV_PATH = Path(r"C:\TradeAlerts\logs") / f"triggers_{date.today():%Y-%m-%d}.csv"
FIELDNAMES = [
    "timestamp","symbol","price",
    "ADX","ATR_val","ATR_pct","Supertrend",
    "RSI","MACD","BB_breakout","Vol_mult","VWAP_diff_pct",
    "ATR_ge","ATRpct_ge","Range_ge","Gap_ge","Price_gt_SMA",
    "signals"
]

def _need_header(p: Path) -> bool:
    return (not p.exists()) or p.stat().st_size == 0

def log_trigger(row: Dict[str, Any]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = _need_header(CSV_PATH)
    # newline='' for Windows; buffering=1 for line-buffered
    with open(CSV_PATH, "a", encoding="utf-8", newline="", buffering=1) as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            w.writeheader()
        row = dict(row)
        row.setdefault("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
        sigs = row.get("signals")
        if isinstance(sigs, (list, tuple)):
            row["signals"] = ", ".join(map(str, sigs))
        w.writerow(row)
        f.flush()

def log_heartbeat(status: str, extra: Dict[str, Any] | None = None) -> None:
    row = {"symbol": "_HEARTBEAT", "price": "", "signals": [status]}
    if extra: row.update(extra)
    log_trigger(row)

def emit_live_alert(sym, price, metrics):
    # ... your signal calc up here ...
    log_trigger({
        "symbol": sym,
        "price": float(price),
        "ADX": metrics.adx,
        "ATR_val": metrics.atr, "ATR_pct": metrics.atr_pct,
        "Supertrend": metrics.supertrend,
        "RSI": metrics.rsi, "MACD": metrics.macd_cross, "BB_breakout": metrics.bb_breakout,
        "Vol_mult": metrics.vol_mult, "VWAP_diff_pct": metrics.vwap_diff_pct,
        "ATR_ge": metrics.atr_ok, "ATRpct_ge": metrics.atr_pct_ok,
        "Range_ge": metrics.range_ok, "Gap_ge": metrics.gap_ok,
        "Price_gt_SMA": metrics.price_gt_sma,
        "signals": metrics.active_signals,  # list
    })
    # then your existing: insert_alert(...), maybe buy_live(...), etc.
