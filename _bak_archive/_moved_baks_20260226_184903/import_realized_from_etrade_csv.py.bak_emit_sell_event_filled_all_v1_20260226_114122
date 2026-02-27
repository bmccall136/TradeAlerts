#!/usr/bin/env python3
"""Import E*TRADE "Gains & Losses" CSV into TradeAlerts live.db.

Why you currently see:
  - No Recent Trades
  - $0 realized P&L

Because your UI is reading ONLY from local SQLite tables:
  - trades
  - realized_trades

…and in your live.db both tables are empty.

This importer is defensive: E*TRADE exports are often multi-section CSVs.
It scans for the first DETAILS table header row containing Symbol + Qty + Gain,
then parses rows until a Total/blank row.

It populates:
  - realized_trades (for realized P&L buckets)
  - trades (for Recent Trades), unless --no-trades is set

Usage (PowerShell):
  cd C:\TradeAlerts
  python .\import_realized_from_etrade_csv.py "C:\EtradeExports\GainsAndLossesDownload.csv" --db "C:\TradeAlerts\live.db" --replace
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").strip().lower())


def _to_float(x: str | None) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s == "--":
        return None
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _parse_date(x: str | None) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s == "--":
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return None


def _iso_close_dt(close_date_iso: Optional[str]) -> str:
    # If we only have a date, store noon UTC to avoid time-zone drama.
    if not close_date_iso:
        return datetime.now(tz=timezone.utc).isoformat()
    try:
        if "T" in close_date_iso:
            dt = datetime.fromisoformat(close_date_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        return close_date_iso + "T12:00:00+00:00"
    except Exception:
        return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class RealizedRow:
    symbol: str
    qty: float
    open_date: Optional[str]
    close_date: Optional[str]
    cost_share: Optional[float]
    total_cost: Optional[float]
    price_share: Optional[float]
    proceeds: Optional[float]
    gain: Optional[float]
    term: Optional[str]


def read_csv_rows(path: str) -> List[List[str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def locate_details_table(rows: List[List[str]]) -> Tuple[int, Dict[str, int]]:
    # Find the first row that looks like: Symbol | Qty | ... | Gain
    for i, r in enumerate(rows):
        if not r:
            continue
        cells = [c.strip() for c in r if c is not None]
        if not cells:
            continue
        n = [_norm(c) for c in cells]
        has_symbol = "symbol" in n
        has_gain = any(x in n for x in ("gain", "gain$", "gaindollar"))
        has_qty = any(x in n for x in ("qty", "qty#", "quantity", "qtynum"))
        if has_symbol and has_gain and has_qty:
            colmap: Dict[str, int] = {}
            for idx, c in enumerate(cells):
                k = _norm(c)
                if k:
                    colmap[k] = idx
            return i, colmap

    preview = []
    for r in rows[:40]:
        preview.append(" | ".join([(c or "").strip() for c in r])[:240])
    raise SystemExit(
        "Could not locate the DETAILS table header row in this export.\n"
        "Preview of first rows:\n- " + "\n- ".join(preview)
    )


def parse_details(rows: List[List[str]], header_i: int, colmap: Dict[str, int]) -> List[RealizedRow]:
    def col(*names: str) -> Optional[int]:
        for nm in names:
            idx = colmap.get(_norm(nm))
            if idx is not None:
                return idx
        return None

    i_symbol = col("Symbol")
    i_qty = col("Qty #", "Qty", "Quantity")
    i_date_added = col("Date Added")
    i_cost_share = col("Cost / Share", "Cost/Share")
    i_total_cost = col("Total Cost")
    i_date_closed = col("Date", "Date Closed", "DateClosed")
    i_price_share = col("Price / Share", "Price/Share")
    i_proceeds = col("Proceeds")
    i_gain = col("Gain $", "Gain", "Gain$")
    i_term = col("Term")

    out: List[RealizedRow] = []

    for r in rows[header_i + 1 :]:
        if not r:
            break

        first = (r[i_symbol] if (i_symbol is not None and i_symbol < len(r)) else "").strip()
        if _norm(first) == "total":
            break

        # E*TRADE uses "--" placeholders
        if not first or first == "--":
            # If row is basically empty, stop; otherwise ignore.
            if sum(1 for c in r if (c or "").strip()) <= 1:
                break
            continue

        qty = _to_float(r[i_qty]) if (i_qty is not None and i_qty < len(r)) else None
        if qty is None:
            continue

        sym = first.upper()
        open_date = _parse_date(r[i_date_added]) if (i_date_added is not None and i_date_added < len(r)) else None
        close_date = _parse_date(r[i_date_closed]) if (i_date_closed is not None and i_date_closed < len(r)) else None
        cost_share = _to_float(r[i_cost_share]) if (i_cost_share is not None and i_cost_share < len(r)) else None
        total_cost = _to_float(r[i_total_cost]) if (i_total_cost is not None and i_total_cost < len(r)) else None
        price_share = _to_float(r[i_price_share]) if (i_price_share is not None and i_price_share < len(r)) else None
        proceeds = _to_float(r[i_proceeds]) if (i_proceeds is not None and i_proceeds < len(r)) else None
        gain = _to_float(r[i_gain]) if (i_gain is not None and i_gain < len(r)) else None
        term = (r[i_term].strip() if (i_term is not None and i_term < len(r) and r[i_term]) else None)

        out.append(
            RealizedRow(
                symbol=sym,
                qty=float(qty),
                open_date=open_date,
                close_date=close_date,
                cost_share=cost_share,
                total_cost=total_cost,
                price_share=price_share,
                proceeds=proceeds,
                gain=gain,
                term=term,
            )
        )

    if not out:
        raise SystemExit("Found the details header, but parsed 0 rows (export may be empty or filtered).")

    return out


DDL_REALIZED = """
CREATE TABLE IF NOT EXISTS realized_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    action TEXT,
    qty REAL,
    open_date TEXT,
    close_date TEXT,
    price_share REAL,
    proceeds REAL,
    cost_share REAL,
    total_cost REAL,
    gain REAL,
    term TEXT,
    price_paid REAL,
    price_sold REAL,
    gain_pct REAL
);
"""

DDL_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_time TEXT,
    symbol TEXT,
    action TEXT,
    qty REAL,
    price REAL,
    pnl REAL
);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(DDL_REALIZED)
    cur.execute(DDL_TRADES)
    con.commit()


def replace_rows(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute("DELETE FROM realized_trades;")
    cur.execute("DELETE FROM trades;")
    con.commit()


def insert_rows(con: sqlite3.Connection, realized: List[RealizedRow], also_trades: bool = True) -> Tuple[int, int]:
    cur = con.cursor()
    n_r = 0
    n_t = 0

    for r in realized:
        # E*TRADE sometimes leaves the close date blank in the CSV details.
        # Your realized_trades schema requires close_date, so default to today's date.
        if not r.close_date:
            r = RealizedRow(**{**r.__dict__, 'close_date': datetime.now().date().isoformat()})
        if not r.open_date:
            r = RealizedRow(**{**r.__dict__, 'open_date': r.close_date})

        total_cost = r.total_cost
        if total_cost is None and r.cost_share is not None:
            total_cost = float(r.cost_share) * float(r.qty)

        proceeds = r.proceeds
        if proceeds is None and r.price_share is not None:
            proceeds = float(r.price_share) * float(r.qty)

        gain = r.gain
        if gain is None and proceeds is not None and total_cost is not None:
            gain = float(proceeds) - float(total_cost)

        gain_pct = None
        if gain is not None and total_cost not in (None, 0):
            gain_pct = (float(gain) / float(total_cost)) * 100.0

        cur.execute(
            """
            INSERT INTO realized_trades
              (symbol, action, qty, open_date, close_date, price_share, proceeds,
               cost_share, total_cost, gain, term, price_paid, price_sold, gain_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.symbol,
                "SELL",
                float(r.qty),
                r.open_date,
                r.close_date,
                r.price_share,
                proceeds,
                r.cost_share,
                total_cost,
                gain,
                r.term,
                r.cost_share,
                r.price_share,
                gain_pct,
            ),
        )
        n_r += 1

        if also_trades:
            cur.execute(
                """
                INSERT INTO trades (trade_time, symbol, action, qty, price, pnl)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso_close_dt(r.close_date),
                    r.symbol,
                    "SELL",
                    float(r.qty),
                    float(r.price_share or 0.0),
                    float(gain or 0.0),
                ),
            )
            n_t += 1

    con.commit()
    return n_r, n_t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--db", default="live.db")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--no-trades", action="store_true")
    args = ap.parse_args()

    csv_path = os.path.expanduser(args.csv_path)
    db_path = os.path.expanduser(args.db)

    if not os.path.exists(csv_path):
        raise SystemExit(f"CSV file not found: {csv_path}")

    rows = read_csv_rows(csv_path)
    header_i, colmap = locate_details_table(rows)
    realized = parse_details(rows, header_i, colmap)

    con = sqlite3.connect(db_path)
    try:
        ensure_schema(con)
        if args.replace:
            replace_rows(con)
        n_r, n_t = insert_rows(con, realized, also_trades=(not args.no_trades))
    finally:
        con.close()

    print(f"Imported realized_trades rows: {n_r}")
    if not args.no_trades:
        print(f"Imported trades rows:         {n_t}")
    print("Done.")


if __name__ == "__main__":
    main()
