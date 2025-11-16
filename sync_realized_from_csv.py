#!/usr/bin/env python
"""
sync_realized_from_csv.py

One-time (or occasional) sync of realized trades from an E*TRADE
"Gains & Losses" CSV export into live.db::realized_trades.

Assumptions:
- CSV is the standard E*TRADE "Gains & Losses" report
  with a "TAXABLE G&L DETAILS" section.
- We only care about the detailed lot rows that start with "Sell".
- Close date is the *second* Date column in that section; in Python's
  csv.DictReader this shows up as the single "Date" field (the last one).
"""

import csv
import datetime as dt
import io
import os
import sqlite3
from typing import List, Tuple

# --- CONFIG ---------------------------------------------------------------

CSV_PATH = r"C:\TradeAlerts\GainsAndLossesDownload.csv"
LIVE_DB = r"C:\TradeAlerts\live.db"

BASELINE_DATE = dt.date(2025, 8, 22)  # inclusive
EXCLUDE_SYMBOLS = {"GEVO"}            # symbols to ignore completely


# --- HELPERS --------------------------------------------------------------


def _parse_money(raw: str) -> float:
    if raw is None:
        return 0.0
    s = str(raw).strip()
    if not s or s == "--":
        return 0.0
    s = s.replace("$", "").replace(",", "")
    return float(s)


def _parse_int(raw: str) -> int:
    if raw is None:
        return 0
    s = str(raw).strip()
    if not s or s == "--":
        return 0
    s = s.replace(",", "")
    return int(float(s))


def _parse_date(raw: str) -> dt.date:
    s = (raw or "").strip()
    if not s or s == "--":
        return None
    # E*TRADE uses MM/DD/YYYY
    return dt.datetime.strptime(s, "%m/%d/%Y").date()


def _load_detail_rows(path: str) -> List[dict]:
    """
    Return a list of DictReader rows starting at the
    'Symbol,Quantity,Date,Cost/Share $...' header under
    'TAXABLE G&L DETAILS'.
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()

    # Find the TAXABLE G&L DETAILS section
    marker = "Symbol,Quantity,Date,Cost/Share $,Total Cost $,Date,Price/Share $,Proceeds $,Gain $,Deferred Loss $,Term,Lot Selection"
    idx = text.find(marker)
    if idx == -1:
        raise RuntimeError("Could not find TAXABLE G&L DETAILS header in CSV.")

    detail_text = text[idx:]
    sio = io.StringIO(detail_text)
    reader = csv.DictReader(sio)

    return [row for row in reader]


def extract_realized_trades() -> List[Tuple]:
    """
    Convert CSV rows into tuples matching realized_trades schema:
    (symbol, action, qty, open_date, close_date,
     price_share, proceeds, cost_share, total_cost, gain, term)
    """
    rows = _load_detail_rows(CSV_PATH)
    realized = []

    current_symbol = None

    for row in rows:
        sym_raw = (row.get("Symbol") or "").strip()

        # Summary line (symbol) – remember it, but don't record as a trade
        if sym_raw and sym_raw.upper() != "SELL":
            current_symbol = sym_raw.upper()
            continue

        # Detail lot line – first column is "Sell"
        if sym_raw.upper() != "SELL":
            continue

        if not current_symbol:
            continue  # safety

        symbol = current_symbol
        if symbol in EXCLUDE_SYMBOLS:
            continue

        qty = _parse_int(row.get("Quantity"))
        if qty == 0:
            continue

        # In DictReader, the *second* Date column (close date) wins the name "Date"
        close_dt = _parse_date(row.get("Date"))
        if not close_dt or close_dt < BASELINE_DATE:
            continue

        cost_share = _parse_money(row.get("Cost/Share $"))
        total_cost = _parse_money(row.get("Total Cost $"))
        price_share = _parse_money(row.get("Price/Share $"))
        proceeds = _parse_money(row.get("Proceeds $"))
        gain = _parse_money(row.get("Gain $"))
        term = (row.get("Term") or "").strip()

        # We don't really need open_date for buckets; store close_date for both
        open_date_str = close_dt.isoformat()
        close_date_str = close_dt.isoformat()

        realized.append(
            (
                symbol,
                "SELL",
                qty,
                open_date_str,
                close_date_str,
                price_share,
                proceeds,
                cost_share,
                total_cost,
                gain,
                term,
            )
        )

    return realized


def main() -> None:
    print("=== Realized sync from CSV -> live.db ===")
    print(f"CSV: {CSV_PATH}")
    print(f"DB : {LIVE_DB}")
    print(f"Baseline date: {BASELINE_DATE.isoformat()}")
    print(f"Excluding symbols: {', '.join(sorted(EXCLUDE_SYMBOLS)) or '(none)'}")
    print()

    trades = extract_realized_trades()
    print(f"[CSV] Parsed {len(trades)} realized trade lots from CSV after filters.")

    if not trades:
        print("[WARN] No trades found; aborting without touching DB.")
        return

    con = sqlite3.connect(LIVE_DB)
    cur = con.cursor()

    # Inspect schema just for sanity/logging
    cur.execute("PRAGMA table_info(realized_trades)")
    cols = [r[1] for r in cur.fetchall()]
    print(f"realized_trades columns: {cols}")
    print()

    print("[DB] Deleting existing realized_trades rows...")
    cur.execute("DELETE FROM realized_trades")

    sql = """
    INSERT INTO realized_trades
      (symbol, action, qty, open_date, close_date,
       price_share, proceeds, cost_share, total_cost, gain, term)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    cur.executemany(sql, trades)
    con.commit()

    total_gain = sum(t[-2] for t in trades)
    first_close = min(dt.date.fromisoformat(t[4]) for t in trades)
    last_close = max(dt.date.fromisoformat(t[4]) for t in trades)

    print(f"[DB] Inserted {len(trades)} rows into realized_trades.")
    print(f"[DB] Date range: {first_close} -> {last_close}")
    print(f"[DB] Total realized gain (excl. {', '.join(EXCLUDE_SYMBOLS)}): ${total_gain:.2f}")

    con.close()
    print("Done.")


if __name__ == "__main__":
    main()
