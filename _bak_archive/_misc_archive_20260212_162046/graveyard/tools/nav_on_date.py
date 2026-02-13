# tools/nav_on_date.py
# Reconstruct NAV on a given date from merged trades (no broker API calls).
# - Timezone: America/New_York (ET)
# - Cash = sum(sells) - sum(buys) up to cutoff (ignores fees)
# - Positions valued at last seen trade price at/before cutoff (fallback avg)
# - Excludes GEVO sells by default (toggle with --include-gevo)

from __future__ import annotations

import sys
import argparse
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import datetime as dt
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    # crude fallback if zoneinfo missing
    ET = dt.timezone(dt.timedelta(hours=-5))

# --- Project import: merged trades ---
try:
    from services.trade_source import load_trades_merged
except Exception as e:
    print(f"[FATAL] Could not import services.trade_source.load_trades_merged: {e}", file=sys.stderr)
    sys.exit(2)


# ---------------------- Helpers ----------------------
@dataclass
class Pos:
    qty: float = 0.0
    avg: float = 0.0
    last: Optional[float] = None

    def buy(self, q: float, px: float) -> None:
        total_cost = self.avg * self.qty + px * q
        self.qty = round(self.qty + q, 8)
        self.avg = (total_cost / self.qty) if self.qty else 0.0
        self.last = px

    def sell(self, q: float, px: float) -> None:
        self.qty = round(self.qty - q, 8)
        if self.qty < 1e-8:
            self.qty = 0.0
        self.last = px


def num(x, default=0.0) -> float:
    try:
        if x is None: return float(default)
        if isinstance(x, (int, float)): return float(x)
        if isinstance(x, str):
            x = x.replace(",", "").replace("$", "").strip()
            return float(x) if x else float(default)
        return float(x)
    except Exception:
        return float(default)


def pretty_money(x: float) -> str:
    return f"${x:,.2f}"


def parse_trade_time(t: dict) -> Optional[dt.datetime]:
    """
    Prefer time_ms (epoch ms). Fallback to 'YYYY-MM-DD HH:MM:SS' (ET) or ISO with T.
    Returns tz-aware ET datetime or None.
    """
    ms = t.get("time_ms")
    if ms is not None:
        try:
            return dt.datetime.fromtimestamp(num(ms) / 1000.0, tz=ET)
        except Exception:
            pass

    s = str(t.get("time") or "").strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        except Exception:
            pass
    return None


def cutoff_range_for_date(d: dt.date) -> Tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=ET)
    end   = dt.datetime(d.year, d.month, d.day, 23, 59, 59, 999000, tzinfo=ET)
    return start, end


# ---------------------- Core replay ----------------------
def replay_positions_and_cash(trades: List[dict],
                              cutoff_end: dt.datetime,
                              exclude_gevo: bool = True,
                              debug: bool = False) -> Tuple[Dict[str, Pos], float]:
    """
    Returns (positions_map, cash) at cutoff_end.
    cash: sells add, buys subtract.
    """
    positions: Dict[str, Pos] = {}
    cash: float = 0.0

    # sort by time ascending, stable
    decorated = []
    for t in trades:
        tdt = parse_trade_time(t)
        if tdt is None:
            continue
        decorated.append((tdt, t))
    decorated.sort(key=lambda x: x[0])

    for tdt, t in decorated:
        if tdt > cutoff_end:
            break

        sym = str(t.get("symbol") or "").upper()
        if not sym:
            continue

        action = (t.get("action") or "").upper()
        qty = num(t.get("qty"), 0.0)
        px  = num(t.get("price"), None)
        if qty <= 0 or px is None or not math.isfinite(px):
            # not enough info to account
            continue

        # initialize
        p = positions.get(sym) or Pos()
        if action == "BUY":
            p.buy(qty, px)
            positions[sym] = p
            cash -= qty * px

        elif action == "SELL":
            # optional GEVO exclusion from realized cash
            if not (exclude_gevo and sym == "GEVO"):
                cash += qty * px
            # reduce position
            p.sell(qty, px)
            positions[sym] = p

        else:
            # unknown action; ignore
            continue

        if debug:
            print(f"[DBG] {tdt} {action} {sym} x{qty} @ {px:.4f} → cash={cash:.2f}, pos={p}")

    # prune zero qty
    positions = {s: p for s, p in positions.items() if p.qty > 0}
    return positions, cash


def value_positions(positions: Dict[str, Pos]) -> float:
    total = 0.0
    for s, p in positions.items():
        mark = p.last if (p.last is not None and p.last > 0) else p.avg
        total += p.qty * mark
    return round(total, 2)


# ---------------------- CLI ----------------------
def main():
    ap = argparse.ArgumentParser(description="Reconstruct NAV on a given date from merged trades.")
    ap.add_argument("date", help="YYYY-MM-DD (ET)")
    ap.add_argument("--include-gevo", action="store_true",
                    help="Include GEVO sells in realized cash (default excludes).")
    ap.add_argument("--debug", action="store_true", help="Print debug lines.")
    args = ap.parse_args()

    try:
        target_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    except Exception:
        print("[FATAL] date must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)

    start, end = cutoff_range_for_date(target_date)

    # Load as many as possible; your loader accepts days/start_iso/max_count
    # We'll just pull a big window and let the cutoff filter do the rest.
    trades = load_trades_merged(days=None, start_iso=None, max_count=100000) or []

    positions, cash = replay_positions_and_cash(
        trades,
        cutoff_end=end,
        exclude_gevo=(not args.include_gevo),
        debug=args.debug
    )
    pv = value_positions(positions)
    nav = round(cash + pv, 2)

    # Report
    print("\n=== NAV ON DATE ========================")
    print(f"Date:            {target_date.isoformat()}")
    print(f"Cash:            {pretty_money(cash)}")
    print(f"Positions Value: {pretty_money(pv)}")
    print("----------------------------------------")
    print(f"NAV:             {pretty_money(nav)}")
    print(f"Excluded:        {'GEVO' if not args.include_gevo else '(none)'}\n")

    if positions:
        print("Positions:")
        for s in sorted(positions.keys()):
            p = positions[s]
            mark = p.last if (p.last is not None and p.last > 0) else p.avg
            print(f"  {s:<6} qty={p.qty:.4f}  avg={pretty_money(p.avg)}  mark={pretty_money(mark)}  val={pretty_money(p.qty*mark)}")
    else:
        print("Positions:\n  (none)")

    print("=======================================\n")


if __name__ == "__main__":
    main()
