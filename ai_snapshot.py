#!/usr/bin/env python
"""
ai_snapshot.py

Quick “AI brain dump” for a trading day.

- Looks for triggers_YYYY-MM-DD.csv under:
    1) C:\TradeAlerts\logs
    2) C:\TradeAlerts
- Treats any row with one or more indicator flags == "1" as a trigger.
- Prints:
    * basic info about the file
    * indicator usage counts
    * top indicator combos
    * symbols that fired most often

Read-only. Does NOT talk to E*TRADE.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple


ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"

# Which columns to treat as indicator flags and how to label them in output
INDICATOR_COLUMNS: Dict[str, str] = {
    "MACD_up": "MACD_up",
    "VWAP_plus": "VWAP_plus",
    "BB_breakout": "BB_breakout",
    "RSI_overbought": "RSI_overbought",
    "Vol_spike": "Vol_spike",
    "ATRpct_ge": "ATRpct_ge",
    "Gap_ge": "Gap_ge",
    "Price_gt_SMA": "Price_gt_SMA",
}


@dataclass
class TriggerRow:
    timestamp: datetime
    symbol: str
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, str] = field(default_factory=dict)


def _log(msg: str) -> None:
    print(msg, flush=True)


def find_latest_triggers_file() -> Path | None:
    """
    Prefer triggers_* in C:\TradeAlerts\logs, then fall back to C:\TradeAlerts.
    """
    candidates = []

    # 1) logs directory if it exists
    if LOGS_DIR.exists():
        candidates.extend(sorted(LOGS_DIR.glob("triggers_*.csv")))

    # 2) root directory
    candidates.extend(sorted(ROOT.glob("triggers_*.csv")))

    if not candidates:
        return None

    # Use the most recently modified file
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest


def parse_triggers(path: Path) -> List[TriggerRow]:
    rows: List[TriggerRow] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                continue

            ts_raw = (row.get("timestamp") or row.get("time") or "").strip()
            if ts_raw:
                # try ISO first
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", ""))
                except Exception:
                    try:
                        ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts = datetime.min
            else:
                ts = datetime.min

            tags: List[str] = []
            for col, label in INDICATOR_COLUMNS.items():
                val = (row.get(col) or "").strip()
                if val == "1":
                    tags.append(label)

            # only care about rows where *something* fired
            if not tags:
                continue

            rows.append(TriggerRow(timestamp=ts, symbol=symbol, tags=tags, raw=row))
    return rows


def summarize(rows: List[TriggerRow]) -> Dict:
    indicator_counter: Counter[str] = Counter()
    combo_counter: Counter[Tuple[str, ...]] = Counter()
    symbol_counter: Counter[str] = Counter()

    for r in rows:
        symbol_counter[r.symbol] += 1
        for tag in r.tags:
            indicator_counter[tag] += 1
        combo_key = tuple(sorted(r.tags))
        combo_counter[combo_key] += 1

    summary = {
        "total_trigger_rows": len(rows),
        "indicators": indicator_counter.most_common(),
        "combos": [(list(k), v) for k, v in combo_counter.most_common()],
        "symbols": symbol_counter.most_common(),
    }
    return summary


def print_summary(path: Path, rows: List[TriggerRow], summary: Dict) -> None:
    _log(f"[ai_snapshot] Using trigger file: {path}")
    if not rows:
        _log("[ai_snapshot] No trigger rows with active indicators (all flags were 0).")
        return

    _log(f"[ai_snapshot] Trigger rows with ≥1 active indicator: {summary['total_trigger_rows']}")
    _log("")

    _log("Top indicators (by count):")
    for name, count in summary["indicators"][:10]:
        _log(f"  - {name:15s} {count}")

    _log("")
    _log("Top indicator combos:")
    for combo, count in summary["combos"][:10]:
        combo_label = " + ".join(combo)
        _log(f"  - {combo_label:40s} {count}")

    _log("")
    _log("Top symbols by trigger count:")
    for symbol, count in summary["symbols"][:15]:
        _log(f"  - {symbol:5s} {count}")

    # Write JSON summary for future “black box” work
    out = ROOT / "ai_snapshot_latest.json"
    data = {
        "file": str(path),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
    }
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _log("")
    _log(f"[ai_snapshot] Wrote JSON summary to {out}")


def main() -> None:
    triggers_path = find_latest_triggers_file()
    if not triggers_path:
        _log(f"[ai_snapshot] No triggers_*.csv files found in {LOGS_DIR} or {ROOT}")
        return

    rows = parse_triggers(triggers_path)
    if not rows:
        _log(f"[ai_snapshot] Using trigger file: {triggers_path}")
        _log("[ai_snapshot] No rows with active indicator flags (all zeros).")
        return

    summary = summarize(rows)
    print_summary(triggers_path, rows, summary)


if __name__ == "__main__":
    main()
