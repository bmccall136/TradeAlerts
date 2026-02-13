#!/usr/bin/env python
"""
update_sp500_symbols.py – FIXED VERSION
"""
from __future__ import annotations

import datetime as dt
import json
from io import StringIO  # <-- add this
from pathlib import Path
from typing import List
from io import StringIO

import pandas as pd
import requests

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 "
        "TradeAlerts-SP500-Updater/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

HERE = Path(__file__).resolve().parent
SYMBOL_FILE = HERE / "sp500_symbols.txt"
BACKUP_FILE = HERE / "sp500_symbols.txt.bak"


def fetch_sp500_html() -> str:
    """Fetch the Wikipedia page HTML with browser headers."""
    resp = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_sp500_symbols() -> list[str]:
    """Parse the S&P 500 table and return cleaned tickers."""
    html = fetch_sp500_html()

    # Use StringIO to avoid the FutureWarning about literal HTML
    tables = pd.read_html(StringIO(html))

    df = None
    for t in tables:
        if any("symbol" in str(c).lower() for c in t.columns):
            df = t
            break

    if df is None:
        raise RuntimeError("Could not locate S&P 500 symbol table")

    # Locate the actual 'Symbol' column
    sym_col = next((c for c in df.columns if "symbol" in str(c).lower()), None)
    if sym_col is None:
        raise RuntimeError("Symbol column missing")

    raw = df[sym_col].astype(str)

    cleaned = []
    for s in raw:
        s = s.strip().upper().replace(".", "-")
        if s:
            cleaned.append(s)

    # Remove duplicates while keeping order
    uniq: list[str] = []
    seen: set[str] = set()
    for s in cleaned:
        if s not in seen:
            seen.add(s)
            uniq.append(s)

    return uniq


def main():
    print("=== update_sp500_symbols.py ===")
    print(f"[{dt.datetime.now()}] Fetching S&P 500 symbols from Wikipedia…")

    try:
        new_syms = fetch_sp500_symbols()
    except Exception as e:
        print(f"[ERROR] Failed to update symbols: {e}")
        return 1

    old_syms = SYMBOL_FILE.read_text().splitlines() if SYMBOL_FILE.exists() else []

    print(f"[INFO] Existing count: {len(old_syms)}")
    print(f"[INFO] New count     : {len(new_syms)}")

    added = sorted(set(new_syms) - set(old_syms))
    removed = sorted(set(old_syms) - set(new_syms))

    if added:
        print(f"[INFO] Added {len(added)}: {', '.join(added[:10])}{'...' if len(added) > 10 else ''}")
    if removed:
        print(f"[INFO] Removed {len(removed)}: {', '.join(removed[:10])}{'...' if len(removed) > 10 else ''}")

    # Backup old file
    if SYMBOL_FILE.exists():
        BACKUP_FILE.write_text(SYMBOL_FILE.read_text())
    print(f"[INFO] Backup saved -> {BACKUP_FILE}")

    # Write new symbols
    SYMBOL_FILE.write_text("\n".join(new_syms) + "\n")
    print(f"[INFO] Backup saved -> {BACKUP_FILE}")

    print("=== Done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
